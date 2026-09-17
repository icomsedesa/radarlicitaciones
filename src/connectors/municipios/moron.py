"""Municipio de Moron (GBA oeste).

Fuente: portal RAFAM (software de gestion financiera municipal que
comparten varios municipios bonaerenses) --
https://apps.moron.gob.ar/ext/rafam_portal/licitaciones/licitaciones.php?tipo=publica
Tabla HTML server-side pura (sin JS), con TODO el historico 2021-2026 en
una sola pagina. Codificacion ISO-8859-1 (Latin-1), no UTF-8.

Limitacion conocida: algunas filas traen el numero de licitacion vacio en
origen (columna "Numero" = "/2021", sin el numero antes de la barra) -- se
descartan porque no se puede armar un numero_proceso confiable.
"""
import re
from datetime import datetime

import requests
from bs4 import BeautifulSoup

URL = "https://apps.moron.gob.ar/ext/rafam_portal/licitaciones/licitaciones.php?tipo=publica"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; RadarLicitaciones/0.1; uso interno)"}

RE_NUMERO = re.compile(r"^\s*(\d+)\s*/\s*(\d{4})\s*$")
RE_VISITA_APERTURA = re.compile(
    r"(?:APERTURA|VISITA DE OBRA)[:\s]*[EL\s]*(?:DIA)?\s*(\d{1,2})\s*(?:DE)?\s*(\w+)\s*(?:DEL?)?\s*(\d{4})",
    re.IGNORECASE,
)
MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}


def _parse_monto(texto: str):
    texto = texto.strip()
    if not texto:
        return None
    texto = re.sub(r"[^\d.,]", "", texto)
    if not texto:
        return None
    # el origen a veces usa "." tanto de miles como de decimales (ej.
    # "373.931.558.64") en vez del formato AR normal con coma decimal --
    # si el ultimo grupo separado por "." tiene 2 digitos, es el decimal.
    partes = texto.split(".")
    if "," not in texto and len(partes) > 1 and len(partes[-1]) == 2:
        texto = "".join(partes[:-1]) + "." + partes[-1]
    else:
        texto = texto.replace(".", "").replace(",", ".")
    try:
        return float(texto)
    except ValueError:
        return None


def _buscar_fecha(texto: str):
    m = RE_VISITA_APERTURA.search(texto)
    if not m:
        return None
    dia, mes_nombre, anio = m.groups()
    mes_num = MESES.get(mes_nombre.lower())
    if not mes_num:
        return None
    try:
        return datetime(int(anio), mes_num, int(dia)).isoformat()
    except ValueError:
        return None


def fetch() -> list[dict]:
    resp = requests.get(URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "iso-8859-1"
    soup = BeautifulSoup(resp.text, "html.parser")
    tables = soup.find_all("table")
    if not tables:
        return []
    filas = tables[-1].find_all("tr")[1:]  # saltear encabezado

    rows = {}
    for tr in filas:
        tds = tr.find_all("td")
        if len(tds) < 5:
            continue
        numero_col = tds[0].get_text(" ", strip=True)
        descripcion = tds[2].get_text(" ", strip=True)
        expediente = tds[3].get_text(" ", strip=True)
        presupuesto = tds[4].get_text(" ", strip=True)

        m = RE_NUMERO.match(numero_col)
        if not m:
            continue  # fila sin numero real (dato faltante en origen)
        numero, anio = m.groups()
        numero_proceso = f"{numero}/{anio}"

        rows[numero_proceso] = {
            "fuente": "muni_moron",
            "numero_proceso": numero_proceso,
            "titulo": f"Licitación Pública {numero_proceso} — {descripcion}"[:250],
            "descripcion": descripcion,
            "organismo": "Municipalidad de Morón",
            "jurisdiccion": "Municipio de Morón (GBA oeste)",
            "tipo_procedimiento": "Licitación Pública",
            "fecha_publicacion": None,
            "fecha_apertura": _buscar_fecha(descripcion),
            "monto_estimado": _parse_monto(presupuesto),
            "moneda": "ARS",
            "estado": None,
            "proveedor_adjudicado": None,
            "monto_adjudicado": None,
            "url": f"https://apps.moron.gob.ar/ext/rafam_portal/licitaciones/licitaciones.php?tipo=publica&anio={anio}&nro={numero}&clase=1",
            "_expediente": expediente,
        }
    for r in rows.values():
        r.pop("_expediente", None)
    return list(rows.values())


if __name__ == "__main__":
    data = fetch()
    print(f"{len(data)} licitaciones normalizadas")
    for row in data[:5]:
        print(row)
