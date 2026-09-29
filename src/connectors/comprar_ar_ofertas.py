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
(BusquedaAvanzadaProveedor.aspx) con TODO el historico de la cuenta
(~100 procesos desde 2017 al conectarlo). El filtro de fecha del propio
buscador (un widget DevExpress) resulto poco confiable -- se probo y no
acotaba el resultado real pese a no tirar error -- asi que en cambio se
filtra del lado nuestro: el numero de proceso ya trae el año codificado
al final ("LPU26" = 2026, "CDI18" = 2018), se recorren TODAS las paginas
del listado sin filtrar y se descartan los que no caen en los ultimos
ANIOS_ATRAS+1 años antes de procesarlos uno por uno.

Flujo verificado a mano (28-sep-2026): Mi escritorio -> "Procesos en los
cuales participé" -> buscador con resultados (paginado) -> click en el
numero de proceso -> detalle del proceso -> link "Ver cuadro
comparativo" -> VerCuadroComparativo (URLs con un token de sesion opaco
por `qs=`, no hay forma de armarlas directo -- hay que navegar la UI real
cada vez). Portal con bastante latencia/flakeo bajo uso real (timeouts
intermitentes, un overlay de carga AJAX que a veces tapa los links,
"page.goto()" sobre la URL del listado que no lo restaura -- carga un
formulario de busqueda vacio en su lugar) -- por eso el script vuelve a
entrar por el escritorio (unico punto de partida confirmado estable)
antes de cada proceso en vez de "volver para atras" entre uno y el
siguiente. Mas lento, pero cada paso ya esta probado. Vuelca captura +
HTML en cada etapa para poder ajustar si algo no matchea.

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


def _año_de_numero(numero: str) -> int:
    """"96-0018-LPU17" -> 2017, "509/3-0009-LPU26" -> 2026 -- los dos
    digitos finales del numero de proceso son el año (siempre 20XX en
    los datos vistos hasta ahora)."""
    m = re.search(r"[A-Z]{3}(\d{2})$", numero)
    return 2000 + int(m.group(1)) if m else 0


def _entrar_a_listado(page):
    """Desde el escritorio, entra a "Procesos en los cuales participé"
    (pagina 1 del listado). El portal a veces tarda en responder esta
    navegacion puntual mas de los 30s default de Playwright (visto en una
    corrida real: el click en si funciono, pero "esperar la navegacion" se
    agoto igual) -- mas margen y reintentos."""
    boton = page.get_by_text(re.compile("Procesos en los cuales particip", re.I)).first
    for intento in range(3):
        try:
            boton.click(timeout=60000)
            break
        except Exception as e:
            if intento == 2:
                raise
            print(f"  ! timeout entrando a 'Procesos en los cuales participé' (intento {intento + 1}), reintentando: {e}")
            page.wait_for_timeout(2000)
    page.wait_for_load_state("networkidle")
    _esperar_sin_overlay(page)


def _avanzar_a_pagina(page, pagina_objetivo: int):
    """Asume que ya esta en la pagina 1 del listado -- clickea "siguiente"
    hasta llegar a `pagina_objetivo`."""
    for pagina in range(1, pagina_objetivo):
        siguiente = page.get_by_role("link", name=str(pagina + 1), exact=True)
        if siguiente.count() == 0:
            break
        _esperar_sin_overlay(page)
        siguiente.click()
        page.wait_for_load_state("networkidle")
        _esperar_sin_overlay(page)


def _listar_procesos_participados(page) -> list[tuple[str, int]]:
    """Devuelve [(numero_proceso, pagina), ...] -- se guarda en que pagina
    del listado esta cada uno para poder volver a ubicarlo despues sin
    depender de goto()/go_back() (revisitar la URL capturada resulto NO
    confiable para este listado puntual: cargaba un formulario de
    busqueda vacio en vez del listado -- confirmado contra el HTML real
    de una corrida fallida)."""
    _entrar_a_listado(page)
    volcar_debug(page, "comprar_ar_ofertas_1_busqueda")

    # El filtro de fecha del buscador (widget DevExpress) resulto poco
    # confiable: se probo `fill()` + Tab sobre el input real y clickear
    # "Buscar" (un <a>, no un <button>) sin error, pero el resultado
    # seguia sin acotarse -- asi que en vez de forcejear mas con la UI se
    # trae TODO el listado (paginado) y se filtra aca por año, usando el
    # sufijo del propio numero de proceso.
    numeros = []  # [(numero, pagina), ...]
    pagina = 1
    while True:
        for link in page.locator("a").all():
            texto = limpiar(link.inner_text())
            if RE_NUMERO_PROCESO.match(texto):
                numeros.append((texto, pagina))
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
    for n, p in numeros:
        if n not in vistos:
            vistos.add(n)
            resultado.append((n, p))

    corte = datetime.now().year - ANIOS_ATRAS
    resultado = [(n, p) for n, p in resultado if _año_de_numero(n) >= corte]
    return resultado


