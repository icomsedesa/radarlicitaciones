"""Comparativas autenticadas de BAC (CABA): todas las ofertas recibidas
(no solo la adjudicataria) de los procesos en los que IcomSalud/SEDESA ya
oferto -- visible solo con la cuenta de proveedor logueada, en la pantalla
"Cuadro comparativo de ofertas" de cada proceso.

A diferencia de PAMI (Actas de Apertura publicas, sin login, para
cualquier proceso), esto solo cubre los procesos donde la cuenta
configurada en /configuracion efectivamente presento oferta -- son los
que listan en "Ofertas confirmadas" del escritorio de BAC ("Mi
escritorio"). Flujo verificado a mano (28-sep-2026): Mi escritorio ->
Ofertas confirmadas -> click en el numero de proceso -> VistaPreviaPliego
-> link "Ver cuadro comparativo" -> VerCuadroComparativo (URLs con un
token de sesion opaco por `qs=`, no hay forma de armarlas directo -- hay
que navegar la UI real cada vez).

Uso:
    python -m src.connectors.bac_ofertas
"""
import re

from playwright.sync_api import sync_playwright

from src.connectors.ofertas_comunes import extraer_cuadro, limpiar, volcar_debug
from src.connectors.portal_auth import login_bac, obtener_credencial

RE_NUMERO_PROCESO = re.compile(r"^\d+-\d+-[A-Z]{3}\d{2}$")


def _listar_procesos_ofertados(page) -> list[str]:
    """Numero de proceso de cada fila de "Ofertas confirmadas" -- son los
    unicos procesos con cuadro comparativo visible para esta cuenta.

    Los datos del escritorio ya estan en el DOM al cargar la pagina -- el
    "+"/"-" de cada seccion es solo un collapse visual (CSS), no hace
    falta clickear nada para leerlos. Confirmado contra el HTML real: el
    control ASP.NET de "Ofertas confirmadas" tiene un id que contiene
    "TablaTareaOfertasConfirmadas", asi que se puede acotar la busqueda de
    links a esa tabla puntual en vez de barrer toda la pagina (que
    mezclaba tambien Invitaciones/Procesos en los que participo/etc.)."""
    volcar_debug(page, "bac_ofertas_0_escritorio")

    tabla = page.locator('[id*="TablaTareaOfertasConfirmadas"]')
    numeros = []
    for link in tabla.locator("a").all():
        texto = limpiar(link.inner_text())
        if RE_NUMERO_PROCESO.match(texto):
            numeros.append(texto)
    # dedupe preservando orden
    vistos = set()
    resultado = []
    for n in numeros:
        if n not in vistos:
            vistos.add(n)
            resultado.append(n)
    return resultado


def _asegurar_visible(page, link, intentos_max: int = 4):
    """El escritorio de BAC es un accordion en DOS niveles (Procesos de
    compra > Ofertas confirmadas) -- el texto de cada link ya esta en el
    DOM apenas carga la pagina, pero no es clickeable hasta que ambos
    niveles esten expandidos visualmente. El estado inicial no es
    consistente: recien logueado arranca expandido, pero un reload (el
    goto() de vuelta al escritorio entre procesos) lo resetea colapsado
    -- por eso se chequea la visibilidad en cada intento en vez de asumir
    un estado fijo (evita clickear -y sin querer volver a colapsar- algo
    que ya estaba abierto)."""
    etiquetas = ("Procesos de compra", "Ofertas confirmadas")
    for i in range(intentos_max):
        if link.is_visible():
            return
        etiqueta = etiquetas[i % len(etiquetas)]
        try:
            page.get_by_text(etiqueta, exact=False).first.click(timeout=3000)
            page.wait_for_timeout(500)
        except Exception:
            pass


def fetch_todas_las_ofertas(headless: bool = True) -> list[dict]:
    """Devuelve [{"numero_proceso": ..., "ofertas": [...]}, ...] para cada
    proceso con oferta confirmada de la cuenta configurada. Cada oferta es
    un dict proveedor/cuit/monto/moneda/fecha_oferta/es_ganadora, mismo
    formato que espera db.set_ofertas."""
    usuario, password = obtener_credencial("bac")

    resultado = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        page = browser.new_page()
        try:
            login_bac(page, usuario, password)
            # "networkidle" a veces vuelve antes de que termine un
            # redirect final post-login (paso, una corrida real quedo con
            # la pagina "todavia navegando" y 0 links) -- se espera
            # explicitamente el contenido real del escritorio.
            page.wait_for_selector('[id*="TablaTareaOfertasConfirmadas"]', timeout=20000)
            url_escritorio = page.url

            numeros = _listar_procesos_ofertados(page)
            print(f"  {len(numeros)} procesos con oferta confirmada de esta cuenta: {numeros}")

            tabla = page.locator('[id*="TablaTareaOfertasConfirmadas"]')
            for i, numero in enumerate(numeros):
                try:
                    # acotado a la tabla de "Ofertas confirmadas" -- el
                    # mismo numero de proceso puede repetirse en otras
                    # secciones del escritorio (ej. "Procesos en los que
                    # participo"), y un click ahi no lleva al mismo lugar.
                    link = tabla.get_by_role("link", name=numero, exact=True)
                    _asegurar_visible(page, link)
                    link.click()
                    page.wait_for_load_state("networkidle")
                    if i == 0:
                        volcar_debug(page, "bac_ofertas_2_pliego")

                    page.get_by_role("link", name=re.compile("Ver cuadro comparativo", re.I)).click()
                    page.wait_for_load_state("networkidle")
                    if i == 0:
                        volcar_debug(page, "bac_ofertas_3_cuadro_comparativo")

                    ofertas = extraer_cuadro(page)
                    if ofertas:
                        resultado.append({"numero_proceso": numero, "ofertas": ofertas})
                        print(f"    {numero}: {len(ofertas)} ofertas")
                    else:
                        print(f"    {numero}: no se pudo extraer ninguna oferta (revisar selectores)")
                        volcar_debug(page, f"bac_ofertas_sin_ofertas_{numero}")

                    # se vuelve al escritorio por URL (no con go_back) --
                    # las paginas ASP.NET de por medio son postback-heavy y
                    # el historial del navegador no siempre las revive bien.
                    page.goto(url_escritorio, wait_until="domcontentloaded")
                    page.wait_for_selector('[id*="TablaTareaOfertasConfirmadas"]', timeout=20000)
                except Exception as e:
                    print(f"  ! error en {numero}: {e}")
                    volcar_debug(page, f"bac_ofertas_error_{numero}")
                    try:
                        page.goto(url_escritorio, wait_until="domcontentloaded")
                        page.wait_for_selector('[id*="TablaTareaOfertasConfirmadas"]', timeout=20000)
                    except Exception as e2:
                        print(f"  ! no se pudo volver al escritorio, se corta la corrida: {e2}")
                        break
        finally:
            browser.close()

    return resultado


if __name__ == "__main__":
    import sys

    headless = "--headless" in sys.argv
    data = fetch_todas_las_ofertas(headless=headless)
    total_ofertas = sum(len(d["ofertas"]) for d in data)
    print(f"\n{len(data)} procesos, {total_ofertas} ofertas en total")
    for row in data:
        print(row)
