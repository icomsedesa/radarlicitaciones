"""Municipio de San Isidro (GBA norte).

Fuente: paginas individuales en www.sanisidro.gob.ar, una por licitacion,
con path predecible:

    /tramites-y-servicios/licitación-pública-nºN        (sin guion)
    /tramites-y-servicios/licitación-pública-nº-N        (con guion)

(la variante usada no es consistente en el tiempo, asi que se prueban
ambas). El listado /tramites-y-servicios/compras esta roto (404) y no hay
sitemap.xml ni buscador interno accesible sin login, asi que no hay forma
de "listar" -- se fuerza la numeracion (que es continua, no reinicia por
año) en un rango acotado.

Cada pagina tiene una tabla HTML simple con filas <strong>Etiqueta</strong>
/ valor: Expediente N°, Objeto de la Contratación, Presupuesto total del
Pliego, Fecha de apertura, Horario de apertura. El numero de licitacion y
el año vienen juntos en el titulo ("LICITACIÓN PÚBLICA 62 del 2024").

Requiere verify=False (mismo problema de cadena de certificados que otros
sitios .gob.ar de esta sesion).
"""
import re
import warnings

import requests
import urllib3
from bs4 import BeautifulSoup

warnings.simplefilter("ignore", urllib3.exceptions.InsecureRequestWarning)

BASE = "https://www.sanisidro.gob.ar/tramites-y-servicios/licitaci%C3%B3n-p%C3%BAblica-n%C2%BA"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; RadarLicitaciones/0.1; uso interno)"}

RE_TITULO = re.compile(r"LICITACI[OÓ]N\s+P[UÚ]BLICA\s+(\d+)\s+del\s+(\d{4})", re.IGNORECASE)
MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}


def _parse_monto(texto: str):
    m = re.search(r"\d{1,3}(?:\.\d{3})*(?:,\d{2})?", texto or "")
    if not m:
        return None
    numero = m.group(0).replace(".", "").replace(",", ".")
    try:
        return float(numero)
    except ValueError:
        return None


def _parse_fecha(fecha_texto: str, hora_texto: str):
    fecha_texto = (fecha_texto or "").strip()
    m = re.match(r"(\d{1,2})\s*-\s*(\d{1,2})\s*-\s*(\d{4})", fecha_texto)
    if not m:
        return None
    dia, mes, anio = (int(x) for x in m.groups())
    hora, minuto = 0, 0
    m_h = re.search(r"(\d{1,2}):(\d{2})", hora_texto or "")
    if m_h:
        hora, minuto = int(m_h.group(1)), int(m_h.group(2))
    from datetime import datetime
    try:
        return datetime(anio, mes, dia, hora, minuto).isoformat()
    except ValueError:
        return None


def _fetch_pagina(numero: int):
    for slug_numero in (str(numero), f"-{numero}"):
        url = f"{BASE}{slug_numero}"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=20, verify=False)
        except Exception:
            continue
        if resp.status_code == 200:
            return url, resp.text
    return None, None


def _parse_pagina(url: str, html: str):
    soup = BeautifulSoup(html, "html.parser")
    texto_pagina = soup.get_text(" ", strip=True)
    m_tit = RE_TITULO.search(texto_pagina)
    if not m_tit:
        return None
    numero, anio = m_tit.groups()
    numero_proceso = f"{numero}/{anio}"

    campos = {}
    for tr in soup.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) != 2:
            continue
        etiqueta = tds[0].get_text(" ", strip=True).rstrip(":")
        valor = tds[1].get_text(" ", strip=True)
        if etiqueta:
            campos[etiqueta] = valor

    objeto = campos.get("Objeto de la Contratación")
    fecha_apertura = _parse_fecha(campos.get("Fecha de apertura"), campos.get("Horario de apertura"))

    return {
        "fuente": "muni_san_isidro",
        "numero_proceso": numero_proceso,
        "titulo": f"Licitación Pública {numero_proceso} — {objeto}"[:250] if objeto else f"Licitación Pública {numero_proceso}",
        "descripcion": objeto,
        "organismo": "Municipalidad de San Isidro",
        "jurisdiccion": "Municipio de San Isidro (GBA norte)",
        "tipo_procedimiento": "Licitación Pública",
        "fecha_publicacion": None,
        "fecha_apertura": fecha_apertura,
        "monto_estimado": _parse_monto(campos.get("Presupuesto total del Pliego")),
        "moneda": "ARS",
        "estado": None,
        "proveedor_adjudicado": None,
        "monto_adjudicado": None,
        "url": url,
    }


def fetch(rango: range = range(1, 90)) -> list[dict]:
    rows = []
    for numero in rango:
        url, html = _fetch_pagina(numero)
        if not html:
            continue
        try:
            row = _parse_pagina(url, html)
        except Exception as e:
            print(f"  ! error parseando {url}: {e}")
            continue
        if row:
            rows.append(row)
    return rows


if __name__ == "__main__":
    data = fetch()
    print(f"{len(data)} licitaciones normalizadas")
    for row in data[:5]:
        print(row)
