"""Orquestador: corre los conectores y carga los resultados normalizados en SQLite.

Uso:
    python -m src.ingest                      # carga completa (comprar_ar full + bac full + pbac 5 paginas)
    python -m src.ingest --rapido              # corrida corta para probar el pipeline
"""
import argparse
import sys

from src import db
from src.connectors import bac, comprar_ar, mendoza, pami, pbac
from src.connectors.municipios import (
    avellaneda, berazategui, chivilcoy, escobar, florencio_varela,
    general_rodriguez, ituzaingo, la_matanza, lanus, lomas_de_zamora, moreno,
    moron, quilmes, san_andres_de_giles, san_isidro, san_miguel, sibom,
    tres_de_febrero, vicente_lopez,
)

# Conectores municipales "simples": basta llamar fetch() sin argumentos.
# (Los que necesitan parametros especiales -- como SIBOM, por city_id --
# se manejan aparte, mas abajo.)
MUNICIPIOS_SIMPLES = [
    ("San Miguel", san_miguel),
    ("La Matanza", la_matanza),
    ("Vicente López", vicente_lopez),
    ("San Andrés de Giles", san_andres_de_giles),
    ("Chivilcoy", chivilcoy),
    ("Quilmes", quilmes),
    ("Morón", moron),
    ("Tres de Febrero", tres_de_febrero),
    ("Florencio Varela", florencio_varela),
    ("Escobar", escobar),
    ("Moreno", moreno),
    ("Avellaneda", avellaneda),
    ("Ituzaingó", ituzaingo),
    ("Lomas de Zamora", lomas_de_zamora),
    ("Berazategui", berazategui),
    ("San Isidro", san_isidro),
    ("General Rodríguez", general_rodriguez),
    ("Lanús", lanus),
]

# Municipios que reutilizan el conector generico de SIBOM (boletin oficial
# compartido de la Provincia), parametrizados por city_id.
MUNICIPIOS_SIBOM = [
    ("Campana", 18, "muni_campana", "Municipalidad de Campana", "Municipio de Campana (GBA)"),
    ("General San Martín", 57, "muni_gral_san_martin", "Municipalidad de General San Martín", "Municipio de General San Martín (GBA norte)"),
    ("Capitán Sarmiento", 20, "muni_capitan_sarmiento", "Municipalidad de Capitán Sarmiento", "Municipio de Capitán Sarmiento (interior bonaerense)"),
    ("San Vicente", 119, "muni_san_vicente", "Municipalidad de San Vicente", "Municipio de San Vicente (GBA sur)"),
]


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

    print("== Mendoza (Provincia y dependencias) ==")
    rows = mendoza.fetch()
    n, n_items = db.upsert_with_items(conn, rows)
    print(f"  {n} filas cargadas ({n_items} renglones)")
    total += n

    print("== PAMI (Nivel Central) ==")
    rows = pami.fetch()
    n = db.upsert_many(conn, rows)
    print(f"  {n} filas cargadas")
    total += n

    print("== PAMI (UGL, 38 unidades en todo el país) ==")
    try:
        rows = pami.fetch_ugl()
        n = db.upsert_many(conn, rows)
        print(f"  {n} filas cargadas")
        total += n
    except Exception as e:
        print(f"  ! error: {e}")

    print("== PAMI (Efectores Sanitarios Propios) ==")
    try:
        rows = pami.fetch_efectores()
        n = db.upsert_many(conn, rows)
        print(f"  {n} filas cargadas")
        total += n
    except Exception as e:
        print(f"  ! error: {e}")

    print("== PAMI (comparativas: actas de apertura) ==")
    try:
        # historico mas amplio que el listado de vigentes -- si el proceso
        # todavia no estaba en la base (ya cerrado, fuera del listado de
        # "vigentes hoy"), se crea aca con lo que trae el acta.
        actas_con_ofertas = pami.fetch_todas_las_ofertas()
        n_ofertas = 0
        for row in actas_con_ofertas:
            ofertas = row.pop("ofertas")
            db.upsert_many(conn, [row])
            if db.set_ofertas(conn, "pami", row["numero_proceso"], ofertas):
                n_ofertas += len(ofertas)
        print(f"  {len(actas_con_ofertas)} procesos con ofertas cargadas ({n_ofertas} ofertas)")
    except Exception as e:
        print(f"  ! error: {e}")

    if municipios:
        for nombre, conector in MUNICIPIOS_SIMPLES:
            print(f"== Municipio de {nombre} ==")
            try:
                rows = conector.fetch()
                n = db.upsert_many(conn, rows)
                print(f"  {n} filas cargadas")
                total += n
            except Exception as e:  # un municipio caido no debe frenar al resto
                print(f"  ! error: {e}")

        for nombre, city_id, fuente, organismo, jurisdiccion in MUNICIPIOS_SIBOM:
            print(f"== Municipio de {nombre} (vía SIBOM) ==")
            try:
                rows = sibom.fetch(
                    city_id=city_id, fuente=fuente,
                    organismo=organismo, jurisdiccion=jurisdiccion,
                )
                n = db.upsert_many(conn, rows)
                print(f"  {n} filas cargadas")
                total += n
            except Exception as e:
                print(f"  ! error: {e}")

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
