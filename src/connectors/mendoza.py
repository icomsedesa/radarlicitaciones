"""Provincia de Mendoza -- dataset historico "Contrataciones Abiertas
Mendoza" (datosabiertos-compras.mendoza.gov.ar), formato OCDS 1.1 real
(no compilado/aplanado como el bac_anual.csv de CABA): cada release trae
tender + planning + awards + contracts completos, INCLUYENDO renglones
(tender.items) y adjudicaciones (awards, con proveedor y monto) sin
necesitar backfill aparte via Playwright -- a diferencia de COMPR.AR
nacional.

Licencia: CC-BY 4.0. Se actualiza mensualmente, pero igual que el CSV
masivo nacional queda desfasado semanas/meses -- para lo realmente
vigente hoy usar `mendoza_live.py` (buscador en vivo, Estado=Publicado).

Hay 3 archivos por rango de fechas (mas viejo a mas nuevo); por defecto
solo se baja el mas reciente (11MB, ~1700 releases de los ultimos meses)
-- los otros dos (87MB y 125MB, historia 2020-2025) quedan disponibles
via el parametro `archivos` si hiciera falta mas profundidad historica.
"""
import re
from pathlib import Path

import requests

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "mendoza"

# (nombre_archivo, url) -- de mas reciente a mas vieja.
ARCHIVOS = [
    ("20260104_release.json", "https://datosabiertos-compras.mendoza.gov.ar/descargar-json/03/20260104_release.json"),
    ("20250810_release.json", "https://datosabiertos-compras.mendoza.gov.ar/descargar-json/02/20250810_release.json"),
    ("2020_20231021_release.json", "https://datosabiertos-compras.mendoza.gov.ar/descargar-json/01/2020_20231021_v1_release.json"),
]

RE_MONTO_CERO = re.compile(r"^0(\.0+)?$")


def _download(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        return dest
    with requests.get(url, stream=True, timeout=180) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                f.write(chunk)
    return dest


def _monto(valor: dict | None):
    if not valor:
        return None, None
    amount = valor.get("amount")
    return (float(amount) if amount else None), valor.get("currency")


def _parse_release(release: dict) -> dict | None:
    tender = release.get("tender") or {}
    numero_proceso = tender.get("id")
    if not numero_proceso:
        return None  # release sin tender (solo contrato suelto) -- se ignora

    monto_estimado, moneda = _monto(tender.get("value"))
    if monto_estimado is None:
        monto_estimado, moneda = _monto((release.get("planning") or {}).get("budget", {}).get("amount"))
    moneda = moneda or "ARS"

    awards = release.get("awards") or []
    primer_award = awards[0] if awards else {}
    monto_adjudicado, _ = _monto(primer_award.get("value"))
    proveedores = primer_award.get("suppliers") or []
    proveedor_adjudicado = proveedores[0].get("name") if proveedores else None

    items = []
    for it in tender.get("items") or []:
        items.append(
            {
                "numero_renglon": it.get("id"),
                "codigo_item": (it.get("classification") or {}).get("id"),
                "descripcion": it.get("description"),
                "cantidad": it.get("quantity"),
                "unidad": None,
                "precio_unitario": None,
                "moneda": moneda,
                "clasificacion": (it.get("classification") or {}).get("scheme"),
            }
        )

    return {
        "fuente": "mendoza",
        "numero_proceso": numero_proceso,
        "titulo": tender.get("title") or tender.get("description"),
        "descripcion": tender.get("description"),
        "organismo": (release.get("buyer") or {}).get("name"),
        "jurisdiccion": "Provincia de Mendoza",
        "tipo_procedimiento": tender.get("submissionMethodDetails") or tender.get("procurementMethod"),
        "fecha_publicacion": (tender.get("tenderPeriod") or {}).get("startDate"),
        "fecha_apertura": (tender.get("tenderPeriod") or {}).get("endDate"),
        "monto_estimado": monto_estimado,
        "moneda": moneda,
        "estado": tender.get("status"),
        "proveedor_adjudicado": proveedor_adjudicado,
        "monto_adjudicado": monto_adjudicado,
        "url": tender.get("awardCriteriaDetails"),
        "items": items,
    }


def fetch(archivos: int = 1) -> list[dict]:
    """`archivos`: cuantos de los 3 JSON bajar, empezando por el mas
    reciente (1 = solo el ultimo, mas rapido; 3 = historia completa desde
    2020, ~220MB)."""
    import json

    rows = {}
    for nombre, url in ARCHIVOS[:archivos]:
        path = _download(url, DATA_DIR / nombre)
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        for release in data.get("releases", []):
            row = _parse_release(release)
            if not row:
                continue
            # varios releases (planning/tender/award/contract) comparten el
            # mismo numero_proceso a medida que avanza el expediente -- nos
            # quedamos con el que tenga mas datos de adjudicacion.
            existente = rows.get(row["numero_proceso"])
            if not existente or (row["proveedor_adjudicado"] and not existente["proveedor_adjudicado"]):
                rows[row["numero_proceso"]] = row
    return list(rows.values())


if __name__ == "__main__":
    data = fetch()
    print(f"{len(data)} licitaciones normalizadas")
    for row in data[:3]:
        print(row)
