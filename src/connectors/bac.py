"""Conector Buenos Aires Compras - BAC (CABA).

Fuente: OCDS 1.1 real, release package del anio corriente.
Licencia CC-BY-2.5-AR (datos.buenosaires.gob.ar).
"""
import json
from pathlib import Path

import requests

BAC_ANUAL_JSON_URL = "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/ministerio-de-economia-y-finanzas/buenos-aires-compras/bac_anual.json"

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


def fetch(limit: int | None = None) -> list[dict]:
    path = _download(BAC_ANUAL_JSON_URL, DATA_DIR / "bac_anual.json")
    with open(path, encoding="utf-8") as f:
        package = json.load(f)

    releases = package.get("releases", [])
    if limit:
        releases = releases[:limit]

    by_ocid: dict[str, dict] = {}
    for rel in releases:
        ocid = rel.get("ocid")
        if not ocid:
            continue
        entry = by_ocid.setdefault(ocid, {})
        tender = rel.get("tender")
        if tender:
            entry["tender"] = tender
            entry["parties"] = rel.get("parties", [])
        awards = rel.get("awards")
        if awards:
            entry["award"] = awards[0]

    rows = []
    for ocid, entry in by_ocid.items():
        tender = entry.get("tender") or {}
        award = entry.get("award") or {}
        buyer = tender.get("procuringEntity", {}) or {}
        value = tender.get("value", {}) or {}

        supplier = None
        suppliers = award.get("suppliers") or []
        if suppliers:
            supplier = "; ".join(s.get("name", "") for s in suppliers if s.get("name"))

        rows.append(
            {
                "fuente": "bac",
                "numero_proceso": tender.get("id") or ocid,
                "titulo": tender.get("title"),
                "descripcion": tender.get("description"),
                "organismo": buyer.get("name"),
                "jurisdiccion": "CABA",
                "tipo_procedimiento": tender.get("procurementMethodDetails") or tender.get("procurementMethod"),
                "fecha_publicacion": tender.get("tenderPeriod", {}).get("startDate"),
                "fecha_apertura": tender.get("tenderPeriod", {}).get("endDate"),
                "monto_estimado": value.get("amount"),
                "moneda": value.get("currency"),
                "estado": tender.get("status"),
                "proveedor_adjudicado": supplier,
                "monto_adjudicado": (award.get("value") or {}).get("amount"),
                "url": f"https://www.buenosairescompras.gob.ar/Compras/VerProcesoCompra.aspx?qs={ocid}",
            }
        )
    return rows


if __name__ == "__main__":
    data = fetch(limit=200)
    print(f"{len(data)} licitaciones normalizadas")
    for row in data[:3]:
        print(row)
