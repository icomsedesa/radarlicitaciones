"""Orquestador: corre los conectores y carga los resultados normalizados en SQLite.

Uso:
    python -m src.ingest                      # carga completa (comprar_ar full + bac full + pbac 5 paginas)
    python -m src.ingest --rapido              # corrida corta para probar el pipeline
"""
import argparse
import sys

from src import db
from src.connectors import bac, comprar_ar, pbac
from src.connectors.municipios import la_matanza, san_miguel, sibom


def run(comprar_limit=None, bac_limit=None, pbac_pages=5, municipios=True):
    conn = db.get_connection()
    total = 0

    print("== COMPR.AR (Nación) ==")
    rows = comprar_ar.fetch(limit=comprar_limit)
    n = db.upsert_many(conn, rows)
    print(f"  {n} filas cargadas")
    total += n

    print("== BAC (CABA) ==")
    rows = bac.fetch(limit=bac_limit)
    n, n_items = db.upsert_with_items(conn, rows)
    print(f"  {n} filas cargadas ({n_items} renglones)")
    total += n

    print("== PBAC (Provincia de Buenos Aires) ==")
    rows = pbac.fetch(max_pages=pbac_pages)
    n = db.upsert_many(conn, rows)
    print(f"  {n} filas cargadas")
    total += n

    if municipios:
        print("== Municipio de San Miguel ==")
        rows = san_miguel.fetch()
        n = db.upsert_many(conn, rows)
        print(f"  {n} filas cargadas")
        total += n

        print("== Municipio de La Matanza ==")
        rows = la_matanza.fetch()
        n = db.upsert_many(conn, rows)
        print(f"  {n} filas cargadas")
        total += n

        print("== Municipio de Campana (vía SIBOM) ==")
        rows = sibom.fetch(
            city_id=18, fuente="muni_campana",
            organismo="Municipalidad de Campana", jurisdiccion="Municipio de Campana (GBA)",
        )
        n = db.upsert_many(conn, rows)
        print(f"  {n} filas cargadas")
        total += n

    conn.close()
    print(f"\nTotal: {total} licitaciones en {db.DB_PATH}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--rapido", action="store_true", help="corrida corta para probar el pipeline")
    args = parser.parse_args()

    if args.rapido:
        run(comprar_limit=500, bac_limit=500, pbac_pages=3)
    else:
        run()
    sys.exit(0)
