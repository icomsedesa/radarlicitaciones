"""Comparativas autenticadas de COMPR.AR (Nacion): todas las ofertas
recibidas (no solo la adjudicataria) de los procesos en los que
IcomSalud ya participo -- visible solo con la cuenta de proveedor
logueada, en la pantalla "Cuadro comparativo de ofertas" de cada
proceso. Mismo formato -- y hasta la misma URL
(EVALUACIONOFERTA/VerCuadroComparativo.aspx) -- que BAC: claramente el
mismo software de fondo (confirmado con capturas reales de ambos
portales, 28-sep-2026). Ver src/connectors/ofertas_comunes.py para el
parseo compartido.

A diferencia de BAC (una lista corta ya armada, "Ofertas confirmadas"
con 5 procesos), en COMPR.AR el punto de entrada es "Procesos en los
cuales participé" en Mi escritorio, que lleva a un buscador
(BusquedaAvanzadaProveedor.aspx) con TODO el historico de la cuenta (92
procesos desde 2017 al conectarlo) -- se acota por fecha de creacion a
los ultimos ANIOS_ATRAS años para no procesar una decada de historial.

Flujo verificado a mano (28-sep-2026): Mi escritorio -> "Procesos en los
cuales participé" -> buscador con fecha desde/hasta + resultados -> click
en el numero de proceso -> detalle del proceso -> link "Ver cuadro
comparativo" -> VerCuadroComparativo (URLs con un token de sesion opaco
por `qs=`, no hay forma de armarlas directo -- hay que navegar la UI real
cada vez). Los selectores del buscador (campo de fecha, boton "Buscar",
paginacion) son una primera aproximacion, no verificada linea por linea
contra el HTML real como si se hizo para BAC -- si algo no matchea, este
script vuelca captura + HTML en cada paso para poder ajustarlo.

Uso:
    python -m src.connectors.comprar_ar_ofertas
"""
import re
from datetime import datetime

from playwright.sync_api import sync_playwright

from src.connectors.ofertas_comunes import extraer_cuadro, limpiar, volcar_debug
from src.connectors.portal_auth import login_comprar_ar, obtener_credencial

# "96-0018-LPU17" o "509/3-0009-LPU26" (la primera parte a veces trae un
# sufijo "/N" -- unidad operativa) -- distinto del formato de BAC (sin '/').
RE_NUMERO_PROCESO = re.compile(r"^\d+(?:/\d+)?-\d+-[A-Z]{3}\d{2}$")

ANIOS_ATRAS = 1  # ano actual + esta cantidad hacia atras


def _esperar_sin_overlay(page, timeout: int = 15000):
    """Los postbacks AJAX (UpdatePanel) de esta pagina muestran un overlay
    semitransparente (#divPanelFondoTransparente) mientras cargan -- si se
    clickea la pagina siguiente mientras sigue visible, el click queda
    bloqueado ("intercepts pointer events") hasta que se agota el timeout.
    "networkidle" no alcanza para detectar esto (las transiciones/timers
    del overlay no necesariamente generan trafico de red)."""
    try:
        page.wait_for_selector("#divPanelFondoTransparente", state="hidden", timeout=timeout)
    except Exception:
        pass  # si no aparecio o ya esta oculto, no hay nada que esperar


