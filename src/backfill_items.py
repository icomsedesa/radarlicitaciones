"""Completa los renglones (items) de las licitaciones COMPR.AR vigentes.

Solo tiene sentido para procesos donde todavia se puede aplicar (fecha de
apertura futura) -- traer renglones del historico completo no aporta y
serian decenas de miles de páginas a scrapear. Correr despues de `ingest`.

Uso:
    python -m src.backfill_items                 # todas las vigentes (hasta --max)
    python -m src.backfill_items --max 20         # acotar para pruebas
"""
import argparse
from datetime import datetime, timedelta

from src import db
from src.connectors import comprar_ar_items

# El CSV masivo tiene fechas de apertura con errores de carga del propio
# organismo (ej. anios "3015" o "2099" usados como placeholder) -- se acota
# la ventana a algo realista para no confundirlas con licitaciones vigentes.
HORIZONTE_DIAS = 180


def run(max_procesos=200):
    conn = db.get_connection()
    ahora = datetime.now().isoformat()
    limite = (datetime.now() + timedelta(days=HORIZONTE_DIAS)).isoformat()

    rows = conn.execute(
        """
        SELECT numero_proceso FROM licitaciones
        WHERE fuente='comprar_ar' AND fecha_apertura >= ? AND fecha_apertura <= ?
        ORDER BY fecha_apertura ASC
        LIMIT ?
        """,
        (ahora, limite, max_procesos),
    ).fetchall()

    numeros = [r["numero_proceso"] for r in rows]
    print(f"{len(numeros)} licitaciones vigentes de COMPR.AR para completar renglones")

    if not numeros:
        conn.close()
        return

    resultados = comprar_ar_items.fetch_renglones_batch(numeros)

    total_items = 0
    for numero, items in resultados.items():
        db.set_items(conn, "comprar_ar", numero, items)
        total_items += len(items)
        print(f"  {numero}: {len(items)} renglones")

    conn.close()
    print(f"\nTotal: {total_items} renglones cargados sobre {len(numeros)} licitaciones")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--max", type=int, default=200)
    args = parser.parse_args()
    run(max_procesos=args.max)
