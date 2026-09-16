"""Municipio de Vicente López (GBA norte).

Fuente: https://www.vicentelopez.gov.ar/compras/ventadepliegos.php -- tabla
real con columnas claras (Contratacion, Numero, Año, Objeto, Presupuesto,
Fecha de Apertura), pero se llena por JS -- con requests/BeautifulSoup da
vacia, hace falta un browser real (Playwright).
"""
from datetime import datetime

from playwright.sync_api import sync_playwright

URL = "https://www.vicentelopez.gov.ar/compras/ventadepliegos.php"


def _parse_monto(texto: str):
    texto = texto.strip()
    if not texto or texto == "0":
        return None
    try:
        return float(texto.replace(".", "").replace(",", "."))
    except ValueError:
        return None


def _parse_fecha(texto: str):
    texto = texto.strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(texto, fmt).isoformat()
        except ValueError:
            continue
    return None


def fetch() -> list[dict]:
    filas_texto = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(URL, wait_until="networkidle", timeout=30000)
        for tr in page.locator("table tr").all():
            tds = tr.locator("td").all()
            if len(tds) >= 6:
                filas_texto.append([td.inner_text().strip() for td in tds])
        browser.close()

    resultado = []
    for valores in filas_texto:
        tipo, numero, anio, objeto = valores[0], valores[1], valores[2], valores[3]
        presupuesto, fecha_apertura_txt = valores[4], valores[5]
        if not numero.isdigit() or not anio.isdigit():
            continue  # salta la fila de encabezado

        numero_proceso = f"{numero}/{anio}"
        resultado.append(
            {
                "fuente": "muni_vicente_lopez",
                "numero_proceso": numero_proceso,
                "titulo": f"{tipo.title()} {numero_proceso} — {objeto.title()}"[:250],
                "descripcion": objeto,
                "organismo": "Municipalidad de Vicente López",
                "jurisdiccion": "Municipio de Vicente López (GBA)",
                "tipo_procedimiento": tipo.title(),
                "fecha_publicacion": None,
                "fecha_apertura": _parse_fecha(fecha_apertura_txt),
                "monto_estimado": _parse_monto(presupuesto),
                "moneda": "ARS",
                "estado": "Publicado",
                "proveedor_adjudicado": None,
                "monto_adjudicado": None,
                "url": URL,
            }
        )
    return resultado


if __name__ == "__main__":
    data = fetch()
    print(f"{len(data)} licitaciones normalizadas")
    for row in data:
        print(row)
