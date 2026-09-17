"""Municipio de Lanús (GBA sur).

Fuente: listado HTML server-side en lanus.gob.ar/documentos-oficiales,
filtrable por categoria (una por año: "Licitaciones Públicas 2020" a
"2026") y paginado (?categoria=N&page=M). Cada tarjeta <article> trae:

    .volanta   "LICITACION PUBLICA N°30 2DO LLAMADO - FECHA DE APERTURA
                23/09/2026- HORA 11:00HS"     (a veces es una Circular
                sobre una licitacion ya cargada, no un llamado nuevo)
    <h3>       objeto, entre comillas tipograficas
    .cover     link a la pagina de descarga del pliego

Nota: el sitio tuvo una caida prolongada (error 525 de Cloudflare) en un
intento anterior de esta sesion -- si vuelve a fallar, no es un problema
del conector, conviene reintentar mas tarde.

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

BASE = "https://www.lanus.gob.ar/documentos-oficiales"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; RadarLicitaciones/0.1; uso interno)"}

# categoria (id interno del sitio) -> año de "Licitaciones Públicas"
CATEGORIAS_POR_ANIO = {
    2026: 23, 2025: 22, 2024: 18, 2023: 17, 2022: 15, 2021: 12, 2020: 11,
}

RE_NUMERO = re.compile(r"LICITACI[OÓ]N\s+P[UÚ]BLICA\s+N[°ºo]?\s*(\d+)", re.IGNORECASE)
RE_FECHA = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})\s*-?\s*HORA\s*(\d{1,2}):(\d{2})", re.IGNORECASE)


def _parse_fecha(texto: str):
    m = RE_FECHA.search(texto or "")
    if not m:
        return None
    dia, mes, anio, hora, minuto = (int(x) for x in m.groups())
    try:
        return datetime(anio, mes, dia, hora, minuto).isoformat()
    except ValueError:
        return None


def _fetch_categoria(categoria: int, anio: int, max_paginas: int = 6) -> list[dict]:
    rows = {}
    for pagina in range(1, max_paginas + 1):
        try:
            resp = requests.get(
                BASE, params={"categoria": categoria, "page": pagina},
                headers=HEADERS, timeout=30, verify=False,
            )
            resp.raise_for_status()
        except Exception as e:
            print(f"  ! error en categoria={categoria} page={pagina}: {e}")
            break

        soup = BeautifulSoup(resp.text, "html.parser")
        articles = soup.find_all("article")
        if not articles:
            break

        for art in articles:
            volanta = art.find(class_="volanta")
            h3 = art.find("h3")
            link = art.find("a", class_="cover")
            if not volanta:
                continue
            texto_volanta = volanta.get_text(" ", strip=True)
            m_num = RE_NUMERO.search(texto_volanta)
            if not m_num:
                continue
            numero_proceso = f"{m_num.group(1)}/{anio}"
            objeto = h3.get_text(" ", strip=True).strip(' "“”') if h3 else None
            es_circular = "circular" in texto_volanta.lower()

            row = {
                "fuente": "muni_lanus",
                "numero_proceso": numero_proceso,
                "titulo": f"Licitación Pública {numero_proceso} — {objeto}"[:250] if objeto else f"Licitación Pública {numero_proceso}",
                "descripcion": objeto,
                "organismo": "Municipalidad de Lanús",
                "jurisdiccion": "Municipio de Lanús (GBA sur)",
                "tipo_procedimiento": "Licitación Pública",
                "fecha_publicacion": None,
                "fecha_apertura": _parse_fecha(texto_volanta),
                "monto_estimado": None,
                "moneda": "ARS",
                "estado": None,
                "proveedor_adjudicado": None,
                "monto_adjudicado": None,
                "url": link["href"] if link and link.get("href") else BASE,
            }
            # las circulares no traen objeto propio -- preferimos quedarnos
            # con la version del llamado original si ya la tenemos
            existente = rows.get(numero_proceso)
            if not existente or (not es_circular and existente["descripcion"] is None):
                rows[numero_proceso] = row

        if len(articles) < 20:
            break

    return list(rows.values())


def fetch(anios: list[int] | None = None) -> list[dict]:
    anios = anios or list(CATEGORIAS_POR_ANIO.keys())
    rows = {}
    for anio in anios:
        categoria = CATEGORIAS_POR_ANIO.get(anio)
        if not categoria:
            continue
        for row in _fetch_categoria(categoria, anio):
            rows[row["numero_proceso"]] = row
    return list(rows.values())


if __name__ == "__main__":
    data = fetch()
    print(f"{len(data)} licitaciones normalizadas")
    for row in data[:5]:
        print(row)
