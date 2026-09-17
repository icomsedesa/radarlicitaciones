"""Municipio de Tres de Febrero (GBA oeste).

Fuente: paginas propias por año, WordPress, sin tabla pero con estructura
<h3>Licitacion N/AAAA</h3> seguida de <p> muy regulares (objeto,
presupuesto, fecha de apertura, expediente). Sin JS, sin login.

El slug de la URL no es 100% consistente entre años (algunos dicen
"licitacionespublicasAAAA", otros "licitacionespublicacionesAAAA").
"""
import re
import warnings
from datetime import datetime

import requests
import urllib3
from bs4 import BeautifulSoup

# el sitio tiene la cadena de certificados incompleta (falta intermedio) --
# funciona con curl (usa el store del SO) pero no con certifi de Python.
# Es una fuente publica de solo lectura, no hay dato sensible en juego.
warnings.simplefilter("ignore", urllib3.exceptions.InsecureRequestWarning)

BASE = "https://www.tresdefebrero.gov.ar/"
# slugs confirmados; si un año no está mapeado, se intenta el patron por defecto igual
SLUGS_CONOCIDOS = {
    2022: "licitacionespublicas2022/",
    2023: "licitacionespublicas2023/",
    2025: "licitacionespublicas2025/",
    2026: "licitacionespublicaciones2026/",
}
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; RadarLicitaciones/0.1; uso interno)"}

MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}

RE_NUMERO = re.compile(r"Licitaci[oó]n\s+(\d+)\s*/\s*(\d{4})", re.IGNORECASE)
RE_PRESUPUESTO = re.compile(r"Presupuesto oficial:\s*\$\s*([\d.,]+)", re.IGNORECASE)
RE_APERTURA = re.compile(
    r"Fecha de apertura:\s*(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})\s+a las\s*(\d{1,2}):(\d{2})",
    re.IGNORECASE,
)
RE_EXPEDIENTE = re.compile(r"Expediente:\s*([\d.]+)", re.IGNORECASE)


def _parse_monto(texto: str):
    try:
        return float(texto.replace(".", "").replace(",", "."))
    except ValueError:
        return None


def _fetch_anio(anio: int, slug: str) -> list[dict]:
    resp = requests.get(BASE + slug, headers=HEADERS, timeout=30, verify=False)
    if resp.status_code != 200:
        return []
    soup = BeautifulSoup(resp.text, "html.parser")
    main = soup.select_one(".entry-content") or soup

    rows = []
    for h3 in main.find_all("h3"):
        m_num = RE_NUMERO.search(h3.get_text(" ", strip=True))
        if not m_num:
            continue
        numero, anio_lic = m_num.groups()
        numero_proceso = f"{numero}/{anio_lic}"

        parrafos = []
        for sib in h3.find_next_siblings():
            if sib.name == "h3":
                break
            if sib.name == "p":
                parrafos.append(sib.get_text(" ", strip=True))
        bloque = " ".join(parrafos)

        objeto = parrafos[0].strip() if parrafos else None
        m_presupuesto = RE_PRESUPUESTO.search(bloque)
        m_expediente = RE_EXPEDIENTE.search(bloque)

        fecha_apertura = None
        m_ap = RE_APERTURA.search(bloque)
        if m_ap:
            dia, mes_nombre, anio_ap, hora, minuto = m_ap.groups()
            mes_num = MESES.get(mes_nombre.lower())
            if mes_num:
                try:
                    fecha_apertura = datetime(int(anio_ap), mes_num, int(dia), int(hora), int(minuto)).isoformat()
                except ValueError:
                    pass

        rows.append(
            {
                "fuente": "muni_tres_de_febrero",
                "numero_proceso": numero_proceso,
                "titulo": f"Licitación {numero_proceso} — {objeto}"[:250] if objeto else f"Licitación {numero_proceso}",
                "descripcion": objeto,
                "organismo": "Municipalidad de Tres de Febrero",
                "jurisdiccion": "Municipio de Tres de Febrero (GBA oeste)",
                "tipo_procedimiento": "Licitación Pública",
                "fecha_publicacion": None,
                "fecha_apertura": fecha_apertura,
                "monto_estimado": _parse_monto(m_presupuesto.group(1)) if m_presupuesto else None,
                "moneda": "ARS",
                "estado": None,
                "proveedor_adjudicado": None,
                "monto_adjudicado": None,
                "url": BASE + slug,
            }
        )
    return rows


def fetch(anios: list[int] | None = None) -> list[dict]:
    anio_actual = datetime.now().year
    anios = anios or [a for a in SLUGS_CONOCIDOS if a >= anio_actual - 1]
    rows = {}
    for anio in anios:
        slug = SLUGS_CONOCIDOS.get(anio, f"licitacionespublicas{anio}/")
        try:
            for row in _fetch_anio(anio, slug):
                rows[row["numero_proceso"]] = row
        except Exception as e:  # pagina de un año puntual caida/con error de cert -- no cortar el resto
            print(f"  ! error en año {anio}: {e}")
    return list(rows.values())


if __name__ == "__main__":
    data = fetch(anios=list(SLUGS_CONOCIDOS.keys()))
    print(f"{len(data)} licitaciones normalizadas")
    for row in data[:5]:
        print(row)
