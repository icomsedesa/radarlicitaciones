"""Municipio de San Miguel (GBA norte).

Fuente: https://www.msm.gov.ar/pliegos/ -- pagina WordPress unica (sin API,
sin tabla) con TODO el historico 2020-2026 acumulado: un <h4> por proceso
("Licitacion publica 48'26") seguido de uno o mas <p><a href=...pdf> con
los documentos (pliego, planilla de cotizacion, redeterminacion, etc).

Limitaciones conocidas:
- No hay fecha de apertura ni expediente en el HTML -- solo dentro de los
  PDF, que no se parsean en esta primera version (podria sumarse despues).
- No hay estado (abierta/cerrada) publicado -- el listado acumula todo el
  historico sin distinguirlo.
"""
import re

import requests
from bs4 import BeautifulSoup

URL = "https://www.msm.gov.ar/pliegos/"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; RadarLicitaciones/0.1; uso interno)"}

RE_NUMERO = re.compile(r"Licitaci[oó]n\s+p[uú]blica\s+(\d+)[.''’](\d{2})", re.IGNORECASE)


def _limpiar_titulo(texto: str, numero_texto: str) -> str:
    # los links suelen empezar repitiendo "LICITACION PUBLICA 48'26 -- <objeto>"
    # o "PUBLICA 48'26 -- <objeto>"; nos quedamos solo con el objeto.
    t = re.sub(r"^(LICITACI[OÓ]N\s+)?P[UÚ]BLICA\s+[\d.''’]+\s*[-–]\s*", "", texto, flags=re.IGNORECASE)
    return t.strip() or texto.strip()


def fetch(limit: int | None = None) -> list[dict]:
    resp = requests.get(URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    container = soup.select_one(".post-content")
    if not container:
        return []

    rows = []
    heading = None
    docs: list[tuple[str, str]] = []

    def flush():
        if heading is None or not docs:
            return None
        m = RE_NUMERO.search(heading)
        if not m:
            return None
        numero, anio2 = m.groups()
        anio = 2000 + int(anio2)
        numero_proceso = f"{numero}/{anio}"
        # preferir el documento que diga "PLIEGO" (suele ser el mas descriptivo
        # del objeto real) tanto para el titulo como para la url principal
        texto_principal, principal = next(
            ((t, h) for t, h in docs if "PLIEGO" in t.upper()), docs[0]
        )
        titulo = _limpiar_titulo(texto_principal, f"{numero}'{anio2}")
        return {
            "fuente": "muni_san_miguel",
            "numero_proceso": numero_proceso,
            "titulo": titulo,
            "descripcion": "; ".join(t for t, _ in docs),
            "organismo": "Municipalidad de San Miguel",
            "jurisdiccion": "Municipio de San Miguel (GBA)",
            "tipo_procedimiento": "Licitación Pública",
            "fecha_publicacion": None,
            "fecha_apertura": None,
            "monto_estimado": None,
            "moneda": "ARS",
            "estado": None,
            "proveedor_adjudicado": None,
            "monto_adjudicado": None,
            "url": principal,
        }

    for el in container.find_all(["h4", "p"], recursive=False):
        if el.name == "h4":
            row = flush()
            if row:
                rows.append(row)
            heading = el.get_text(strip=True)
            docs = []
        else:
            a = el.find("a", href=True)
            if a:
                docs.append((a.get_text(strip=True), a["href"]))

    row = flush()
    if row:
        rows.append(row)

    if limit:
        rows = rows[:limit]
    return rows


if __name__ == "__main__":
    data = fetch()
    print(f"{len(data)} licitaciones normalizadas")
    for row in data[:5]:
        print(row)
