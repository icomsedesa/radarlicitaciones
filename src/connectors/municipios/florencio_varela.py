"""Municipio de Florencio Varela (GBA sur).

Fuente: https://www.varela.gob.ar/licitaciones/default.aspx -- lista
simple de links a PDF (sin pagina de detalle, sin historico -- solo lo
vigente). Cada PDF tiene texto real con un patron muy regular.
"""
import re
from datetime import datetime

import requests
from bs4 import BeautifulSoup

LISTADO_URL = "https://www.varela.gob.ar/licitaciones/default.aspx"
BASE = "https://www.varela.gob.ar"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; RadarLicitaciones/0.1; uso interno)"}

RE_NUMERO = re.compile(r"LICITACI[OÓ]N\s+(P[UÚ]BLICA|PRIVADA)\s*N[°ºo]?\s*(\d+)\s*/\s*(\d{4})", re.IGNORECASE)
RE_OBJETO = re.compile(r"OBJETO:\s*[“\"](.*?)[”\"]", re.IGNORECASE | re.DOTALL)
RE_PRESUPUESTO = re.compile(r"PRESUPUESTO OFICIAL:\s*\$\s*([\d.,]+)", re.IGNORECASE)
RE_APERTURA = re.compile(r"APERTURA:\s*(\d{1,2})/(\d{1,2})/(\d{4})\s*HORA:\s*(\d{1,2}):(\d{2})", re.IGNORECASE)
RE_EXPEDIENTE = re.compile(r"Expte\.?\s*(?:Adm\.?)?\s*([\d\-A-Z]+)", re.IGNORECASE)


def _parse_monto(texto: str):
    try:
        return float(texto.replace(".", "").replace(",", "."))
    except ValueError:
        return None


def fetch() -> list[dict]:
    resp = requests.get(LISTADO_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    pdfs = [a["href"] for a in soup.find_all("a", href=True) if a["href"].lower().endswith(".pdf")]

    rows = []
    for href in pdfs:
        url = href if href.startswith("http") else BASE + href
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            r.raise_for_status()
        except Exception as e:
            print(f"  ! error descargando {url}: {e}")
            continue

        import io
        import pdfplumber

        try:
            with pdfplumber.open(io.BytesIO(r.content)) as pdf:
                texto = "\n".join(p.extract_text() or "" for p in pdf.pages[:2])
        except Exception as e:
            print(f"  ! error leyendo PDF {url}: {e}")
            continue
        texto_plano = re.sub(r"\s+", " ", texto)

        m_num = RE_NUMERO.search(texto_plano)
        if not m_num:
            continue
        tipo, numero, anio = m_num.groups()
        numero_proceso = f"{numero}/{anio}"

        m_obj = RE_OBJETO.search(texto_plano)
        objeto = m_obj.group(1).strip() if m_obj else None

        fecha_apertura = None
        m_ap = RE_APERTURA.search(texto_plano)
        if m_ap:
            dia, mes, anio_ap, hora, minuto = m_ap.groups()
            try:
                fecha_apertura = datetime(int(anio_ap), int(mes), int(dia), int(hora), int(minuto)).isoformat()
            except ValueError:
                pass

        m_presupuesto = RE_PRESUPUESTO.search(texto_plano)

        rows.append(
            {
                "fuente": "muni_florencio_varela",
                "numero_proceso": numero_proceso,
                "titulo": f"Licitación {tipo.title()} {numero_proceso} — {objeto}"[:250] if objeto else f"Licitación {tipo.title()} {numero_proceso}",
                "descripcion": objeto,
                "organismo": "Municipalidad de Florencio Varela",
                "jurisdiccion": "Municipio de Florencio Varela (GBA sur)",
                "tipo_procedimiento": f"Licitación {tipo.title()}",
                "fecha_publicacion": None,
                "fecha_apertura": fecha_apertura,
                "monto_estimado": _parse_monto(m_presupuesto.group(1)) if m_presupuesto else None,
                "moneda": "ARS",
                "estado": None,
                "proveedor_adjudicado": None,
                "monto_adjudicado": None,
                "url": url,
            }
        )
    return rows


if __name__ == "__main__":
    data = fetch()
    print(f"{len(data)} licitaciones normalizadas")
    for row in data:
        print(row)
