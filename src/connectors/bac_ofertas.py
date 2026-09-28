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
from pathlib import Path

import re

from playwright.sync_api import sync_playwright

from src.connectors.portal_auth import login_bac, obtener_credencial

RE_NUMERO_PROCESO = re.compile(r"^\d+-\d+-[A-Z]{3}\d{2}$")
RE_OFERTA = re.compile(
    r"([A-ZÁÉÍÓÚÑ0-9.,&'()/ ]{3,90}?)\s*-\s*(\d{11})\s*\n?\s*Total:\s*ARS\s*([\d.]+,\d{2})"
)

SALIDA_DEBUG = Path(__file__).resolve().parent.parent.parent / "data" / "explorar"


def _limpiar(texto: str) -> str:
    return re.sub(r"\s+", " ", texto).strip()


def _volcar_debug(page, nombre: str):
    SALIDA_DEBUG.mkdir(parents=True, exist_ok=True)
    try:
        page.screenshot(path=str(SALIDA_DEBUG / f"{nombre}.png"), full_page=True)
        (SALIDA_DEBUG / f"{nombre}.html").write_text(page.content(), encoding="utf-8")
        print(f"  (debug) guardado {SALIDA_DEBUG / nombre}.png/.html")
    except Exception as e:
        print(f"  (debug) no se pudo volcar '{nombre}': {e}")


def _listar_procesos_ofertados(page) -> list[str]:
    """Numero de proceso de cada fila de "Ofertas confirmadas" -- son los
    unicos procesos con cuadro comparativo visible para esta cuenta."""
    _volcar_debug(page, "bac_ofertas_0_escritorio")

    # el escritorio es un acordeon anidado: "Procesos de compra" puede
    # arrancar colapsado, y "Ofertas confirmadas" (adentro) tambien -- se
    # intenta expandir los dos, tolerando que alguno ya este abierto.
    for etiqueta in ("Procesos de compra", "Ofertas confirmadas"):
        if page.get_by_text("Proceso de compra", exact=False).count() > 0:
            break  # la tabla ya esta visible, no hace falta seguir clickeando
        candidato = page.get_by_text(re.compile(re.escape(etiqueta)), exact=False).first
        try:
            candidato.click(timeout=3000)
            page.wait_for_timeout(800)
        except Exception as e:
            print(f"  (debug) no se pudo clickear '{etiqueta}': {e}")

    _volcar_debug(page, "bac_ofertas_1_post_expandir")

    todos_los_links = page.locator("a").all()
    print(f"  (debug) {len(todos_los_links)} links totales en la pagina")

    numeros = []
    for link in todos_los_links:
        texto = _limpiar(link.inner_text())
        if RE_NUMERO_PROCESO.match(texto):
            numeros.append(texto)
    # dedupe preservando orden (puede aparecer repetido si otro bloque del
    # escritorio tambien lista el mismo proceso)
    vistos = set()
    resultado = []
    for n in numeros:
        if n not in vistos:
            vistos.add(n)
            resultado.append(n)
    return resultado


def _extraer_cuadro(page) -> list[dict]:
    contenido = page.inner_text("body")
    ofertas = []
    for m in RE_OFERTA.finditer(contenido):
        nombre, cuit, monto_txt = m.groups()
        monto = float(monto_txt.replace(".", "").replace(",", "."))
        ofertas.append({
            "proveedor": nombre.strip(" -"),
            "cuit": cuit,
            "monto": monto,
            "moneda": "ARS",
            "fecha_oferta": None,
            "es_ganadora": False,
        })
    if ofertas:
        # marca la de menor monto como referencia -- igual que en el resto
        # de la app, NO implica que sea la adjudicataria real (eso depende
        # tambien de criterios tecnicos).
        minimo = min(o["monto"] for o in ofertas)
        for o in ofertas:
            o["es_ganadora"] = o["monto"] == minimo
    return ofertas


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
            url_escritorio = page.url

            numeros = _listar_procesos_ofertados(page)
            print(f"  {len(numeros)} procesos con oferta confirmada de esta cuenta: {numeros}")

            for numero in numeros:
                try:
                    page.get_by_role("link", name=numero, exact=True).first.click()
                    page.wait_for_load_state("networkidle")
                    page.get_by_role("link", name=re.compile("Ver cuadro comparativo", re.I)).click()
                    page.wait_for_load_state("networkidle")

                    ofertas = _extraer_cuadro(page)
                    if ofertas:
                        resultado.append({"numero_proceso": numero, "ofertas": ofertas})
                        print(f"    {numero}: {len(ofertas)} ofertas")
                    else:
                        print(f"    {numero}: no se pudo extraer ninguna oferta (revisar selectores)")

                    # se vuelve al escritorio por URL (no con go_back) --
                    # las paginas ASP.NET de por medio son postback-heavy y
                    # el historial del navegador no siempre las revive bien.
                    page.goto(url_escritorio, wait_until="domcontentloaded")
                except Exception as e:
                    print(f"  ! error en {numero}: {e}")
                    page.goto(url_escritorio, wait_until="domcontentloaded")
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
