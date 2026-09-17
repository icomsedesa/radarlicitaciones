"""Municipio de Ituzaingó (GBA oeste).

Fuente: Boletin Oficial mensual en PDF (texto real, completo -- no
extractado) -- indice por año en miituzaingo.gov.ar/es/boletin-oficial-AAAA.
Cada mes trae varios decretos que mencionan la(s) licitacion(es) del
periodo en distintas etapas (llamado, admisibilidad, adjudicacion), con
una sub-frase bastante consistente:

    "la Licitacion Publica N° X/AAAA, tramitada [por|a traves de] [el]
    expediente [de] N° NNNN, destinada a|relacionada con la "OBJETO""

No siempre incluye fecha de apertura en esa sub-frase (depende del tipo de
decreto) -- queda en None cuando no se encuentra.
"""
import re
from datetime import datetime

import requests
from bs4 import BeautifulSoup
import pdfplumber
import io

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; RadarLicitaciones/0.1; uso interno)"}

RE_LIC = re.compile(
    r"Licitaci[oó]n\s+P[uú]blica\s+N[°ºo]?\s*(\d+)\s*/\s*(\d{4}),?\s*"
    r"tramitad[ao].{0,25}?expediente\s*(?:de\s*)?N[°ºo]?\s*([\d./\-]+),?\s*"
    r"(?:destinada a|relacionada con).{0,10}?[“\"](.*?)[”\"]",
    re.IGNORECASE | re.DOTALL,
)
RE_APERTURA = re.compile(
    r"Fecha de Apertura\s*:\s*(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})\s+a las\s*(\d{1,2}):(\d{2})",
    re.IGNORECASE,
)
MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}


def _listar_boletines(anio: int) -> list[str]:
    resp = requests.get(f"https://www.miituzaingo.gov.ar/es/boletin-oficial-{anio}", headers=HEADERS, timeout=30)
    if resp.status_code != 200:
        return []
    soup = BeautifulSoup(resp.text, "html.parser")
    return [a["href"] for a in soup.find_all("a", href=True) if a["href"].lower().endswith(".pdf")]


def _extraer_texto(url: str) -> str:
    """El boletin viene a dos columnas -- extract_text() normal intercala
    lineas de ambas mezclando frases sin sentido. Se recorta cada pagina
    por la mitad y se extrae columna por columna."""
    resp = requests.get(url, headers=HEADERS, timeout=60)
    resp.raise_for_status()
    texto = []
    with pdfplumber.open(io.BytesIO(resp.content)) as pdf:
        for pagina in pdf.pages:
            w, h = pagina.width, pagina.height
            izq = pagina.crop((0, 0, w / 2, h)).extract_text() or ""
            der = pagina.crop((w / 2, 0, w, h)).extract_text() or ""
            texto.append(izq)
            texto.append(der)
    full = "\n".join(texto)
    return re.sub(r"-\n", "", full)  # rejuntar palabras cortadas al final de linea


def fetch(anios: list[int] | None = None, max_boletines_por_anio: int = 3) -> list[dict]:
    anio_actual = datetime.now().year
    anios = anios or [anio_actual, anio_actual - 1]

    rows = {}
    for anio in anios:
        urls = _listar_boletines(anio)[:max_boletines_por_anio]
        for url in urls:
            try:
                texto_plano = re.sub(r"\s+", " ", _extraer_texto(url))
            except Exception as e:
                print(f"  ! error en {url}: {e}")
                continue

            for m in RE_LIC.finditer(texto_plano):
                numero, anio_lic, expediente, objeto = m.groups()
                numero_proceso = f"{numero}/{anio_lic}"
                objeto = objeto.strip(' "“”.,')[:300]

                fecha_apertura = None
                m_ap = RE_APERTURA.search(texto_plano, m.end(), m.end() + 2000)
                if m_ap:
                    dia, mes_nombre, anio_ap, hora, minuto = m_ap.groups()
                    mes_num = MESES.get(mes_nombre.lower())
                    if mes_num:
                        try:
                            fecha_apertura = datetime(int(anio_ap), mes_num, int(dia), int(hora), int(minuto)).isoformat()
                        except ValueError:
                            pass

                if numero_proceso not in rows or fecha_apertura:
                    rows[numero_proceso] = {
                        "fuente": "muni_ituzaingo",
                        "numero_proceso": numero_proceso,
                        "titulo": f"Licitación Pública {numero_proceso} — {objeto}"[:250],
                        "descripcion": objeto,
                        "organismo": "Municipalidad de Ituzaingó",
                        "jurisdiccion": "Municipio de Ituzaingó (GBA oeste)",
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
    return list(rows.values())


if __name__ == "__main__":
    data = fetch()
    print(f"{len(data)} licitaciones normalizadas")
    for row in data[:5]:
        print(row)
