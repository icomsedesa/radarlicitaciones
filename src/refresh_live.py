"""Actualiza el estado real de las licitaciones (COMPR.AR, Mendoza, BAC)
contra los buscadores EN VIVO de cada portal -- no los CSV/datasets
masivos, que quedan semanas desfasados (o, en el caso de BAC, con la fecha
de apertura directamente vencida aunque el proceso siga abierto).

Corre esto periodicamente (p.ej. una vez por dia) para saber que esta
realmente "Publicado" (abierto) hoy. Actualiza estado/fecha_apertura/titulo
de las licitaciones que ya existen (de la carga del CSV) sin pisar su
monto/descripcion, e inserta las que todavia no estaban en el CSV.

Uso:
    python -m src.refresh_live              # todas las paginas
    python -m src.refresh_live --max 5      # acotar para pruebas
"""
import argparse
import os
import sys

from src import db
from src.connectors import bac_live, comprar_ar_live, mendoza_live


def _fuente(titulo, fetch, errores):
    """Corre una fuente aislada: si falla (portal caido, dato raro), las
    demas igual se actualizan."""
    print(f"Consultando {titulo}...")
    try:
        rows = fetch()
        print(f"{len(rows)} licitaciones encontradas")
        conn = db.get_connection()
        try:
            n_update, n_insert = db.upsert_live_estado(conn, rows)
        finally:
            conn.close()
        print(f"  {n_update} actualizadas, {n_insert} nuevas")
    except Exception as e:
        print(f"  ! error: {e!r}")
        errores.append(titulo)


def run(max_paginas=None):
    errores = []
    _fuente("buenosairescompras.gob.ar (apertura proxima)",
            lambda: bac_live.fetch(max_paginas=max_paginas), errores)
    _fuente("comprar.gob.ar (Estado = Publicado)",
            lambda: comprar_ar_live.fetch_abiertas(max_paginas=max_paginas), errores)
    _fuente("comprar.mendoza.gov.ar (Estado = Publicado)",
            lambda: mendoza_live.fetch(max_paginas=max_paginas), errores)
    _fuente("comprarosep.mendoza.gov.ar (Estado = Publicado)",
            lambda: mendoza_live.fetch_osep(max_paginas=max_paginas), errores)
    if errores:
        print(f"Fuentes con error: {', '.join(errores)}")
    return errores


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--max", type=int, default=None, help="acotar paginas para pruebas")
    args = parser.parse_args()
    try:
        errores = run(max_paginas=args.max)
        codigo = 1 if errores else 0
    except BaseException as e:
        print(f"! fallo: {e!r}")
        codigo = 1
    # ver src/ingest.py: el hilo asyncio de libsql no deja terminar al proceso
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(codigo)
