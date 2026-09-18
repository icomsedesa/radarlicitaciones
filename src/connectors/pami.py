"""PAMI (INSSJP) -- Nivel Central.

Fuente: prestadores.pami.org.ar, HTML estatico clasico (paginas .php sin
JS), sin login. Dos secciones usadas:

  1. Listado de licitaciones vigentes (`result.php?c=7-1-1-1`): cada
     entrada trae tipo+numero, objeto, expediente, destino, fecha de
     apertura y un link directo al PDF del pliego.
  2. **Actas de Apertura** (`result.php?c=7-1-3&par=1`): PUBLICA, sin
     login, el detalle de TODAS las ofertas recibidas por proceso (razon
     social, CUIT, fecha de recepcion, precio cotizado) -- exactamente el
     dato de "comparativas" que en COMPR.AR/BAC solo se ve con cuenta de
     proveedor logueada. El PDF del acta tiene URL predecible a partir del
     numero de expediente: `compraselectronicas.pami.org.ar/uploads_actas/
     AA-{expediente}.pdf`.

Alcance actual: solo "Nivel Central" (par=1). PAMI tambien publica compras
de sus Unidades de Gestion Local (UGL) -- no relevado todavia, ver
`par=2`/`par=3` u otros valores en el menu "Agencias / UGL".
"""
import io
import re

import pdfplumber
import requests

LISTADO_URL = "https://prestadores.pami.org.ar/result.php?c=7-1-1-1"
ACTAS_URL = "https://prestadores.pami.org.ar/result.php?c=7-1-3&par=1"
ACTA_PDF_BASE = "https://compraselectronicas.pami.org.ar/uploads_actas/AA-{expediente}.pdf"

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; RadarLicitaciones/0.1; uso interno)"}

RE_ENTRADA = re.compile(
    r'<span class="bordeaux">(Compulsa Abreviada|Licitaci[oó]n P[uú]blica|Licitaci[oó]n Privada)\s*N[°º]\s*(\d+)</strong></span>'
)
RE_OBJETO = re.compile(r'<td class="texto"><p>(.*?)</p></td>', re.DOTALL)
RE_EXPEDIENTE = re.compile(r'Expediente:</span>\s*<span class="negro">(.*?)</span>')
RE_DESTINO = re.compile(r'Destino:</span>\s*<span class="negro">(.*?)</span>')
RE_FECHA = re.compile(r'Fecha Apertura:</span>\s*<span class="negro">(\d{1,2})/(\d{1,2})/(\d{4}),\s*(\d{1,2}):(\d{2}):(\d{2})')
RE_PDF = re.compile(r'href="(http[^"]+\.pdf)"')
RE_TAG = re.compile(r"<[^>]+>")


def _limpiar_html(texto: str) -> str:
    return RE_TAG.sub(" ", texto).replace("&nbsp;", " ")


def _parse_fecha(m) -> str | None:
    from datetime import datetime
    dia, mes, anio, hora, minuto, segundo = (int(x) for x in m.groups())
    try:
        return datetime(anio, mes, dia, hora, minuto, segundo).isoformat()
    except ValueError:
        return None


