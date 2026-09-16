"""Renglones (items) de un proceso puntual de COMPR.AR.

El CSV masivo de Convocatorias NO trae detalle de items -- solo existe en la
pagina de cada proceso ("Detalle de productos o servicios"), detras de un
buscador ASP.NET/DevExpress con token opaco por resultado. Por eso esto se
resuelve on-demand (por numero_proceso) con un browser headless (Playwright),
no en la carga masiva: se usa para completar renglones solo de las
licitaciones que interesan (p.ej. las vigentes), no de todo el historico.
"""
import re

from playwright.sync_api import sync_playwright

BASE_URL = "https://comprar.gob.ar/BuscarAvanzado.aspx"


def _parse_cantidad(text: str):
    text = text.strip()
    m = re.match(r"([\d.,]+)\s*(.*)", text)
    if not m:
        return None, None
    numero, unidad = m.groups()
    numero = numero.replace(".", "").replace(",", ".")
    try:
        return float(numero), unidad.strip() or None
    except ValueError:
        return None, unidad.strip() or None


def fetch_renglones(numero_proceso: str, page=None) -> dict:
    """Si no se pasa `page`, abre y cierra un browser propio (mas lento;
    para lotes usar fetch_renglones_batch). Devuelve {"url": ..., "items": [...]}."""
    if page is not None:
        return _fetch_with_page(page, numero_proceso)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page()
        try:
            return _fetch_with_page(pg, numero_proceso)
        finally:
            browser.close()


def _fetch_with_page(page, numero_proceso: str) -> dict:
    page.goto(BASE_URL, wait_until="domcontentloaded")
    page.fill("#ctl00_CPH1_txtNumeroProceso", numero_proceso)
    page.click("#ctl00_CPH1_btnListarPliegoNumero")

    link = page.locator(f"a:text-is('{numero_proceso}')").first
    try:
        link.wait_for(state="visible", timeout=20000)
    except Exception:
        return {"url": None, "items": []}  # sin resultados para este numero de proceso

    link.click()
    page.wait_for_selector("text=Detalle de productos o servicios", timeout=20000)
    url_detalle = page.url

    # la tabla de renglones esta bajo el encabezado "Detalle de productos o servicios"
    tables = page.locator("table")
    target = None
    for i in range(tables.count()):
        t = tables.nth(i)
        header = t.locator("tr").first
        if header.count() == 0:
            continue
        header_text = header.inner_text().lower()
        if "renglón" in header_text and "cantidad" in header_text:
            target = t
            break
    if target is None:
        return {"url": url_detalle, "items": []}

    items = []
    rows = target.locator("tr")
    for i in range(1, rows.count()):
        tr = rows.nth(i)
        tds = tr.locator("td")
        if tds.count() < 5:
            continue
        cantidad, unidad = _parse_cantidad(tds.nth(4).inner_text())
        items.append(
            {
                "numero_renglon": tds.nth(0).inner_text().strip(),
                "codigo_item": tds.nth(2).inner_text().strip(),
                "descripcion": tds.nth(3).inner_text().strip(),
                "cantidad": cantidad,
                "unidad": unidad,
                "precio_unitario": None,
                "moneda": None,
                "clasificacion": tds.nth(1).inner_text().strip(),
            }
        )
    return {"url": url_detalle, "items": items}


def fetch_renglones_batch(numeros_proceso: list[str]) -> dict[str, dict]:
    """Reusa un unico browser/page para varios procesos (mucho mas rapido
    que abrir uno por proceso). Devuelve {numero_proceso: {"url","items"}}."""
    resultados = {}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        for numero in numeros_proceso:
            try:
                resultados[numero] = _fetch_with_page(page, numero)
            except Exception as e:  # portal caido, timeout, etc. -- no cortar el lote
                print(f"  ! error en {numero}: {e}")
                resultados[numero] = {"url": None, "items": []}
        browser.close()
    return resultados


if __name__ == "__main__":
    import sys

    numero = sys.argv[1] if len(sys.argv) > 1 else "95-0004-CDI26"
    resultado = fetch_renglones(numero)
    print("url:", resultado["url"])
    for item in resultado["items"]:
        print(item)
