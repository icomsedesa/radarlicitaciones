"""Municipio de Escobar (GBA norte).

Fuente: https://www.escobar.gob.ar/licitaciones/ -- listado WordPress (no
tabla) que linkea a un post individual por licitacion, con permalink
predecible (/pliego-licitacion-publica-no-N-AA/). Cada post trae el texto
completo en un patron regular y parseable con regex.
"""
import re
from datetime import datetime

import requests
from bs4 import BeautifulSoup

LISTADO_URL = "https://www.escobar.gob.ar/licitaciones/"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; RadarLicitaciones/0.1; uso interno)"}

MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}

RE_NUMERO = re.compile(r"Licitaci[oó]n\s+P[uú]blica\s+N[°ºo]?\s*(\d+)\s*/\s*(\d{2,4})", re.IGNORECASE)
RE_OBJETO = re.compile(
    r"Licitaci[oó]n\s+P[uú]blica\s+N[°ºo]?\s*\d+\s*/\s*\d{2,4}[,]?\s*(?:realizada\s+)?"
    r"(?:para|referente a)?\s*(?:la\s+)?(?:contrataci[oó]n\s+de\s+la\s+obra:?|contrataci[oó]n\s+de|adquisici[oó]n\s+de)?\s*"
    r"[:\-]?\s*[“\"]?(.*?)[”\"]?\s*Fecha de apertura",
    re.IGNORECASE | re.DOTALL,
)
RE_APERTURA = re.compile(
    r"apertura de sobres se realizar[aá]\s*(?:el\s+d[ií]a)?\s*(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})\s+a las\s*(\d{1,2})[.:](\d{2})",
    re.IGNORECASE,
)
RE_PRESUPUESTO = re.compile(r"Presupuesto oficial\s*Pesos[^(]*\(\$?\s*([\d.,]+)\)", re.IGNORECASE)
RE_EXPEDIENTE = re.compile(r"EXPEDIENTE\s*N[°ºo]?\s*([\d./]+)", re.IGNORECASE)


def _listar_links() -> list[str]:
    resp = requests.get(LISTADO_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    links = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "escobar.gob.ar/pliego-licitacion" in href or "escobar.gob.ar/licitacion-" in href:
            links.add(href.split("?")[0])
    return sorted(links)


def _parse_monto(texto: str):
    try:
        return float(texto.replace(".", "").replace(",", "."))
    except ValueError:
        return None


def _parse_post(url: str) -> dict | None:
    resp = requests.get(url, headers=HEADERS, timeout=30)
    if resp.status_code != 200:
        return None
    soup = BeautifulSoup(resp.text, "html.parser")
    body = soup.find("body")
    texto = re.sub(r"\s+", " ", body.get_text(" ", strip=True)) if body else ""

    m_num = RE_NUMERO.search(texto)
    if not m_num:
        return None
    numero, anio_txt = m_num.groups()
    anio = int(anio_txt)
    anio = anio if anio > 100 else 2000 + anio
    numero_proceso = f"{numero}/{anio}"

    m_obj = RE_OBJETO.search(texto)
    objeto = m_obj.group(1).strip(' "“”.,-') if m_obj else None

    fecha_apertura = None
    m_ap = RE_APERTURA.search(texto)
    if m_ap:
        dia, mes_nombre, anio_ap, hora, minuto = m_ap.groups()
        mes_num = MESES.get(mes_nombre.lower())
        if mes_num:
            try:
                fecha_apertura = datetime(int(anio_ap), mes_num, int(dia), int(hora), int(minuto)).isoformat()
            except ValueError:
                pass

    m_presupuesto = RE_PRESUPUESTO.search(texto)
    m_expediente = RE_EXPEDIENTE.search(texto)

    return {
        "fuente": "muni_escobar",
        "numero_proceso": numero_proceso,
        "titulo": f"Licitación Pública {numero_proceso} — {objeto}"[:250] if objeto else f"Licitación Pública {numero_proceso}",
        "descripcion": objeto,
        "organismo": "Municipalidad de Escobar",
        "jurisdiccion": "Municipio de Escobar (GBA norte)",
        "tipo_procedimiento": "Licitación Pública",
        "fecha_publicacion": None,
        "fecha_apertura": fecha_apertura,
        "monto_estimado": _parse_monto(m_presupuesto.group(1)) if m_presupuesto else None,
        "moneda": "ARS",
        "estado": None,
        "proveedor_adjudicado": None,
        "monto_adjudicado": None,
        "url": url,
    }


def fetch(max_posts: int = 60) -> list[dict]:
    links = _listar_links()[:max_posts]
    rows = []
    for url in links:
        try:
            row = _parse_post(url)
        except Exception as e:  # pagina puntual con formato distinto -- no cortar el lote
            print(f"  ! error en {url}: {e}")
            continue
        if row:
            rows.append(row)
    return rows


if __name__ == "__main__":
    data = fetch()
    print(f"{len(data)} licitaciones normalizadas")
    for row in data[:5]:
        print(row)
