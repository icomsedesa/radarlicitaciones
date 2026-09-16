"""SIBOM -- Sistema de Boletines Oficiales Municipales (Provincia de Buenos Aires).

Plataforma compartida por decenas de municipios bonaerenses para publicar su
Boletin Oficial (sibom.slyt.gba.gob.ar). No tiene filtro nativo por
categoria "licitacion" -- hay que recorrer los boletines de un municipio y
buscar, entre TODOS los decretos/resoluciones/ordenanzas, los que mencionan
"licitacion" (mezclado con designaciones, subsidios, etc).

Cada boletin (/bulletins/{id}) trae el TEXTO COMPLETO de todos sus actos en
una sola pagina (no hace falta visitar /bulletins/{id}/contents/{content_id}
por separado, salvo para el link permalink de cada uno).

Reusable por municipio: solo cambia el city_id. IDs de ciudad conocidos:
  - Campana: 18

Limitaciones conocidas: no siempre hay fecha de apertura en el texto del
decreto (a veces esta en el pliego adjunto, no en el cuerpo) -- se completa
cuando el patron de texto la trae, si no queda en None.
"""
import re
from datetime import datetime

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://sibom.slyt.gba.gob.ar"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; RadarLicitaciones/0.1; uso interno)"}

RE_LICITACION = re.compile(
    r"Licitaci[oó]n\s+(P[uú]blica|Privada|Abreviada)\s*N[°ºo]?\s*(\d+)\s*/\s*(\d{2,4})",
    re.IGNORECASE,
)
RE_HEADER = re.compile(
    r"^(Decreto|Resoluci[oó]n|Ordenanza)\s*N[°ºo]?\s*([\d./]+)\s+([A-ZÁÉÍÓÚÑa-záéíóúñ\s]+?),\s*(\d{2}/\d{2}/\d{4})"
    r"\s*(?:Expediente\s+Municipal\s+N[°ºo]?\s*([\d.\-/ ]+?))?\s+(.*?)\s+Visto\b",
    re.IGNORECASE | re.DOTALL,
)


def _listar_boletines(city_id: int, max_boletines: int) -> list[tuple[int, str]]:
    """Devuelve [(bulletin_id, fecha_publicacion_str), ...] mas recientes primero."""
    boletines = []
    pagina = 1
    while len(boletines) < max_boletines and pagina <= 5:
        resp = requests.get(f"{BASE_URL}/cities/{city_id}", params={"page": pagina}, headers=HEADERS, timeout=30)
        if resp.status_code != 200:
            break
        ids = re.findall(r'action="/bulletins/(\d+)"', resp.text)
        if not ids:
            break
        soup = BeautifulSoup(resp.text, "html.parser")
        fechas = [p.get_text(strip=True) for p in soup.select(".bulletin-date")]
        for bid, fecha in zip(ids, fechas):
            boletines.append((int(bid), fecha))
        pagina += 1
    return boletines[:max_boletines]


def _normalizar_anio(anio_texto: str) -> int:
    anio = int(anio_texto)
    return anio if anio > 100 else 2000 + anio


def _parse_bloque(box, bulletin_id: int) -> dict | None:
    texto = box.get_text(" ", strip=True)
    if "licitaci" not in texto.lower():
        return None

    m_lic = RE_LICITACION.search(texto)
    if not m_lic:
        return None
    tipo, numero, anio_texto = m_lic.groups()
    anio = _normalizar_anio(anio_texto)
    numero_proceso = f"{numero}/{anio}"

    m_header = RE_HEADER.match(texto)
    fecha_decreto = None
    expediente = None
    objeto = texto
    if m_header:
        _, _, ciudad, fecha_str, expediente, objeto = m_header.groups()
        try:
            fecha_decreto = datetime.strptime(fecha_str, "%d/%m/%Y").isoformat()
        except ValueError:
            fecha_decreto = None
        objeto = objeto.strip()

    estado = None
    tl = texto.lower()
    if "adjudicaci" in tl:
        estado = "Adjudicada"
    elif "llamado" in tl or "llámase" in tl:
        estado = "Publicado"

    link = box.find_parent("a", class_="content-link") or box.find("a", class_="content-link")
    href = link["href"] if link and link.get("href") else f"/bulletins/{bulletin_id}"

    return {
        "fuente": None,  # lo completa el caller (depende del municipio)
        "numero_proceso": numero_proceso,
        "titulo": f"Licitación {tipo.capitalize()} {numero_proceso} — {objeto}"[:250],
        "descripcion": objeto,
        "organismo": None,  # lo completa el caller
        "jurisdiccion": None,  # lo completa el caller
        "tipo_procedimiento": f"Licitación {tipo.capitalize()}",
        "fecha_publicacion": fecha_decreto,
        "fecha_apertura": None,  # no siempre esta en el cuerpo del decreto
        "monto_estimado": None,
        "moneda": "ARS",
        "estado": estado,
        "proveedor_adjudicado": None,
        "monto_adjudicado": None,
        "url": f"{BASE_URL}{href}",
        "_expediente": expediente,
    }


def fetch(city_id: int, fuente: str, organismo: str, jurisdiccion: str, max_boletines: int = 20) -> list[dict]:
    boletines = _listar_boletines(city_id, max_boletines)
    rows: dict[str, dict] = {}

    for bulletin_id, _fecha_pub in boletines:
        resp = requests.get(f"{BASE_URL}/bulletins/{bulletin_id}", headers=HEADERS, timeout=30)
        if resp.status_code != 200:
            continue
        soup = BeautifulSoup(resp.text, "html.parser")
        for box in soup.select(".white-box"):
            row = _parse_bloque(box, bulletin_id)
            if not row:
                continue
            row["fuente"] = fuente
            row["organismo"] = organismo
            row["jurisdiccion"] = jurisdiccion
            row.pop("_expediente", None)
            # nos quedamos con la mencion mas reciente (boletines mas nuevos
            # primero) de cada numero de licitacion -- ej. adjudicacion pisa
            # al llamado inicial
            if row["numero_proceso"] not in rows:
                rows[row["numero_proceso"]] = row

    return list(rows.values())


if __name__ == "__main__":
    import sys

    city_id = int(sys.argv[1]) if len(sys.argv) > 1 else 18  # Campana
    data = fetch(city_id, fuente="muni_campana", organismo="Municipalidad de Campana", jurisdiccion="Municipio de Campana (GBA)")
    print(f"{len(data)} licitaciones normalizadas")
    for row in data[:5]:
        print(row)
