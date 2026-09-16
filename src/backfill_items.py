"""Completa los renglones (items) de las licitaciones COMPR.AR vigentes.

Solo tiene sentido para procesos donde todavia se puede aplicar. Usa el
campo `estado` como criterio principal -- confiable solo despues de correr
`python -m src.refresh_live`, que lo trae del buscador en vivo (el CSV
masivo no es confiable para esto: ver README). Si todavia no se corrio
refresh_live, cae a un criterio por fecha con ventana acotada (el CSV
masivo tiene años placeholder como "2099"/"3015" en fechas de apertura).

Uso:
    python -m src.backfill_items                 # todas las vigentes (hasta --max)
    python -m src.backfill_items --max 20         # acotar para pruebas
"""
import argparse
from datetime import datetime, timedelta

from src import db
from src.connectors import comprar_ar_items

HORIZONTE_DIAS = 180  # fallback si todavia no se corrio refresh_live


def run(max_procesos=200):
    conn = db.get_connection()
    ahora = datetime.now().isoformat()
    limite = (datetime.now() + timedelta(days=HORIZONTE_DIAS)).isoformat()

    rows = conn.execute(
        """
        SELECT l.numero_proceso FROM licitaciones l
        WHERE l.fuente='comprar_ar' AND (
            l.estado = 'Publicado'
            OR (l.fecha_apertura >= ? AND l.fecha_apertura <= ?)
        )
        AND NOT EXISTS (SELECT 1 FROM licitacion_items i WHERE i.licitacion_id = l.id)
        ORDER BY l.fecha_apertura ASC
        LIMIT ?
        """,
        (ahora, limite, max_procesos),
    ).fetchall()

    numeros = [r["numero_proceso"] for r in rows]
    print(f"{len(numeros)} licitaciones vigentes de COMPR.AR para completar renglones (sin renglones todavia)")

    if not numeros:
        conn.close()
        return

    resultados = comprar_ar_items.fetch_renglones_batch(numeros)

    total_items = 0
    for numero, resultado in resultados.items():
        items = resultado["items"]
        db.set_items(conn, "comprar_ar", numero, items, url=resultado.get("url"))
        total_items += len(items)
        print(f"  {numero}: {len(items)} renglones")

    conn.close()
    print(f"\nTotal: {total_items} renglones cargados sobre {len(numeros)} licitaciones")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--max", type=int, default=200)
    args = parser.parse_args()
    run(max_procesos=args.max)
