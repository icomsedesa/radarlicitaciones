"""Municipio de Moreno (GBA oeste).

Fuente: API JSON abierta de noticias (moreno.gob.ar/services/noticias/
list.php), sin autenticacion, paginable por list_last_id. Cada licitacion
importante tiene su propia noticia (noticia-detalle.php?id=N) con texto
muy regular y campos etiquetados: MOTIVO, EXPEDIENTE, PRESUPUESTO OFICIAL,
APERTURA DE OFERTAS.

El sitio tiene la cadena de certificados SSL incompleta (verify=False;
fuente publica de solo lectura, sin dato sensible en juego).
"""
import re
import warnings
from datetime import datetime

import requests
import urllib3
from bs4 import BeautifulSoup

warnings.simplefilter("ignore", urllib3.exceptions.InsecureRequestWarning)

LIST_URL = "https://moreno.gob.ar/services/noticias/list.php"
DETALLE_URL = "https://moreno.gob.ar/noticia-detalle.php"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; RadarLicitaciones/0.1; uso interno)"}

MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}

RE_NUMERO = re.compile(r"LICITACI[OÓ]N\s+(P[UÚ]BLICA|PRIVADA)\s*N[°ºo]?\s*(\d+)\s*/\s*(\d{4})", re.IGNORECASE)
RE_MOTIVO = re.compile(r"MOTIVO\s*:\s*[«\"“]?(.*?)[»\"”]?\s*EXPEDIENTE", re.IGNORECASE | re.DOTALL)
RE_EXPEDIENTE = re.compile(r"EXPEDIENTE:\s*([\d\-A-Z]+)", re.IGNORECASE)
RE_PRESUPUESTO = re.compile(r"PRESUPUESTO OFICIAL\s*:.*?\(\$\s*([\d.,]+)\)", re.IGNORECASE | re.DOTALL)
RE_APERTURA = re.compile(
    r"APERTURA DE OFERTAS\s*:.*?(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})\s+a las\s*(\d{1,2}):(\d{2})",
    re.IGNORECASE | re.DOTALL,
)


def _parse_monto(texto: str):
    try:
        return float(texto.replace(".", "").replace(",", "."))
    except ValueError:
        return None


def _listar_noticias(paginas: int = 3) -> list[dict]:
    noticias = []
    last_id = 0
    for _ in range(paginas):
        resp = requests.get(
            LIST_URL, params={"list_last_id": last_id, "busqueda": "", "data_custom": -1},
            headers=HEADERS, timeout=30, verify=False,
        )
        if resp.status_code != 200:
            break
        data = resp.json()
        items = data[0] if data else []
        if not items:
            break
        noticias.extend(items)
        last_id = items[-1]["noticia_id"]
    return noticias


def _parse_detalle(noticia_id: int) -> dict | None:
    resp = requests.get(DETALLE_URL, params={"id": noticia_id}, headers=HEADERS, timeout=30, verify=False)
    if resp.status_code != 200:
        return None
    soup = BeautifulSoup(resp.text, "html.parser")
    body = soup.find("body")
    texto = re.sub(r"\s+", " ", body.get_text(" ", strip=True)) if body else ""

    m_num = RE_NUMERO.search(texto)
    if not m_num:
        return None
    tipo, numero, anio = m_num.groups()
    numero_proceso = f"{numero}/{anio}"

    m_motivo = RE_MOTIVO.search(texto)
    objeto = m_motivo.group(1).strip(' "«»“”.,') if m_motivo else None

    fecha_apertura = None
    m_ap = RE_APERTURA.search(texto)
    if m_ap:
        dia, mes_nombre, anio_ap, hora, minuto = m_ap.groups()
        mes_num = MESES.get(mes_nombre.lower())
        if mes_num:
            try:
                fecha_apertura = datetime(int(anio_ap), mes_num, int(dia), int(hora), int(minuto)).isoformat()
            except ValueError:
                pass

    m_presupuesto = RE_PRESUPUESTO.search(texto)
    m_expediente = RE_EXPEDIENTE.search(texto)

    return {
        "fuente": "muni_moreno",
        "numero_proceso": numero_proceso,
        "titulo": f"Licitación {tipo.title()} {numero_proceso} — {objeto}"[:250] if objeto else f"Licitación {tipo.title()} {numero_proceso}",
        "descripcion": objeto,
        "organismo": "Municipalidad de Moreno",
        "jurisdiccion": "Municipio de Moreno (GBA oeste)",
        "tipo_procedimiento": f"Licitación {tipo.title()}",
        "fecha_publicacion": None,
        "fecha_apertura": fecha_apertura,
        "monto_estimado": _parse_monto(m_presupuesto.group(1)) if m_presupuesto else None,
        "moneda": "ARS",
        "estado": None,
        "proveedor_adjudicado": None,
        "monto_adjudicado": None,
        "url": f"{DETALLE_URL}?id={noticia_id}",
    }


def fetch(paginas: int = 3) -> list[dict]:
    noticias = _listar_noticias(paginas)
    candidatas = [n for n in noticias if "LICITACI" in n["noticia_titulo"].upper()]

    rows = {}
    for n in candidatas:
        try:
            row = _parse_detalle(n["noticia_id"])
        except Exception as e:
            print(f"  ! error en noticia {n['noticia_id']}: {e}")
            continue
        if row:
            rows[row["numero_proceso"]] = row
    return list(rows.values())


if __name__ == "__main__":
    data = fetch()
    print(f"{len(data)} licitaciones normalizadas")
    for row in data[:5]:
        print(row)
