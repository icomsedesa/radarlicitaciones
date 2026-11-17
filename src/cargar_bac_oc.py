"""Carga los adjudicatarios de BAC (ordenes de compra publicas) en la base.

Incremental: solo procesa los "Adjudicado" de los ultimos 30 dias que todavia
no tienen ofertas cargadas. Va DESPUES de refresh_live (que es quien inserta
los procesos de los ultimos 30 dias que el CSV anual de BAC no trae).

Uso:
    python -m src.cargar_bac_oc [max_procesos]
"""
import os
import sys

from src import db
from src.connectors import bac_adjudicaciones


def run(max_procesos=150) -> int:
    conn = db.get_connection()
    try:
        conocidos = db.procesos_con_ofertas(conn, "bac")
        print(f"{len(conocidos)} procesos de BAC ya tienen ofertas cargadas")
        datos = bac_adjudicaciones.fetch(conocidos=conocidos, max_procesos=max_procesos)
        n = 0
        for d in datos:
            if db.set_ofertas_oc(conn, "bac", d["numero_proceso"], d["ofertas"]):
                n += 1
        print(f"{n} procesos con adjudicatario cargados ({len(datos)} leidos)")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    try:
        codigo = run(int(sys.argv[1]) if len(sys.argv) > 1 else 150)
    except BaseException as e:
        print(f"! fallo: {e!r}")
        codigo = 0  # no dejar el job en rojo por un portal ajeno
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(codigo)