def _listar_procesos_participados(page) -> list[str]:
    page.get_by_text(re.compile("Procesos en los cuales particip", re.I)).first.click()
    page.wait_for_load_state("networkidle")
    volcar_debug(page, "comprar_ar_ofertas_1_busqueda")

    # el campo de fecha es un widget DevExpress (ASPxDateEdit) -- el
    # <label for=...> no apunta al id real del <input> (termina en "_I"),
    # asi que get_by_label no lo encuentra. "Buscar" tampoco es un
    # <button>, es un <a> con role "link".
    fecha_desde = f"01/01/{datetime.now().year - ANIOS_ATRAS}"
    try:
        campo = page.locator('input[id$="devDteEdtFechaDesde_I"]')
        campo.fill(fecha_desde)
        campo.press("Tab")  # dispara el blur -- el widget sincroniza su valor interno recien ahi
        page.get_by_role("link", name=re.compile(r"^\s*Buscar\s*$", re.I)).click()
        page.wait_for_load_state("networkidle")
        _esperar_sin_overlay(page)
    except Exception as e:
        print(f"  ! no se pudo acotar por fecha ({e}) -- sigue con el listado sin filtrar")
    volcar_debug(page, "comprar_ar_ofertas_2_post_filtro")
    # se guarda ACA (pagina 1 de resultados) -- no despues de recorrer la
    # paginacion, que dejaria la pagina posicionada en la ULTIMA pagina en
    # vez de la primera (asi volvia el goto() entre procesos, por eso el
    # primer numero de la lista tiraba timeout: no estaba en esa pagina).
    url_resultados = page.url

    numeros = []
    pagina = 1
    while True:
        for link in page.locator("a").all():
            texto = limpiar(link.inner_text())
            if RE_NUMERO_PROCESO.match(texto):
                numeros.append(texto)
        siguiente = page.get_by_role("link", name=str(pagina + 1), exact=True)
        if siguiente.count() == 0:
            break
        _esperar_sin_overlay(page)
        siguiente.click()
        page.wait_for_load_state("networkidle")
        _esperar_sin_overlay(page)
        pagina += 1
        if pagina > 30:  # tope de seguridad, no debería hacer falta
            break

    vistos = set()
    resultado = []
    for n in numeros:
        if n not in vistos:
            vistos.add(n)
            resultado.append(n)
    return resultado, url_resultados


def fetch_todas_las_ofertas(headless: bool = True) -> list[dict]:
    """Devuelve [{"numero_proceso": ..., "ofertas": [...]}, ...] para cada
    proceso en el que participo la cuenta configurada (acotado a los
    ultimos ANIOS_ATRAS+1 años). Cada oferta es un dict proveedor/cuit/
    monto/moneda/fecha_oferta/es_ganadora, mismo formato que espera
    db.set_ofertas."""
    usuario, password = obtener_credencial("comprar_ar")

    resultado = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        page = browser.new_page()
        try:
            login_comprar_ar(page, usuario, password)
            page.wait_for_load_state("networkidle")
            volcar_debug(page, "comprar_ar_ofertas_0_escritorio")

            # se vuelve a url_resultados (pagina 1 de la busqueda ya
            # filtrada) entre procesos, no a la del escritorio -- evita
            # rehacer la busqueda (click + filtro por fecha) en cada
            # iteracion.
            numeros, url_resultados = _listar_procesos_participados(page)
            print(f"  {len(numeros)} procesos participados desde {datetime.now().year - ANIOS_ATRAS}: {numeros}")

            for i, numero in enumerate(numeros):
                try:
                    _esperar_sin_overlay(page)
                    page.get_by_role("link", name=numero, exact=True).first.click()
                    page.wait_for_load_state("networkidle")
                    _esperar_sin_overlay(page)
                    if i == 0:
                        volcar_debug(page, "comprar_ar_ofertas_3_pliego")

                    page.get_by_role("link", name=re.compile("Ver cuadro comparativo", re.I)).click()
                    page.wait_for_load_state("networkidle")
                    _esperar_sin_overlay(page)
                    if i == 0:
                        volcar_debug(page, "comprar_ar_ofertas_4_cuadro_comparativo")

                    ofertas = extraer_cuadro(page)
                    if ofertas:
                        resultado.append({"numero_proceso": numero, "ofertas": ofertas})
                        print(f"    {numero}: {len(ofertas)} ofertas")
                    else:
                        print(f"    {numero}: no se pudo extraer ninguna oferta (revisar selectores)")
                        volcar_debug(page, f"comprar_ar_ofertas_sin_ofertas_{numero.replace('/', '_')}")

                    page.goto(url_resultados, wait_until="domcontentloaded")
                    page.wait_for_load_state("networkidle")
                    _esperar_sin_overlay(page)
                except Exception as e:
                    print(f"  ! error en {numero}: {e}")
                    volcar_debug(page, f"comprar_ar_ofertas_error_{numero.replace('/', '_')}")
                    try:
                        page.goto(url_resultados, wait_until="domcontentloaded")
                        page.wait_for_load_state("networkidle")
                    except Exception as e2:
                        print(f"  ! no se pudo volver al listado, se corta la corrida: {e2}")
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
