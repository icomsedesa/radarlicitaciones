"""Migracion unica: copia todo lo que ya esta en el SQLite local
(data/licitaciones.db) a la base remota en Turso, preservando los `id`
tal cual (para que licitacion_items.licitacion_id y
licitacion_ofertas.licitacion_id sigan apuntando bien) en vez de re-
scrapear todas las fuentes de nuevo.

Uso: .venv\\Scripts\\python.exe scripts_migrar_a_turso.py
"""
import sqlite3

from src import db, db_turso

COLUMNAS = {
    "licitaciones": [
        "id", "fuente", "numero_proceso", "titulo", "descripcion", "organismo",
        "jurisdiccion", "tipo_procedimiento", "fecha_publicacion", "fecha_apertura",
        "monto_estimado", "moneda", "estado", "proveedor_adjudicado",
        "monto_adjudicado", "url", "actualizado_en",
    ],
    "licitacion_items": [
        "id", "licitacion_id", "numero_renglon", "codigo_item", "descripcion",
        "cantidad", "unidad", "precio_unitario", "moneda", "clasificacion",
    ],
    "licitacion_ofertas": [
        "id", "licitacion_id", "proveedor", "cuit", "monto", "moneda",
        "fecha_oferta", "es_ganadora",
    ],
}


def migrar_tabla(local_conn, turso_conn, tabla):
    cols = COLUMNAS[tabla]
    placeholders = ", ".join(f":{c}" for c in cols)
    insert_sql = f"INSERT INTO {tabla} ({', '.join(cols)}) VALUES ({placeholders})"

    local_conn.row_factory = sqlite3.Row
    filas = [dict(r) for r in local_conn.execute(f"SELECT {', '.join(cols)} FROM {tabla}")]
    print(f"  {tabla}: {len(filas)} filas a migrar")
    if filas:
        turso_conn.executemany(insert_sql, filas)

    max_id = max((f["id"] for f in filas), default=0)
    if max_id:
        turso_conn.execute(
            "INSERT INTO sqlite_sequence (name, seq) VALUES (:t, :m) "
            "ON CONFLICT(name) DO UPDATE SET seq=excluded.seq",
            {"t": tabla, "m": max_id},
        )
    print(f"  {tabla}: OK (max id={max_id})")


def main():
    local_conn = sqlite3.connect(db.DB_PATH)
    turso_conn = db_turso.conectar_desde_env()
    if turso_conn is None:
        raise SystemExit("Faltan TURSO_DATABASE_URL / TURSO_AUTH_TOKEN en el entorno (.env)")
    turso_conn.executescript(db.SCHEMA)

    print("Limpiando tablas en Turso (por si hay datos de prueba)...")
    turso_conn.execute("DELETE FROM licitacion_ofertas")
    turso_conn.execute("DELETE FROM licitacion_items")
    turso_conn.execute("DELETE FROM licitaciones")

    for tabla in ("licitaciones", "licitacion_items", "licitacion_ofertas"):
        migrar_tabla(local_conn, turso_conn, tabla)

    local_conn.close()
    turso_conn.close()
    print("Migracion completa.")


if __name__ == "__main__":
    main()
