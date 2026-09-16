"""Conector Buenos Aires Compras - BAC (CABA).

Fuente: OCDS 1.1 (datos.buenosaires.gob.ar), CC-BY-2.5-AR.

Nota: el recurso "Buenos Aires Compras" (bac_anual.json) que parece el mas
comodo esta MAL ETIQUETADO -- pese a actualizarse a diario, sus ~23k
releases son TODOS de 2022 (bug/desfasaje del lado de CABA, verificado
16-sep-2026: `substr(fecha,1,4)` da un unico valor "2022"). El recurso que
SI trae datos vigentes es "Buenos Aires Compras - Anual" (bac_anual.csv):
mismo OCID, pero cada fila ya viene compilada con tender + primer award +
primer item. Limitacion conocida: como es un CSV "compilado" (no el
release-level `tender.csv`), procesos con mas de un renglon solo muestran
el primero -- para full fidelity habria que sumar el `tender.csv` de 620MB
y unir por ocid, pendiente si hace falta mas adelante.
"""
from pathlib import Path

import pandas as pd
import requests

BAC_ANUAL_CSV_URL = "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/ministerio-de-economia-y-finanzas/buenos-aires-compras/bac_anual.csv"

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "bac"


def _download(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        return dest
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                f.write(chunk)
    return dest


def _num(value):
    return None if pd.isna(value) else float(value)


def _txt(value):
    return None if pd.isna(value) else str(value)


def fetch(limit: int | None = None) -> list[dict]:
    path = _download(BAC_ANUAL_CSV_URL, DATA_DIR / "bac_anual.csv")
    df = pd.read_csv(path, dtype=str, low_memory=False)
    if limit:
        df = df.head(limit)

    rows = []
    for r in df.to_dict(orient="records"):
        numero_proceso = r.get("tender/id")
        if pd.isna(numero_proceso):
            continue  # release sin datos de tender (solo award/contract) -- se ignora por ahora

        items = []
        if pd.notna(r.get("tender/items/0/description")):
            items.append(
                {
                    "numero_renglon": _txt(r.get("tender/items/0/id")),
                    "codigo_item": _txt(r.get("tender/items/0/classification/id")),
                    "descripcion": _txt(r.get("tender/items/0/description")),
                    "cantidad": _num(r.get("tender/items/0/quantity")),
                    "unidad": _txt(r.get("tender/items/0/unit/name")),
                    "precio_unitario": _num(r.get("tender/items/0/unit/value/amount")),
                    "moneda": _txt(r.get("tender/items/0/unit/value/currency")),
                    "clasificacion": _txt(r.get("tender/items/0/classification/scheme")),
                }
            )

        rows.append(
            {
                "fuente": "bac",
                "numero_proceso": numero_proceso,
                "titulo": _txt(r.get("tender/title")),
                "descripcion": _txt(r.get("tender/description")),
                "organismo": _txt(r.get("tender/procuringEntity/name")),
                "jurisdiccion": "CABA",
                "tipo_procedimiento": _txt(r.get("tender/procurementMethodDetails")) or _txt(r.get("tender/procurementMethod")),
                "fecha_publicacion": _txt(r.get("tender/tenderPeriod/startDate")),
                "fecha_apertura": _txt(r.get("tender/tenderPeriod/endDate")),
                "monto_estimado": _num(r.get("tender/value/amount")),
                "moneda": _txt(r.get("tender/value/currency")),
                "estado": _txt(r.get("tender/status")),
                "proveedor_adjudicado": _txt(r.get("awards/0/suppliers/0/name")),
                "monto_adjudicado": _num(r.get("awards/0/value/amount")),
                "url": f"https://www.buenosairescompras.gob.ar/Compras/VerProcesoCompra.aspx?qs={r.get('ocid')}",
                "items": items,
            }
        )
    return rows


if __name__ == "__main__":
    data = fetch(limit=500)
    print(f"{len(data)} licitaciones normalizadas")
    for row in data[:3]:
        print(row)