def _ubicar_en_listado(page, url_escritorio: str, pagina: int, reintentos: int = 2) -> bool:
    """Se posiciona en la pagina `pagina` del listado, partiendo siempre
    del escritorio (URL estable, a diferencia de la de resultados -- ver
    docstring de _listar_procesos_participados).

    Hubo un intento de detectar "sesion vencida" (aterrizar en Login.aspx)
    y volver a loguear ahi mismo -- resulto CONTRAPRODUCENTE: una corrida
    real mostro que, en al menos un caso, el propio sitio ya estaba
    redirigiendo de vuelta al escritorio (sesion en realidad viva) cuando
    nuestro re-login intervino, y el choque entre esa redireccion propia y
    nuestro goto() a Login.aspx dejaba la pagina en un estado roto para
    el resto de la corrida ("Navigation interrupted by another
    navigation"). Mejor no reaccionar de forma especial ante eso: se
    reintenta la MISMA navegacion simple, con una pausa mas larga entre
    intentos para darle tiempo a que cualquier redireccion transitoria del
    sitio se asiente sola."""
    for intento in range(reintentos + 1):
        try:
            page.goto(url_escritorio, wait_until="domcontentloaded")
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(800)
            _entrar_a_listado(page)
            _avanzar_a_pagina(page, pagina)
            return True
        except Exception as e:
            if intento < reintentos:
                print(f"  ! no se pudo ubicar en la pagina {pagina} del listado (intento {intento + 1}), reintentando en unos segundos: {e}")
                page.wait_for_timeout(5000)
            else:
                print(f"  ! no se pudo ubicar en la pagina {pagina} del listado tras {reintentos + 1} intentos: {e}")
    return False


def fetch_todas_las_ofertas(headless: bool = True, max_procesos: int | None = None) -> list[dict]:
    """Devuelve [{"numero_proceso": ..., "ofertas": [...]}, ...] para cada
    proceso en el que participo la cuenta configurada (acotado a los
    ultimos ANIOS_ATRAS+1 años). Cada oferta es un dict proveedor/cuit/
    monto/moneda/fecha_oferta/es_ganadora, mismo formato que espera
    db.set_ofertas. `max_procesos` acota cuantos se procesan de punta a
    punta -- util para probar en chico (el portal mostro bastante
    latencia/flakeo real con lotes grandes)."""
    usuario, password = obtener_credencial("comprar_ar")

    resultado = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        page = browser.new_page()
        page.set_default_timeout(45000)  # el portal mostro latencia real por encima de los 30s default
        try:
            login_comprar_ar(page, usuario, password)
            page.wait_for_load_state("networkidle")
            url_escritorio = page.url
            volcar_debug(page, "comprar_ar_ofertas_0_escritorio")

            numeros = _listar_procesos_participados(page)
            if max_procesos:
                numeros = numeros[:max_procesos]
            print(f"  {len(numeros)} procesos participados desde {datetime.now().year - ANIOS_ATRAS}: {[n for n, _ in numeros]}")

            for i, (numero, pagina) in enumerate(numeros):
                try:
                    if i > 0:
                        # pausa entre procesos -- el portal mostro
                        # comportamiento raro (redirecciones que chocan
                        # entre si) bajo navegacion automatica muy seguida.
                        page.wait_for_timeout(1500)
                    # se re-ubica desde el escritorio antes de CADA proceso
                    # (mas lento que volver "para atras", pero confiable --
                    # ver _ubicar_en_listado).
                    if not _ubicar_en_listado(page, url_escritorio, pagina):
                        print(f"  ! no se pudo ubicar el listado para {numero}, se lo salta")
                        continue

                    _esperar_sin_overlay(page)
                    page.get_by_role("link", name=numero, exact=True).first.click()
                    page.wait_for_load_state("networkidle")
                    _esperar_sin_overlay(page)
                    # espera el contenido real del detalle (no solo
                    # "networkidle", que en un par de corridas volvio antes
                    # de que la navegacion terminara realmente).
                    page.wait_for_selector("text=Ofertas al proceso de compra", timeout=20000)
                    if i == 0:
                        volcar_debug(page, "comprar_ar_ofertas_3_pliego")

                    page.get_by_role("link", name=re.compile("Ver cuadro comparativo", re.I)).click()
                    page.wait_for_load_state("networkidle")
                    _esperar_sin_overlay(page)
                    page.wait_for_selector("text=Cuadro comparativo de ofertas", timeout=20000)
                    if i == 0:
                        volcar_debug(page, "comprar_ar_ofertas_4_cuadro_comparativo")

                    ofertas = extraer_cuadro(page)
                    if ofertas:
                        resultado.append({"numero_proceso": numero, "ofertas": ofertas})
                        print(f"    {numero}: {len(ofertas)} ofertas")
                    else:
                        print(f"    {numero}: no se pudo extraer ninguna oferta (revisar selectores)")
                        volcar_debug(page, f"comprar_ar_ofertas_sin_ofertas_{numero.replace('/', '_')}")
                except Exception as e:
                    print(f"  ! error en {numero}: {e}")
                    volcar_debug(page, f"comprar_ar_ofertas_error_{numero.replace('/', '_')}")
        finally:
            browser.close()

    return resultado


if __name__ == "__main__":
    import sys

    headless = "--headless" in sys.argv
    max_procesos = None
    if "--max" in sys.argv:
        max_procesos = int(sys.argv[sys.argv.index("--max") + 1])
    data = fetch_todas_las_ofertas(headless=headless, max_procesos=max_procesos)
    total_ofertas = sum(len(d["ofertas"]) for d in data)
    print(f"\n{len(data)} procesos, {total_ofertas} ofertas en total")
    for row in data:
        print(row)
