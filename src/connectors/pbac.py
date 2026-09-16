"""Conector PBAC (Provincia de Buenos Aires).

Fuente: portal ASP.NET WebForms sin API REST (pbac.cgp.gba.gov.ar).
Se scrapea el listado "Licitaciones de apertura proxima", paginado via
postback clasico de ASP.NET (__EVENTTARGET / __EVENTARGUMENT=Page$N).

Nota legal: el sitio declara los datos protegidos contra copia/reuso
comercial. Aceptable para uso interno; revisar antes de comercializar
(ver seccion "Riesgos y legal" del plan).
"""
from datetime import datetime

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://pbac.cgp.gba.gov.ar/ListarAperturaProxima.aspx"
GRID_ID = "ctl00_CPH1_GridListaPliegos"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; RadarLicitaciones/0.1; uso interno)"}


def _extract_hidden_fields(soup: BeautifulSoup) -> dict:
    fields = {}
    for name in ("__VIEWSTATE", "__VIEWSTATEGENERATOR", "__EVENTVALIDATION"):
        el = soup.find("input", {"name": name})
        if el and el.get("value") is not None:
            fields[name] = el["value"]
    return fields


def _parse_fecha_apertura(text: str):
    text = text.strip().replace("Hrs.", "").strip()
    try:
        return datetime.strptime(text, "%d/%m/%Y %H:%M").isoformat()
    except ValueError:
        return None


def _parse_rows(soup: BeautifulSoup) -> list[dict]:
    table = soup.find("table", id=GRID_ID)
    if not table:
        return []
    rows = []
    # ":scope >" restringe a filas directas -- el renglon de paginacion trae
    # una tabla ANIDADA con sus propios <tr>, que find_all("tr") (recursivo
    # por defecto) tambien matchearia como si fueran filas de datos.
    trs = table.select(":scope > tbody > tr") or table.select(":scope > tr")
    for tr in trs[1:]:  # salteamos header
        if "pagination" in (tr.get("class") or []):
            continue
        tds = tr.find_all("td", recursive=False)
        if len(tds) < 6:
            continue
        numero = tds[0].get_text(strip=True)
        if not numero or "-" not in numero:
            continue  # descarta filas de plantilla/placeholder de la grilla
        rows.append(
            {
                "fuente": "pbac",
                "numero_proceso": numero,
                "titulo": tds[1].get_text(strip=True),
                "descripcion": None,
                "organismo": tds[5].get_text(strip=True),
                "jurisdiccion": "Provincia de Buenos Aires",
                "tipo_procedimiento": tds[2].get_text(strip=True),
                "fecha_publicacion": None,
                "fecha_apertura": _parse_fecha_apertura(tds[3].get_text()),
                "monto_estimado": None,
                "moneda": "ARS",
                "estado": tds[4].get_text(strip=True),
                "proveedor_adjudicado": None,
                "monto_adjudicado": None,
                # no hay URL de detalle por proceso sin sesion (postback opaco);
                # se linkea al listado general, buscable por numero
                "url": BASE_URL,
            }
        )
    return rows


def fetch(max_pages: int = 5) -> list[dict]:
    """Trae hasta `max_pages` paginas (10 registros c/u) del listado publico.

    Default bajo (5 paginas = ~50 registros) para no sobrecargar el portal
    provincial durante pruebas; subir max_pages para una carga completa.
    """
    session = requests.Session()
    session.headers.update(HEADERS)

    resp = session.get(BASE_URL, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    all_rows = _parse_rows(soup)
    hidden = _extract_hidden_fields(soup)

    page = 2
    while page <= max_pages and hidden.get("__VIEWSTATE"):
        form = {
            "__EVENTTARGET": "ctl00$CPH1$GridListaPliegos",
            "__EVENTARGUMENT": f"Page${page}",
            **hidden,
        }
        resp = session.post(BASE_URL, data=form, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        rows = _parse_rows(soup)
        if not rows:
            break
        all_rows.extend(rows)
        hidden = _extract_hidden_fields(soup)
        page += 1

    return all_rows


if __name__ == "__main__":
    data = fetch(max_pages=3)
    print(f"{len(data)} licitaciones normalizadas")
    for row in data[:5]:
        print(row)
