"""Conector COMPR.AR (Nacion, bienes y servicios).

Fuente: CSV propio de la ONC publicado en infra.datos.gob.ar (no es OCDS).
Dos tablas unidas por Numero_Proceso: Convocatorias + Adjudicaciones.
"""
import re
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests

CONVOCATORIAS_URL = "https://infra.datos.gob.ar/catalog/jgm/dataset/4/distribution/4.21/download/Convocatorias.csv"
ADJUDICACIONES_URL = "https://infra.datos.gob.ar/catalog/jgm/dataset/4/distribution/4.22/download/Adjudicaciones.csv"

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "comprar_ar"


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


def _read_csv(path: Path) -> pd.DataFrame:
    try:
        return pd.read_csv(path, encoding="utf-8", dtype=str)
    except UnicodeDecodeError:
        return pd.read_csv(path, encoding="latin-1", dtype=str)


def _parse_monto(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    s = str(value).replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


_MESES_AMPM = re.compile(r"a\.\s*m\.", re.IGNORECASE), re.compile(r"p\.\s*m\.", re.IGNORECASE)


def _parse_fecha(value):
    if not value or (isinstance(value, float) and pd.isna(value)):
        return None
    s = str(value).strip()
    s = _MESES_AMPM[0].sub("AM", s)
    s = _MESES_AMPM[1].sub("PM", s)
    for fmt in ("%d/%m/%Y %I:%M:%S %p", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).isoformat()
        except ValueError:
            continue
    return None


def fetch(limit: int | None = None) -> list[dict]:
    """Descarga y normaliza COMPR.AR. `limit` acota filas para pruebas rapidas."""
    conv_path = _download(CONVOCATORIAS_URL, DATA_DIR / "Convocatorias.csv")
    adj_path = _download(ADJUDICACIONES_URL, DATA_DIR / "Adjudicaciones.csv")

    convocatorias = _read_csv(conv_path)
    adjudicaciones = _read_csv(adj_path)

    adjudicaciones["Monto_num"] = adjudicaciones["Monto"].apply(_parse_monto)
    agg = (
        adjudicaciones.groupby("Numero_Proceso")
        .agg(
            proveedores=("Descripcion_Proveedor", lambda s: "; ".join(sorted(set(s.dropna()))[:3])),
            monto_adjudicado=("Monto_num", "sum"),
            moneda=("Moneda", lambda s: s.mode().iat[0] if not s.mode().empty else None),
        )
        .reset_index()
    )

    merged = convocatorias.merge(agg, on="Numero_Proceso", how="left")
    if limit:
        merged = merged.head(limit)

    rows = []
    for r in merged.itertuples(index=False):
        r = r._asdict() if hasattr(r, "_asdict") else dict(zip(merged.columns, r))
        rows.append(
            {
                "fuente": "comprar_ar",
                "numero_proceso": r.get("Numero_Proceso"),
                "titulo": r.get("Nombre_del_Proceso"),
                "descripcion": r.get("Objeto_del_Proceso"),
                "organismo": r.get("Descripcion_SAF"),
                "jurisdiccion": "Nación",
                "tipo_procedimiento": r.get("Tipo_de_Procedimiento"),
                "fecha_publicacion": _parse_fecha(r.get("Fecha_de_Publicacion")),
                "fecha_apertura": _parse_fecha(r.get("Fecha_de_Apertura")),
                "monto_estimado": _parse_monto(r.get("Monto_Estimado")),
                "moneda": r.get("moneda") if pd.notna(r.get("moneda")) else "Peso Argentino",
                # "Etapa" (Unica/Multiple) NO es un estado real -- el CSV masivo no trae
                # estado de apertura confiable, por eso queda null hasta refresh_live.
                "estado": None,
                "proveedor_adjudicado": r.get("proveedores") if pd.notna(r.get("proveedores")) else None,
                "monto_adjudicado": r.get("monto_adjudicado") if pd.notna(r.get("monto_adjudicado")) else None,
                "url": f"https://comprar.gob.ar/BuscarAvanzado.aspx?qs={r.get('Numero_Proceso')}",
            }
        )
    return rows


if __name__ == "__main__":
    data = fetch(limit=5)
    for row in data:
        print(row)
