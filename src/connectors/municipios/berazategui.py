"""Municipio de Berazategui (GBA sur).

Fuente: https://berazategui.gob.ar/licitaciones/ -- el listado se arma por
JS/AJAX (grilla WPBakery, requiere un nonce que no vale la pena replicar a
mano), asi que se usa Playwright solo para levantar la lista de links.
Pero el PDF de cada licitacion sigue un patron de URL predecible que no
depende del listado ni de la pagina de noticia intermedia:

    https://berazategui.gob.ar/descargas/licitaciones/{anio}/licitacion-publica-{numero}-{anio}.pdf

con texto real y campos etiquetados (Expediente, Presupuesto Oficial,
Apertura de ofertas).
"""
import re
from datetime import datetime

import requests
from playwright.sync_api import sync_playwright

LISTADO_URL = "https://berazategui.gob.ar/licitaciones/"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; RadarLicitaciones/0.1; uso interno)"}

RE_SLUG = re.compile(r"licitacion-publica-no-(\d+)-(\d{4})", re.IGNORECASE)
RE_EXPEDIENTE = re.compile(r"Expediente\s+N[°ºo]?\s*([\w.\-]+)", re.IGNORECASE)
RE_OBJETO = re.compile(r"para el objeto:\s*[“\"](.*?)[”\"]", re.IGNORECASE | re.DOTALL)
RE_PRESUPUESTO = re.compile(r"Presupuesto Oficial Total:\s*\$\s*([\d.,]+)", re.IGNORECASE)
RE_APERTURA = re.compile(
    r"Apertura de ofertas:.*?(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4}),?\s*a\s*(?:las)?\s*(\d{1,2})[.:](\d{2})",
    re.IGNORECASE | re.DOTALL,
)
MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}


def _listar_numeros(max_links: int = 40) -> list[tuple[str, str]]:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(LISTADO_URL, wait_until="networkidle", timeout=30000)
        hrefs = [a.get_attribute("href") or "" for a in page.locator('a[href*="licitacion"]').all()]
        browser.close()

    vistos = set()
    resultado = []
    for href in hrefs:
        m = RE_SLUG.search(href)
        if not m:
            continue
        numero, anio = m.groups()
        if (numero, anio) in vistos:
            continue
        vistos.add((numero, anio))
        resultado.append((numero, anio))
    return resultado[:max_links]


def _parse_monto(texto: str):
    try:
        return float(texto.replace(".", "").replace(",", "."))
    except ValueError:
        return None


def fetch(max_licitaciones: int = 40) -> list[dict]:
    rows = []
    for numero, anio in _listar_numeros(max_licitaciones):
        url = f"https://berazategui.gob.ar/descargas/licitaciones/{anio}/licitacion-publica-{numero}-{anio}.pdf"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=30)
            if resp.status_code != 200:
                continue
        except Exception as e:
            print(f"  ! error descargando {url}: {e}")
            continue

        import io
        import pdfplumber

        try:
            with pdfplumber.open(io.BytesIO(resp.content)) as pdf:
                texto = "\n".join((p.extract_text() or "") for p in pdf.pages[:2])
        except Exception as e:
            print(f"  ! error leyendo PDF {url}: {e}")
            continue
        texto_plano = re.sub(r"\s+", " ", texto)

        numero_proceso = f"{numero}/{anio}"
        m_obj = RE_OBJETO.search(texto_plano)
        objeto = m_obj.group(1).strip() if m_obj else None
        m_exp = RE_EXPEDIENTE.search(texto_plano)
        m_pre = RE_PRESUPUESTO.search(texto_plano)

        fecha_apertura = None
        m_ap = RE_APERTURA.search(texto_plano)
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
                "fuente": "muni_berazategui",
                "numero_proceso": numero_proceso,
                "titulo": f"Licitación Pública {numero_proceso} — {objeto}"[:250] if objeto else f"Licitación Pública {numero_proceso}",
                "descripcion": objeto,
                "organismo": "Municipalidad de Berazategui",
                "jurisdiccion": "Municipio de Berazategui (GBA sur)",
                "tipo_procedimiento": "Licitación Pública",
                "fecha_publicacion": None,
                "fecha_apertura": fecha_apertura,
                "monto_estimado": _parse_monto(m_pre.group(1)) if m_pre else None,
                "moneda": "ARS",
                "estado": None,
                "proveedor_adjudicado": None,
                "monto_adjudicado": None,
                "url": url,
            }
        )
    return rows


if __name__ == "__main__":
    data = fetch(max_licitaciones=10)
    print(f"{len(data)} licitaciones normalizadas")
    for row in data[:5]:
        print(row)