def fetch() -> list[dict]:
    resp = requests.get(LISTADO_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    html = resp.text

    partes = RE_ENTRADA.split(html)
    # partes[0] es lo previo a la primera entrada; despues se repite en
    # grupos de 3: tipo, numero, contenido-hasta-la-proxima-entrada.
    rows = []
    for i in range(1, len(partes) - 2, 3):
        tipo, numero, contenido = partes[i], partes[i + 1], partes[i + 2]
        numero_proceso = f"{numero}/2026"

        m_obj = RE_OBJETO.search(contenido)
        objeto = re.sub(r"\s+", " ", _limpiar_html(m_obj.group(1))).strip() if m_obj else None

        m_exp = RE_EXPEDIENTE.search(contenido)
        expediente = _limpiar_html(m_exp.group(1)).strip() if m_exp else None

        m_dest = RE_DESTINO.search(contenido)
        destino = _limpiar_html(m_dest.group(1)).strip() if m_dest else "Nivel Central"

        m_fecha = RE_FECHA.search(contenido)
        fecha_apertura = _parse_fecha(m_fecha) if m_fecha else None

        m_pdf = RE_PDF.search(contenido)
        url = m_pdf.group(1) if m_pdf else LISTADO_URL

        rows.append(
            {
                "fuente": "pami",
                "numero_proceso": numero_proceso,
                "titulo": f"{tipo} {numero_proceso} — {objeto}"[:250] if objeto else f"{tipo} {numero_proceso}",
                "descripcion": objeto,
                "organismo": f"PAMI — {destino}",
                "jurisdiccion": "PAMI (Nación)",
                "tipo_procedimiento": tipo,
                "fecha_publicacion": None,
                "fecha_apertura": fecha_apertura,
                "monto_estimado": None,
                "moneda": "ARS",
                "estado": None,
                "proveedor_adjudicado": None,
                "monto_adjudicado": None,
                "url": url,
                "expediente": expediente,
            }
        )
    return rows


RE_ACTA_ENTRADA = re.compile(
    r"<td[^>]*><p>(\d{1,2}/\d{1,2}/\d{4})</p></td>\s*"
    r"<td[^>]*><p>(\d{1,2}:\d{2}:\d{2})</p></td>\s*"
    r"<td[^>]*><p>(.*?)</p></td>\s*"
    r"<td[^>]*><p>(\d+/\d{4})</p></td>\s*"
    r"<td[^>]*>\s*<p>(.*?)</p></td>\s*"
    r'<td[^>]*>\s*<p><a href="([^"]+)"',
    re.DOTALL,
)


def listar_actas() -> list[dict]:
    """Lista (numero_proceso, tipo, fecha_apertura, objeto, url_acta) para
    las aperturas ya realizadas en Nivel Central. Este listado es mas
    amplio (historico) que `fetch()` (solo lo vigente hoy) -- por eso trae
    tipo/fecha/objeto propios: permite crear la licitacion en la base si
    todavia no existia, antes de cargarle las ofertas."""
    resp = requests.get(ACTAS_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    html = resp.text
    resultado = []
    for m in RE_ACTA_ENTRADA.finditer(html):
        fecha, hora, tipo, numero, objeto, url_pdf = m.groups()
        dia, mes, anio = (int(x) for x in fecha.split("/"))
        h, mi = (int(x) for x in hora.split(":")[:2])
        from datetime import datetime
        try:
            fecha_apertura = datetime(anio, mes, dia, h, mi).isoformat()
        except ValueError:
            fecha_apertura = None
        resultado.append({
            "numero_proceso": numero,
            "tipo": tipo,
            "fecha_apertura": fecha_apertura,
            "objeto": _limpiar_html(objeto).strip(),
            "url_acta": url_pdf if url_pdf.startswith("http") else "https://compraselectronicas.pami.org.ar" + url_pdf,
        })
    return resultado


RE_CUIT = re.compile(r"^\d{2}-\d{8}-\d$")


def _parse_monto(texto: str):
    texto = (texto or "").strip().replace(".", "").replace(",", ".")
    try:
        return float(texto)
    except ValueError:
        return None


def _extraer_ofertas_de_tablas(tablas: list[list[list]]) -> list[dict]:
    """El PDF del Acta de Apertura trae una tabla real (con lineas) para las
    ofertas -- extract_tables() la reconstruye con columnas limpias, a
    diferencia de extract_text() que mezcla el encabezado (varias lineas,
    columnas de distinto ancho) con la primera fila de datos. Se detecta la
    tabla de ofertas por su encabezado ("RAZON SOCIAL" + "CUIT") y se
    procesan las filas siguientes hasta la primera que no tenga un CUIT
    valido en la segunda columna."""
    for tabla in tablas:
        if not tabla:
            continue
        header = " ".join(c or "" for c in tabla[0]).upper()
        if "RAZ" not in header or "CUIT" not in header:
            continue
        ofertas = []
        for fila in tabla[1:]:
            if len(fila) < 5:
                continue
            proveedor = re.sub(r"\s+", " ", (fila[0] or "")).strip()
            cuit = (fila[1] or "").strip()
            if not RE_CUIT.match(cuit):
                continue
            fecha_oferta = (fila[2] or "").replace("\n", " ").strip()
            monto = _parse_monto(fila[4])
            ofertas.append({
                "proveedor": proveedor,
                "cuit": cuit,
                "monto": monto,
                "moneda": "ARS",
                "fecha_oferta": fecha_oferta,
            })
        if ofertas:
            ganadora = min(ofertas, key=lambda o: o["monto"] if o["monto"] is not None else float("inf"))
            ganadora["es_ganadora"] = True
        return ofertas
    return []


def fetch_ofertas_para(numero_proceso: str, url_acta: str) -> list[dict]:
    resp = requests.get(url_acta, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    with pdfplumber.open(io.BytesIO(resp.content)) as pdf:
        tablas = [t for p in pdf.pages for t in p.extract_tables()]
    return _extraer_ofertas_de_tablas(tablas)


def fetch_todas_las_ofertas(max_actas: int | None = None) -> list[dict]:
    """Recorre todas las Actas de Apertura publicadas (historico, mas
    amplio que `fetch()` que solo trae lo vigente hoy) y devuelve, por cada
    una con ofertas, un dict con los datos de la licitacion (para poder
    crearla si no existia todavia en la base) + su lista de 'ofertas'."""
    actas = listar_actas()
    if max_actas:
        actas = actas[:max_actas]
    resultado = []
    for acta in actas:
        try:
            ofertas = fetch_ofertas_para(acta["numero_proceso"], acta["url_acta"])
        except Exception as e:
            print(f"  ! error en acta {acta['numero_proceso']}: {e}")
            continue
        if not ofertas:
            continue
        resultado.append({
            "fuente": "pami",
            "numero_proceso": acta["numero_proceso"],
            "titulo": f"{acta['tipo']} {acta['numero_proceso']} — {acta['objeto']}"[:250] if acta["objeto"] else f"{acta['tipo']} {acta['numero_proceso']}",
            "descripcion": acta["objeto"],
            "organismo": "PAMI — Nivel Central",
            "jurisdiccion": "PAMI (Nación)",
            "tipo_procedimiento": acta["tipo"],
            "fecha_publicacion": None,
            "fecha_apertura": acta["fecha_apertura"],
            "monto_estimado": None,
            "moneda": "ARS",
            "estado": None,
            "proveedor_adjudicado": None,
            "monto_adjudicado": None,
            "url": acta["url_acta"],
            "ofertas": ofertas,
        })
    return resultado


if __name__ == "__main__":
    data = fetch()
    print(f"{len(data)} licitaciones normalizadas")
    for row in data[:5]:
        print(row)

    print("\n--- actas de apertura ---")
    actas = listar_actas()
    print(f"{len(actas)} actas listadas")
    for a in actas[:3]:
        print(a)
        ofertas = fetch_ofertas_para(a["numero_proceso"], a["url_acta"])
        print(f"  {len(ofertas)} ofertas:", ofertas)
