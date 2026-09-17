"""Municipio de Lomas de Zamora (GBA sur).

Fuente: Boletin Oficial mensual en PDF (Decretos y Resoluciones por
separado), descubierto via un endpoint AJAX de ASP.NET (PageMethod) que
no necesita browser:

    POST https://formularios.lomasdezamora.gov.ar/BoletinOficial.aspx/getHTMLs
    Content-Type: application/json; charset=utf-8
    Body: {subseccion:"294"}          # el id de "subseccion" = el año;
                                        # 294 = 2026, 293 = 2025, etc.
                                        # (se ve en el HTML de la pagina)

Devuelve {"d": "<html con links a PDF por mes>"}. El texto de los PDF es
real (no escaneado), con un patron razonablemente regular:

    "Llamar a Licitacion Publica Nº 82/26, cuya apertura se realizara en
    fecha y hora a determinar, para la contratacion de..."
    "Aprobar la Contratacion efectuada por la Licitacion Privada Nº
    212/26, para la adquisicion de..."

Limitacion conocida: la fecha de apertura casi siempre figura como "a
determinar" en el decreto de llamado (no hay fecha fija todavia) -- queda
en None en esos casos.
"""
import re
import warnings
from datetime import datetime

import requests
import urllib3
from bs4 import BeautifulSoup
import pdfplumber
import io

warnings.simplefilter("ignore", urllib3.exceptions.InsecureRequestWarning)

AJAX_URL = "https://formularios.lomasdezamora.gov.ar/BoletinOficial.aspx/getHTMLs"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; RadarLicitaciones/0.1; uso interno)"}

# id de "subseccion" -> año (extraido del HTML de la pagina del boletin)
SUBSECCION_POR_ANIO = {2026: "294", 2025: "293", 2024: "264"}

MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}

RE_LIC = re.compile(r"Licitaci[oó]n\s+(P[uú]blica|Privada)\s+N[°ºo]?\s*(\d+)\s*/\s*(\d{2,4})", re.IGNORECASE)
RE_APERTURA = re.compile(
    r"apertura se realizar[aá]\s+el\s+d[ií]a\s*(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})(?:\s*a las\s*(\d{1,2}):(\d{2}))?",
    re.IGNORECASE,
)
RE_OBJETO = re.compile(
    r"para\s+(?:la\s+)?(?:contrataci[oó]n|adquisici[oó]n)\s+(?:del?\s+)?(.*?)(?:,\s*(?:requerido|solicitad[oa]|por el per[ií]odo)|\.\s)",
    re.IGNORECASE | re.DOTALL,
)


def _normalizar_anio(anio_texto: str) -> int:
    anio = int(anio_texto)
    return anio if anio > 100 else 2000 + anio


def _listar_pdfs(anio: int) -> list[str]:
    subseccion = SUBSECCION_POR_ANIO.get(anio)
    if not subseccion:
        return []
    resp = requests.post(
        AJAX_URL, json={"subseccion": subseccion}, headers=HEADERS, timeout=30, verify=False,
    )
    if resp.status_code != 200:
        return []
    html = resp.json().get("d") or ""
    soup = BeautifulSoup(html, "html.parser")
    return [a["href"] for a in soup.find_all("a", href=True) if a["href"].lower().endswith(".pdf")]


def _extraer_texto(url: str) -> str:
    resp = requests.get(url, headers=HEADERS, timeout=60, verify=False)
    resp.raise_for_status()
    texto = []
    with pdfplumber.open(io.BytesIO(resp.content)) as pdf:
        for pagina in pdf.pages:
            t = pagina.extract_text()
            if t:
                texto.append(t)
    return re.sub(r"\s+", " ", "\n".join(texto))


def fetch(anio: int | None = None, max_pdfs: int = 4) -> list[dict]:
    anio = anio or datetime.now().year
    urls = _listar_pdfs(anio)[-max_pdfs:]  # los mas recientes (la lista viene cronologica ascendente)

    rows = {}
    for url in urls:
        try:
            texto = _extraer_texto(url)
        except Exception as e:
            print(f"  ! error en {url}: {e}")
            continue

        for m in RE_LIC.finditer(texto):
            tipo, numero, anio_txt = m.groups()
            anio_lic = _normalizar_anio(anio_txt)
            numero_proceso = f"{numero}/{anio_lic}"

            ventana = texto[m.end(): m.end() + 500]

            fecha_apertura = None
            m_ap = RE_APERTURA.search(ventana)
            if m_ap:
                dia, mes_nombre, anio_ap, hora, minuto = m_ap.groups()
                mes_num = MESES.get(mes_nombre.lower())
                if mes_num:
                    try:
                        fecha_apertura = datetime(
                            int(anio_ap), mes_num, int(dia), int(hora or 0), int(minuto or 0)
                        ).isoformat()
                    except ValueError:
                        pass

            m_obj = RE_OBJETO.search(ventana)
            objeto = m_obj.group(1).strip(' "“”.,')[:300] if m_obj else None

            estado = "Adjudicada" if "adjudicar" in ventana.lower() or "aprobar la contrataci" in texto[max(0, m.start() - 60):m.start()].lower() else "Publicado"

            row = {
                "fuente": "muni_lomas_de_zamora",
                "numero_proceso": numero_proceso,
                "titulo": f"Licitación {tipo.title()} {numero_proceso} — {objeto}"[:250] if objeto else f"Licitación {tipo.title()} {numero_proceso}",
                "descripcion": objeto,
                "organismo": "Municipalidad de Lomas de Zamora",
                "jurisdiccion": "Municipio de Lomas de Zamora (GBA sur)",
                "tipo_procedimiento": f"Licitación {tipo.title()}",
                "fecha_publicacion": None,
                "fecha_apertura": fecha_apertura,
                "monto_estimado": None,
                "moneda": "ARS",
                "estado": estado,
                "proveedor_adjudicado": None,
                "monto_adjudicado": None,
                "url": url,
            }
            # si ya existia (ej. primero "llamado" y despues "adjudicacion"),
            # nos quedamos con el que tenga fecha de apertura real, o el mas nuevo
            existente = rows.get(numero_proceso)
            if not existente or (fecha_apertura and not existente.get("fecha_apertura")):
                rows[numero_proceso] = row

    return list(rows.values())


if __name__ == "__main__":
    data = fetch()
    print(f"{len(data)} licitaciones normalizadas")
    for row in data[:5]:
        print(row)
