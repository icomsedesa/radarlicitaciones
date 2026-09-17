"""Municipio de Avellaneda (GBA sur).

Fuente: https://www.mda.gob.ar/tramites/licitaciones/ -- HTML server-side
(sin JS) con TODO el historico en una sola pagina (~860 tarjetas
<div class="caja-sombra">), cada una con numero/año, objeto y decreto (con
fecha) directo en el texto -- no hace falta abrir el PDF "Nota" para esos
campos. La fecha de apertura si esta solo en el PDF, no se parsea en esta
primera version (igual que San Miguel).
"""
import re
import warnings
from datetime import datetime

import requests
import urllib3
from bs4 import BeautifulSoup

# cadena de certificados incompleta del lado del servidor -- fuente
# publica de solo lectura, sin dato sensible en juego.
warnings.simplefilter("ignore", urllib3.exceptions.InsecureRequestWarning)

URL = "https://www.mda.gob.ar/tramites/licitaciones/"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; RadarLicitaciones/0.1; uso interno)"}

RE_NUMERO = re.compile(r"LICITACI[OÓ]N\s+(P[UÚ]BLICA|PRIVADA)\s+NRO\.?\s*(\d+)\s*/\s*(\d{4})", re.IGNORECASE)
RE_OBJETO = re.compile(r"[“\"](.*?)[”\"]", re.DOTALL)
RE_DECRETO = re.compile(r"DECRETO\s+NRO\.?\s*N[°ºo]?\s*([\d.]+)\s*fechado el\s*(\d{1,2})/(\d{1,2})/(\d{4})", re.IGNORECASE)


def fetch(anios_atras: int = 2) -> list[dict]:
    resp = requests.get(URL, headers=HEADERS, timeout=30, verify=False)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    cajas = soup.find_all("div", class_="caja-sombra")

    anio_limite = datetime.now().year - anios_atras
    rows = {}
    for caja in cajas:
        texto = caja.get_text(" ", strip=True)
        m_num = RE_NUMERO.search(texto)
        if not m_num:
            continue
        tipo, numero, anio = m_num.groups()
        if int(anio) < anio_limite:
            continue
        numero_proceso = f"{numero}/{anio}"

        m_obj = RE_OBJETO.search(texto)
        objeto = m_obj.group(1).strip() if m_obj else None

        fecha_publicacion = None
        m_dec = RE_DECRETO.search(texto)
        if m_dec:
            _decreto, dia, mes, anio_dec = m_dec.groups()
            try:
                fecha_publicacion = datetime(int(anio_dec), int(mes), int(dia)).isoformat()
            except ValueError:
                pass

        nota = caja.find("a", href=lambda h: h and "licitacion" in h.lower() and h.lower().endswith(".pdf"))

        rows[numero_proceso] = {
            "fuente": "muni_avellaneda",
            "numero_proceso": numero_proceso,
            "titulo": f"Licitación {tipo.title()} {numero_proceso} — {objeto}"[:250] if objeto else f"Licitación {tipo.title()} {numero_proceso}",
            "descripcion": objeto,
            "organismo": "Municipalidad de Avellaneda",
            "jurisdiccion": "Municipio de Avellaneda (GBA sur)",
            "tipo_procedimiento": f"Licitación {tipo.title()}",
            "fecha_publicacion": fecha_publicacion,
            "fecha_apertura": None,
            "monto_estimado": None,
            "moneda": "ARS",
            "estado": None,
            "proveedor_adjudicado": None,
            "monto_adjudicado": None,
            "url": nota["href"] if nota else URL,
        }
    return list(rows.values())


if __name__ == "__main__":
    data = fetch()
    print(f"{len(data)} licitaciones normalizadas")
    for row in data[:5]:
        print(row)
