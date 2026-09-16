"""Licitaciones nacionales con Estado = "Publicado" (abiertas ahora mismo).

El CSV masivo de COMPR.AR (`comprar_ar.py`) esta semanas desfasado: para
cuando se publica, la mayoria de los procesos que trae ya cerraron. Este
conector en cambio scrapea el buscador EN VIVO de comprar.gob.ar filtrando
por estado "Publicado", usando el mismo mecanismo de paginacion por
postback (`ctl00$CPH1$GridListaPliegos`, `Page$N`) que ya se uso para PBAC
y para el detalle de renglones. No trae renglones (para eso, ver
comprar_ar_items.fetch_renglones sobre el numero_proceso resultante).
"""
import re
from datetime import datetime

from playwright.sync_api import sync_playwright

BASE_URL = "https://comprar.gob.ar/BuscarAvanzado.aspx"
ESTADO_PUBLICADO = "6"


def _parse_fecha(text: str):
    text = text.strip().replace("Hrs.", "").strip()
    try:
        return datetime.strptime(text, "%d/%m/%Y %H:%M").isoformat()
    except ValueError:
        return None


def _parse_rows(page) -> list[dict]:
    # ">" restringe a filas directas de la tabla -- el renglon de paginacion
    # trae una tabla ANIDADA con sus propios <tr>, que "tr" sin scope
    # tambien matchearia (y se colarian como filas de datos invalidas).
    table = page.locator("table#ctl00_CPH1_GridListaPliegos")
    trs = table.locator("> tbody > tr, > tr").all()
    items = []
    for tr in trs[1:]:
        cls = tr.get_attribute("class") or ""
        if "pagination" in cls:
            continue
        tds = tr.locator("> td").all()
        if len(tds) < 7:
            continue
        numero = tds[0].inner_text().strip()
        if not numero:
            continue
        items.append(
            {
                "fuente": "comprar_ar",
                "numero_proceso": numero,
                "titulo": tds[2].inner_text().strip(),
                "descripcion": None,
                "organismo": tds[6].inner_text().strip(),
                "jurisdiccion": "Nación",
                "tipo_procedimiento": tds[3].inner_text().strip(),
                "fecha_publicacion": None,
                "fecha_apertura": _parse_fecha(tds[4].inner_text()),
                "monto_estimado": None,
                "moneda": "Peso Argentino",
                "estado": tds[5].inner_text().strip(),
                "proveedor_adjudicado": None,
                "monto_adjudicado": None,
                "url": None,
                "expediente": tds[1].inner_text().strip(),
            }
        )
    return items


FILAS_POR_PAGINA = 10


def _total_paginas(page) -> int:
    """El paginador de la grilla solo muestra una ventana de ~10 numeros
    con un link "..." que en realidad apunta a la pagina siguiente (no
    "revela mas"), asi que nunca expone el total real. Se usa en cambio
    el conteo de "Se han encontrado (N) resultados" del encabezado."""
    heading = page.locator("text=/Se han encontrado \\(\\d+\\) resultados/").first
    text = heading.inner_text()
    m = re.search(r"\((\d+)\)", text)
    total = int(m.group(1)) if m else FILAS_POR_PAGINA
    return max(1, -(-total // FILAS_POR_PAGINA))  # ceil division


def fetch_abiertas(max_paginas: int | None = None) -> list[dict]:
    """Trae todas las licitaciones nacionales en estado "Publicado".
    `max_paginas` acota para pruebas rapidas (None = todas)."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        try:
            page.goto(BASE_URL, wait_until="domcontentloaded")
            page.select_option("#ctl00_CPH1_ddlEstadoProceso", ESTADO_PUBLICADO)
            page.click("#ctl00_CPH1_btnListarPliegoAvanzado")
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
    data = fetch_abiertas(max_paginas=max_p)
    print(f"{len(data)} licitaciones publicadas (abiertas) encontradas")
    for row in data[:5]:
        print(row)
