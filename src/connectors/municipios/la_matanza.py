"""Municipio de La Matanza (el mas poblado de la provincia).

Fuente: Boletin Municipal mensual en PDF (texto real, no escaneado) --
https://www.lamatanza.gov.ar/upload/pdf/gobierno/boletin/{anio}/Boletin%20Oficial%20-%20{Mes}%20{anio}.pdf

No hay tabla ni sistema de compras online (la pagina "proveedores" del
sitio tiene un PDF muerto de 2017). El Boletin mezcla TODOS los decretos
del mes (designaciones, licitaciones, etc.) pero el patron de redaccion
de los llamados a licitacion es muy regular y se puede extraer con regex:

    "ARTICULO 1°: Llamase a Licitacion Publica N°75/2026, para el dia 26
    de Agosto de 2026, a las 10:00 horas... referente a ... conforme
    especificaciones ... Presupuesto Oficial: $ 1.798.053.400.-"
"""
import re
from datetime import datetime
from pathlib import Path

import pdfplumber
import requests

BASE_URL = "https://www.lamatanza.gov.ar/upload/pdf/gobierno/boletin"
DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "muni_la_matanza"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; RadarLicitaciones/0.1; uso interno)"}

MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}
MESES_NOMBRE = {v: k.capitalize() for k, v in MESES.items()}

PATRON = re.compile(
    r"Ll[aá]mase a Licitaci[oó]n P[uú]blica\s*N[°º]\s*(\d+)\s*/\s*(\d{4}),"
    r"\s*para el d[ií]a\s*(\d{1,2})\s*de\s*(\w+)\s*de\s*(\d{4}),"
    r"\s*a las\s*(\d{1,2}):(\d{2})\s*horas.*?referente a\s*(?:la\s+)?(.*?)\s*,?\s*conforme especificaciones",
    re.IGNORECASE | re.DOTALL,
)
PATRON_MONTO = re.compile(r"Presupuesto Oficial:\s*\$\s*([\d.,]+)")


def _mes_actual_y_anteriores(n=3):
    hoy = datetime.now()
    meses = []
    anio, mes = hoy.year, hoy.month
    for _ in range(n):
        meses.append((anio, mes))
        mes -= 1
        if mes == 0:
            mes, anio = 12, anio - 1
    return meses


def _descargar_boletin(anio: int, mes: int) -> Path | None:
    nombre_mes = MESES_NOMBRE[mes]
    dest = DATA_DIR / f"{anio}-{mes:02d}.pdf"
    if dest.exists():
        return dest
    url = f"{BASE_URL}/{anio}/Boletin%20Oficial%20-%20{nombre_mes}%20{anio}.pdf"
    resp = requests.get(url, headers=HEADERS, timeout=60)
    if resp.status_code != 200:
        return None
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(resp.content)
    return dest


def _extraer_texto(pdf_path: Path) -> str:
    texto = []
    with pdfplumber.open(pdf_path) as pdf:
        for pagina in pdf.pages:
            t = pagina.extract_text()
            if t:
                texto.append(t)
    return "\n".join(texto)


def _parse_monto(texto_monto: str):
    if not texto_monto:
        return None
    s = texto_monto.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def fetch(meses_atras: int = 3) -> list[dict]:
    rows = {}
    for anio, mes in _mes_actual_y_anteriores(meses_atras):
        pdf_path = _descargar_boletin(anio, mes)
        if not pdf_path:
            continue
        texto = _extraer_texto(pdf_path)
        matches = list(PATRON.finditer(texto))
        for idx, m in enumerate(matches):
            numero, anio_lic, dia, mes_nombre, anio_apertura, hora, minuto, objeto = m.groups()
            mes_num = MESES.get(mes_nombre.lower())
            if not mes_num:
                continue
            try:
                fecha_apertura = datetime(int(anio_apertura), mes_num, int(dia), int(hora), int(minuto)).isoformat()
            except ValueError:
                fecha_apertura = None

            limite = matches[idx + 1].start() if idx + 1 < len(matches) else m.end() + 3000
            monto_m = PATRON_MONTO.search(texto, m.end(), limite)
            objeto = re.sub(r"\s+", " ", objeto).strip(' "“”.,')

            numero_proceso = f"{numero}/{anio_lic}"
            rows[numero_proceso] = {
                "fuente": "muni_la_matanza",
                "numero_proceso": numero_proceso,
                "titulo": f"Licitación Pública {numero_proceso} — {objeto}"[:250],
                "descripcion": objeto,
                "organismo": "Municipalidad de La Matanza",
                "jurisdiccion": "Municipio de La Matanza (GBA)",
                "tipo_procedimiento": "Licitación Pública",
                "fecha_publicacion": None,
                "fecha_apertura": fecha_apertura,
                "monto_estimado": _parse_monto(monto_m.group(1)) if monto_m else None,
                "moneda": "ARS",
                "estado": None,
                "proveedor_adjudicado": None,
                "monto_adjudicado": None,
                "url": f"{BASE_URL}/{anio}/Boletin%20Oficial%20-%20{MESES_NOMBRE[mes]}%20{anio}.pdf",
            }
    return list(rows.values())


if __name__ == "__main__":
    data = fetch()
    print(f"{len(data)} licitaciones normalizadas")
    for row in data[:5]:
        print(row)
