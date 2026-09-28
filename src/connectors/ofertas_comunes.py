"""Piezas compartidas entre los conectores de comparativas autenticadas
(bac_ofertas.py, comprar_ar_ofertas.py) -- ambos portales resultaron usar
el mismo software de "Cuadro comparativo de ofertas" por debajo (misma
URL EVALUACIONOFERTA/VerCuadroComparativo.aspx, mismo formato "NOMBRE -
CUIT" + "Total: ARS monto" -- confirmado contra capturas reales de los
dos, 28-sep-2026)."""
from pathlib import Path

import re

# El monto aparece en dos ordenes distintos segun el portal -- BAC:
# "Total: ARS 18.208.800,00"; COMPR.AR: "34.797.037,00 ARS" (sin la
# etiqueta "Total:"). El nombre del oferente tambien varia de mayusculas
# fijas (BAC) a Title Case (COMPR.AR), de ahi el rango A-Za-z.
RE_OFERTA = re.compile(
    r"([A-Za-zÁÉÍÓÚÑáéíóúñ0-9.,&'()/ ]{3,90}?)\s*-\s*(\d{11})\s*\n?\s*"
    r"(?:Total:\s*ARS\s*([\d.]+,\d{2})|([\d.]+,\d{2})\s*ARS)"
)

SALIDA_DEBUG = Path(__file__).resolve().parent.parent.parent / "data" / "explorar"


def limpiar(texto: str) -> str:
    return re.sub(r"\s+", " ", texto).strip()


def volcar_debug(page, nombre: str):
    SALIDA_DEBUG.mkdir(parents=True, exist_ok=True)
    try:
        page.screenshot(path=str(SALIDA_DEBUG / f"{nombre}.png"), full_page=True)
        (SALIDA_DEBUG / f"{nombre}.html").write_text(page.content(), encoding="utf-8")
        print(f"  (debug) guardado {SALIDA_DEBUG / nombre}.png/.html")
    except Exception as e:
        print(f"  (debug) no se pudo volcar '{nombre}': {e}")


def extraer_cuadro(page) -> list[dict]:
    """Parsea la pantalla "Cuadro comparativo de ofertas" (BAC o
    COMPR.AR) y devuelve una lista de dicts proveedor/cuit/monto/moneda/
    fecha_oferta/es_ganadora -- mismo formato que espera db.set_ofertas."""
    contenido = page.inner_text("body")
    ofertas = []
    for m in RE_OFERTA.finditer(contenido):
        nombre, cuit, monto_bac, monto_comprar = m.groups()
        monto_txt = monto_bac or monto_comprar
        monto = float(monto_txt.replace(".", "").replace(",", "."))
        ofertas.append({
            "proveedor": nombre.strip(" -"),
            "cuit": cuit,
            "monto": monto,
            "moneda": "ARS",
            "fecha_oferta": None,
            "es_ganadora": False,
        })
    if ofertas:
        # marca la de menor monto como referencia -- igual que en el resto
        # de la app, NO implica que sea la adjudicataria real (eso depende
        # tambien de criterios tecnicos).
        minimo = min(o["monto"] for o in ofertas)
        for o in ofertas:
            o["es_ganadora"] = o["monto"] == minimo
    return ofertas
