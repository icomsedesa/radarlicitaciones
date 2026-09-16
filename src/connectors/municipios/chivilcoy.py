"""Municipio de Chivilcoy (interior bonaerense, oeste del GBA).

Fuente: https://chivilcoy.gov.ar/licitaciones-publicas/ -- pagina WordPress
que el municipio reescribe a mano con la licitacion vigente del momento
(una sola a la vez, sin historico). Formato de texto regular y parseable.
"""
import re
from datetime import datetime

import requests
from bs4 import BeautifulSoup

URL = "https://chivilcoy.gov.ar/licitaciones-publicas/"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; RadarLicitaciones/0.1; uso interno)"}

MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}

RE_NUMERO = re.compile(r"LICITACI[OÓ]N\s+P[UÚ]BLICA\s+N[°ºo]?\s*(\d+)\s*/\s*(\d{4})", re.IGNORECASE)
RE_EXPEDIENTE = re.compile(r"Expediente\s+([\d\-]+)", re.IGNORECASE)
RE_APERTURA = re.compile(
    r"APERTURA DE PROPUESTAS:\s*D[ií]a:\s*(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})\s*\.?\s*Hora:\s*(\d{1,2}):(\d{2})",
    re.IGNORECASE,
)
RE_PRESUPUESTO = re.compile(r"PRESUPUESTO OFICIAL\s*:?\s*\$\s*([\d.,]+)", re.IGNORECASE)
RE_OBJETO = re.compile(r"LICITACI[OÓ]N\s+P[UÚ]BLICA\s+PARA\s+LA\s+(.*?)[«\"“](.*?)[»\"”]", re.IGNORECASE | re.DOTALL)


def _parse_monto(texto: str):
    try:
        return float(texto.replace(".", "").replace(",", "."))
    except ValueError:
        return None


def fetch() -> list[dict]:
    resp = requests.get(URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    main = soup.select_one("article") or soup.select_one(".entry-content") or soup
    texto = re.sub(r"\s+", " ", main.get_text(" ", strip=True))

    m_num = RE_NUMERO.search(texto)
    if not m_num:
        return []
    numero, anio = m_num.groups()
    numero_proceso = f"{numero}/{anio}"

    m_obj = RE_OBJETO.search(texto)
    objeto = (m_obj.group(1) + m_obj.group(2)).strip() if m_obj else texto[:300]

    m_apertura = RE_APERTURA.search(texto)
    fecha_apertura = None
    if m_apertura:
        dia, mes_nombre, anio_ap, hora, minuto = m_apertura.groups()
        mes_num = MESES.get(mes_nombre.lower())
        if mes_num:
            try:
                fecha_apertura = datetime(int(anio_ap), mes_num, int(dia), int(hora), int(minuto)).isoformat()
            except ValueError:
                pass

    m_presupuesto = RE_PRESUPUESTO.search(texto)
    m_expediente = RE_EXPEDIENTE.search(texto)

    row = {
        "fuente": "muni_chivilcoy",
        "numero_proceso": numero_proceso,
        "titulo": f"Licitación Pública {numero_proceso} — {objeto}"[:250],
        "descripcion": objeto,
        "organismo": "Municipalidad de Chivilcoy",
        "jurisdiccion": "Municipio de Chivilcoy (interior bonaerense)",
        "tipo_procedimiento": "Licitación Pública",
        "fecha_publicacion": None,
        "fecha_apertura": fecha_apertura,
        "monto_estimado": _parse_monto(m_presupuesto.group(1)) if m_presupuesto else None,
        "moneda": "ARS",
        "estado": None,
        "proveedor_adjudicado": None,
        "monto_adjudicado": None,
        "url": URL,
    }
    return [row]


if __name__ == "__main__":
    data = fetch()
    print(f"{len(data)} licitaciones normalizadas")
    for row in data:
        print(row)
