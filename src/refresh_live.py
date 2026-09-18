"""Actualiza el estado real de las licitaciones COMPR.AR contra el buscador
EN VIVO de comprar.gob.ar (no el CSV masivo, que esta semanas desfasado).

Corre esto periodicamente (p.ej. una vez por dia) para saber que esta
realmente "Publicado" (abierto) hoy. Actualiza estado/fecha_apertura/titulo
de las licitaciones que ya existen (de la carga del CSV) sin pisar su
monto/descripcion, e inserta las que todavia no estaban en el CSV.

Uso:
    python -m src.refresh_live              # todas las paginas
    python -m src.refresh_live --max 5      # acotar para pruebas
"""
import argparse

from src import db
from src.connectors import comprar_ar_live, mendoza_live


def run(max_paginas=None):
    print("Consultando comprar.gob.ar (Estado = Publicado)...")
    rows = comprar_ar_live.fetch_abiertas(max_paginas=max_paginas)
    print(f"{len(rows)} licitaciones publicadas encontradas")

    conn = db.get_connection()
    n_update, n_insert = db.upsert_live_estado(conn, rows)
    conn.close()

    print(f"  {n_update} actualizadas (ya estaban del CSV masivo)")
    print(f"  {n_insert} nuevas (todavia no estaban en el CSV masivo)")

    print("Consultando comprar.mendoza.gov.ar (Estado = Publicado)...")
    rows = mendoza_live.fetch(max_paginas=max_paginas)
    print(f"{len(rows)} licitaciones publicadas encontradas")

    conn = db.get_connection()
    n_update, n_insert = db.upsert_live_estado(conn, rows)
    conn.close()

    print(f"  {n_update} actualizadas (ya estaban del dataset historico)")
    print(f"  {n_insert} nuevas (todavia no estaban en el dataset historico)")

    print("Consultando comprarosep.mendoza.gov.ar (Estado = Publicado)...")
    rows = mendoza_live.fetch_osep(max_paginas=max_paginas)
    print(f"{len(rows)} licitaciones publicadas encontradas")

    conn = db.get_connection()
    n_update, n_insert = db.upsert_live_estado(conn, rows)
    conn.close()

    print(f"  {n_update} actualizadas")
    print(f"  {n_insert} nuevas")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--max", type=int, default=None, help="acotar paginas para pruebas")
    args = parser.parse_args()
    run(max_paginas=args.max)
