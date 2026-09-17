"""Municipio de General Rodríguez (GBA oeste).

Fuente: HTML estatico (sin JS) en generalrodriguez.gob.ar, con paginas de
listado separadas para "actuales" y "pasadas":

    /licitaciones/            (publicas actuales)
    /licitaciones/pasadas     (publicas pasadas -- tiene el historial)

Cada licitacion es un bloque secuencial <h3>titulo<br>objeto</h3> seguido
de <p><b>Fecha de apertura:</b> DD/MM/AAAA - HH:MM hs.</p> dentro de un
<section> comun (no hay contenedor propio por licitacion, hay que iterar
los <h3> y tomar el <p> siguiente).

Requiere verify=False (mismo problema de cadena de certificados que otros
sitios .gob.ar de esta sesion).
"""
import re
import warnings
from datetime import datetime

import requests
import urllib3
from bs4 import BeautifulSoup

warnings.simplefilter("ignore", urllib3.exceptions.InsecureRequestWarning)

PAGINAS = [
    "https://generalrodriguez.gob.ar/licitaciones/",
    "https://generalrodriguez.gob.ar/licitaciones/pasadas",
]
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; RadarLicitaciones/0.1; uso interno)"}

RE_TITULO = re.compile(r"Licitaci[oó]n\s+P[uú]blica\s+N[°ºo]?\s*(\d+)\s*/\s*(\d{4})", re.IGNORECASE)
RE_FECHA = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})\s*-\s*(\d{1,2}):(\d{2})")


def _parse_fecha(texto: str):
    m = RE_FECHA.search(texto or "")
    if not m:
        return None
    dia, mes, anio, hora, minuto = (int(x) for x in m.groups())
    try:
        return datetime(anio, mes, dia, hora, minuto).isoformat()
    except ValueError:
        return None


def _parse_pagina(url: str) -> list[dict]:
    resp = requests.get(url, headers=HEADERS, timeout=30, verify=False)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    rows = []
    for h3 in soup.find_all("h3"):
        texto_h3 = h3.get_text(" ", strip=True)
        m = RE_TITULO.search(texto_h3)
        if not m:
            continue
        numero, anio = m.groups()
        numero_proceso = f"{numero}/{anio}"

        objeto = texto_h3.split(None, 1)
        # el objeto es lo que sigue al "Licitación Pública N°X/YYYY" inicial
        m_full = re.match(r"Licitaci[oó]n\s+P[uú]blica\s+N[°ºo]?\s*\d+\s*/\s*\d{4}\s*(.*)", texto_h3, re.IGNORECASE)
        objeto = m_full.group(1).strip(" -") if m_full else None

        p_fecha = h3.find_next_sibling("p")
        fecha_apertura = _parse_fecha(p_fecha.get_text(" ", strip=True)) if p_fecha else None

        rows.append(
            {
                "fuente": "muni_general_rodriguez",
                "numero_proceso": numero_proceso,
                "titulo": f"Licitación Pública {numero_proceso} — {objeto}"[:250] if objeto else f"Licitación Pública {numero_proceso}",
                "descripcion": objeto,
                "organismo": "Municipalidad de General Rodríguez",
                "jurisdiccion": "Municipio de General Rodríguez (GBA oeste)",
                "tipo_procedimiento": "Licitación Pública",
                "fecha_publicacion": None,
                "fecha_apertura": fecha_apertura,
                "monto_estimado": None,
                "moneda": "ARS",
                "estado": None,
                "proveedor_adjudicado": None,
                "monto_adjudicado": None,
                "url": url,
            }
        )
    return rows


def fetch() -> list[dict]:
    rows = {}
    for url in PAGINAS:
        try:
            for row in _parse_pagina(url):
                rows[row["numero_proceso"]] = row
        except Exception as e:
            print(f"  ! error en {url}: {e}")
    return list(rows.values())


if __name__ == "__main__":
    data = fetch()
    print(f"{len(data)} licitaciones normalizadas")
    for row in data[:5]:
        print(row)
