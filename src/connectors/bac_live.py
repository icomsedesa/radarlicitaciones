"""Licitaciones de BAC (CABA) con apertura futura -- buscador EN VIVO de
buenosairescompras.gob.ar.

El dataset masivo (`bac_anual.csv`, ver `bac.py`) esta desactualizado en
las fechas: de ~5200 procesos marcados 'active' en el OCDS, solo 1 tenia
`tenderPeriod.endDate` en el futuro (verificado 25-sep-2026) -- CABA no
actualiza esa fecha aunque el proceso siga administrativamente abierto.
Este conector en cambio scrapea `ListarAperturaProxima.aspx`, la misma
pagina que el propio portal de BAC usa para su acceso directo "Próximas
licitaciones" en la home, que SI trae la fecha de apertura real (170
procesos al conectarlo). Mismo mecanismo de paginacion por postback
(`GridListaPliegos`, `Page$N`) que ya se uso para COMPR.AR en vivo y PBAC.
"""
import re
from datetime import datetime

from playwright.sync_api import sync_playwright

HOME_URL = "https://buenosairescompras.gob.ar/Default.aspx"
URL = "https://buenosairescompras.gob.ar/ListarAperturaProxima.aspx"

FILAS_POR_PAGINA = 10


def _parse_fecha(texto: str):
    texto = texto.strip().replace("Hrs.", "").strip()
    try:
        return datetime.strptime(texto, "%d/%m/%Y %H:%M").isoformat()
    except ValueError:
        return None


def _parse_rows(page) -> list[dict]:
    table = page.locator("table#ctl00_CPH1_GridListaPliegos")
    trs = table.locator("> tbody > tr, > tr").all()
    items = []
    for tr in trs[1:]:  # trs[0] es el header
        tds = tr.locator("> td").all()
        if len(tds) < 6:
            continue
        numero = tds[0].inner_text().strip()
        if not numero or "-" not in numero:
            continue  # fila de paginacion, no un proceso
        items.append({
            "fuente": "bac",
            "numero_proceso": numero,
            "titulo": tds[1].inner_text().strip(),
            "descripcion": None,
            "organismo": tds[5].inner_text().strip(),
            "jurisdiccion": "CABA",
            "tipo_procedimiento": tds[2].inner_text().strip(),
            "fecha_publicacion": None,
            "fecha_apertura": _parse_fecha(tds[3].inner_text()),
            "monto_estimado": None,
            "moneda": "Peso Argentino",
            "estado": tds[4].inner_text().strip(),
            "proveedor_adjudicado": None,
            "monto_adjudicado": None,
            "url": URL,
        })
    return items


def _total_paginas(page) -> int:
    """Igual que en comprar_ar_live: el paginador solo muestra una ventana
    de ~10 numeros con un "..." que en realidad es la pagina siguiente, asi
    que se usa el conteo de "Se han encontrado (N) resultados" en cambio."""
    heading = page.locator("text=/Se han encontrado \\(\\d+\\) resultados/").first
    texto = heading.inner_text()
    m = re.search(r"\((\d+)\)", texto)
    total = int(m.group(1)) if m else FILAS_POR_PAGINA
    return max(1, -(-total // FILAS_POR_PAGINA))  # ceil division


def fetch(max_paginas: int | None = None) -> list[dict]:
    """Trae todas las licitaciones de BAC con apertura proxima (futura).
    `max_paginas` acota para pruebas rapidas (None = todas)."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        try:
            # entrar directo a ListarAperturaProxima.aspx sin visitar antes
            # el sitio rebota a la home (necesita la cookie de sesion que se
            # establece ahi) -- se pisa igual con el goto siguiente.
            page.goto(HOME_URL, wait_until="domcontentloaded")
            page.goto(URL, wait_until="domcontentloaded")
            page.wait_for_selector("table#ctl00_CPH1_GridListaPliegos", timeout=20000)

            resultados = _parse_rows(page)
            total_paginas = _total_paginas(page)
            if max_paginas:
                total_paginas = min(total_paginas, max_paginas)

            pagina = 2
            while pagina <= total_paginas:
                try:
                    page.evaluate(
                        "__doPostBack('ctl00$CPH1$GridListaPliegos', 'Page$" + str(pagina) + "')"
                    )
                    page.wait_for_load_state("networkidle")
                    page.wait_for_selector("table#ctl00_CPH1_GridListaPliegos", timeout=15000)
                    resultados.extend(_parse_rows(page))
                except Exception as e:  # pagina puntual con timeout/hiccup -- no cortar el lote
                    print(f"  ! error en pagina {pagina}: {e}")
                pagina += 1

            return resultados
        finally:
            browser.close()


if __name__ == "__main__":
    import sys

    max_p = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    data = fetch(max_paginas=max_p)
    print(f"{len(data)} licitaciones de BAC con apertura proxima")
    for row in data[:5]:
        print(row)
