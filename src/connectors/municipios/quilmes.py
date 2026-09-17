"""Municipio de Quilmes (GBA sur).

Fuente: https://quilmes.gov.ar/contrataciones/licitaciones-publicas.php --
HTML server-side puro (sin JS), con TODO el historico 2000-2026 en una sola
pagina (~500 links, agrupados por año en un acordeon). Cada licitacion
tiene una pagina de detalle propia (licitacion-publica.php?id=N) con campos
etiquetados: Objeto, Presupuesto Oficial, fechas de retiro/recepcion/
apertura, lugar de apertura.

Por volumen, solo se visita el detalle de las licitaciones de los ultimos
`anios_atras` años (el listado no trae fecha por si solo, hay que abrir
cada detalle).
"""
import re
from datetime import datetime

import requests
from bs4 import BeautifulSoup

BASE = "https://quilmes.gov.ar/contrataciones/"
LISTADO_URL = BASE + "licitaciones-publicas.php"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; RadarLicitaciones/0.1; uso interno)"}

MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}

RE_LINK_NUMERO = re.compile(r"Licitaci[oó]n\s+P[uú]blica\s+N?°?\s*(\d+)\s*/\s*(\d{2,4})", re.IGNORECASE)
RE_OBJETO = re.compile(r"Objeto:\s*[\"“]?(.*?)[\"”]?\s*Presupuesto Oficial:", re.IGNORECASE | re.DOTALL)
RE_PRESUPUESTO = re.compile(r"Presupuesto Oficial:\s*\$\s*([\d.,]+)", re.IGNORECASE)
RE_APERTURA = re.compile(
    r"Fecha de apertura de ofertas:\s*(\d{1,2})/(\d{1,2})/(\d{4})\s*a las\s*(\d{1,2}):(\d{2})",
    re.IGNORECASE,
)


def _normalizar_anio(anio_texto: str) -> int:
    anio = int(anio_texto)
    return anio if anio > 100 else 2000 + anio


def _parse_monto(texto: str):
    try:
        return float(texto.replace(".", "").replace(",", "."))
    except ValueError:
        return None


def _listar() -> list[tuple[str, str, int]]:
    """[(id_url, numero_proceso, anio), ...] de todo el historico."""
    resp = requests.get(LISTADO_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    resultado = []
    for a in soup.find_all("a", href=True):
        if "licitacion-publica.php?id=" not in a["href"]:
            continue
        texto = a.get_text(" ", strip=True)
        m = RE_LINK_NUMERO.search(texto)
        if not m:
            continue
        numero, anio_txt = m.groups()
        anio = _normalizar_anio(anio_txt)
        resultado.append((a["href"], f"{numero}/{anio}", anio))
    return resultado


def _parse_detalle(id_url: str, numero_proceso: str) -> dict | None:
    resp = requests.get(BASE + id_url, headers=HEADERS, timeout=30)
    if resp.status_code != 200:
        return None
    soup = BeautifulSoup(resp.text, "html.parser")
    body = soup.find("body")
    texto = re.sub(r"\s+", " ", body.get_text(" ", strip=True)) if body else ""

    m_obj = RE_OBJETO.search(texto)
    objeto = m_obj.group(1).strip(' "“”.,') if m_obj else None

    fecha_apertura = None
    m_ap = RE_APERTURA.search(texto)
    if m_ap:
        dia, mes, anio, hora, minuto = m_ap.groups()
        try:
            fecha_apertura = datetime(int(anio), int(mes), int(dia), int(hora), int(minuto)).isoformat()
        except ValueError:
            pass

    m_presupuesto = RE_PRESUPUESTO.search(texto)

    return {
        "fuente": "muni_quilmes",
        "numero_proceso": numero_proceso,
        "titulo": f"Licitación Pública {numero_proceso} — {objeto}"[:250] if objeto else f"Licitación Pública {numero_proceso}",
        "descripcion": objeto,
        "organismo": "Municipalidad de Quilmes",
        "jurisdiccion": "Municipio de Quilmes (GBA sur)",
        "tipo_procedimiento": "Licitación Pública",
        "fecha_publicacion": None,
        "fecha_apertura": fecha_apertura,
        "monto_estimado": _parse_monto(m_presupuesto.group(1)) if m_presupuesto else None,
        "moneda": "ARS",
        "estado": None,
        "proveedor_adjudicado": None,
        "monto_adjudicado": None,
        "url": BASE + id_url,
    }


def fetch(anios_atras: int = 2, max_detalles: int = 120) -> list[dict]:
    anio_actual = datetime.now().year
    anio_limite = anio_actual - anios_atras
    items = [(u, n, a) for u, n, a in _listar() if a >= anio_limite][:max_detalles]

    rows = []
    for id_url, numero_proceso, _anio in items:
        try:
            row = _parse_detalle(id_url, numero_proceso)
        except Exception as e:
            print(f"  ! error en {numero_proceso}: {e}")
            continue
        if row:
            rows.append(row)
    return rows


if __name__ == "__main__":
    data = fetch()
    print(f"{len(data)} licitaciones normalizadas")
    for row in data[:5]:
        print(row)
