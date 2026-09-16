"""Municipio de San Andrés de Giles (interior bonaerense, oeste del GBA).

Fuente: https://www.sanandresdegiles.gob.ar/?q=licitaciones-publicas -- pagina
Drupal estatica (sin tabla) que el municipio reescribe a mano con las
licitaciones vigentes del momento; no guarda historico (al 16-sep-2026
todavia mostraba solo 3 licitaciones de marzo/2025 -- puede quedar
desactualizada por meses). El patron de redaccion es regular y parseable.
"""
import re
from datetime import datetime

import requests
from bs4 import BeautifulSoup

URL = "https://www.sanandresdegiles.gob.ar/?q=licitaciones-publicas"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; RadarLicitaciones/0.1; uso interno)"}

MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}

RE_BLOQUE = re.compile(
    r"Licitaci[oó]n\s+P[uú]blica\s+N[°ºo]?\s*(\d+)\s*/\s*(\d{4}).*?"
    r"Expediente\s+N[°ºo]?\s*([\d./\-]+)[,\s]*(?:referente a|–|-)?\s*(.*?)\."
    r"\s*Presupuesto Oficial:\s*\$\s*([\d.,]+)"
    r".*?Apertura de [Oo]fertas:\s*(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})\s+a\s+las\s+(\d{1,2}):(\d{2})",
    re.IGNORECASE | re.DOTALL,
)


def _parse_monto(texto: str):
    try:
        return float(texto.replace(".", "").replace(",", "."))
    except ValueError:
        return None


def fetch() -> list[dict]:
    resp = requests.get(URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    texto = soup.get_text("\n", strip=True)
    texto = re.sub(r"[ \t]+", " ", texto)

    rows = {}
    for m in RE_BLOQUE.finditer(texto):
        numero, anio, expediente, objeto, monto, dia, mes_nombre, anio_apertura, hora, minuto = m.groups()
        mes_num = MESES.get(mes_nombre.lower())
        fecha_apertura = None
        if mes_num:
            try:
                fecha_apertura = datetime(int(anio_apertura), mes_num, int(dia), int(hora), int(minuto)).isoformat()
            except ValueError:
                pass

        numero_proceso = f"{numero}/{anio}"
        objeto = objeto.strip(' "“”.,')
        rows[numero_proceso] = {
            "fuente": "muni_san_andres_giles",
            "numero_proceso": numero_proceso,
            "titulo": f"Licitación Pública {numero_proceso} — {objeto}"[:250],
            "descripcion": objeto,
            "organismo": "Municipalidad de San Andrés de Giles",
            "jurisdiccion": "Municipio de San Andrés de Giles (interior bonaerense)",
            "tipo_procedimiento": "Licitación Pública",
            "fecha_publicacion": None,
            "fecha_apertura": fecha_apertura,
            "monto_estimado": _parse_monto(monto),
            "moneda": "ARS",
            "estado": None,
            "proveedor_adjudicado": None,
            "monto_adjudicado": None,
            "url": URL,
        }
    return list(rows.values())


if __name__ == "__main__":
    data = fetch()
    print(f"{len(data)} licitaciones normalizadas")
    for row in data:
        print(row)
