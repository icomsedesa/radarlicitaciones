"""Ingesta solo de PBAC (Provincia de Buenos Aires), liviana.

Existe porque el servidor de PBAC no responde a las IP de GitHub Actions ni
de Vercel (verificado nov-2026), asi que no puede correr dentro del workflow
diario. Se corre desde una maquina con salida a internet desde Argentina
(ver README / scripts/ingesta_pbac_local.ps1).

A proposito NO importa src.ingest: aquel arrastra pandas/playwright/pdfplumber
y todos los conectores; esto solo necesita requirements-pbac.txt.

Uso:
    python -m src.ingest_pbac
Requiere TURSO_DATABASE_URL y TURSO_AUTH_TOKEN (en .env o en el entorno).
"""
import os
import sys

from src import db
from src.connectors import pbac


def main() -> int:
    conn = db.get_connection()
    try:
        rows = pbac.fetch(max_pages=5)
        n = db.upsert_many(conn, rows)
        print(f"PBAC: {n} filas cargadas")
        db.registrar_estado_fuente(conn, ["pbac"], ok=True)
        return 0
    except Exception as e:
        print(f"! error: {e!r}")
        db.registrar_estado_fuente(conn, ["pbac"], ok=False, mensaje=str(e))
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    try:
        codigo = main()
    except BaseException as e:
        print(f"! la ingesta fallo: {e!r}")
        codigo = 1
    # os._exit: el cliente libsql deja un hilo asyncio no-daemon que
    # impide terminar el proceso ante una excepcion
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(codigo)
