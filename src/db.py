"""Esquema y acceso a la base de datos (SQLite para el PoC; migrar a Postgres en Fase 1 productiva)."""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "licitaciones.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS licitaciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fuente TEXT NOT NULL,
    numero_proceso TEXT NOT NULL,
    titulo TEXT,
    descripcion TEXT,
    organismo TEXT,
    jurisdiccion TEXT,
    tipo_procedimiento TEXT,
    fecha_publicacion TEXT,
    fecha_apertura TEXT,
    monto_estimado REAL,
    moneda TEXT,
    estado TEXT,
    proveedor_adjudicado TEXT,
    monto_adjudicado REAL,
    url TEXT,
    actualizado_en TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(fuente, numero_proceso)
);
CREATE INDEX IF NOT EXISTS idx_licitaciones_organismo ON licitaciones(organismo);
CREATE INDEX IF NOT EXISTS idx_licitaciones_fecha_apertura ON licitaciones(fecha_apertura);
CREATE INDEX IF NOT EXISTS idx_licitaciones_fuente ON licitaciones(fuente);

CREATE TABLE IF NOT EXISTS licitacion_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    licitacion_id INTEGER NOT NULL REFERENCES licitaciones(id) ON DELETE CASCADE,
    numero_renglon TEXT,
    codigo_item TEXT,
    descripcion TEXT,
    cantidad REAL,
    unidad TEXT,
    precio_unitario REAL,
    moneda TEXT,
    clasificacion TEXT
);
CREATE INDEX IF NOT EXISTS idx_items_licitacion ON licitacion_items(licitacion_id);
CREATE INDEX IF NOT EXISTS idx_items_descripcion ON licitacion_items(descripcion);
"""

UPSERT_SQL = """
INSERT INTO licitaciones (
    fuente, numero_proceso, titulo, descripcion, organismo, jurisdiccion,
    tipo_procedimiento, fecha_publicacion, fecha_apertura, monto_estimado,
    moneda, estado, proveedor_adjudicado, monto_adjudicado, url
) VALUES (
    :fuente, :numero_proceso, :titulo, :descripcion, :organismo, :jurisdiccion,
    :tipo_procedimiento, :fecha_publicacion, :fecha_apertura, :monto_estimado,
    :moneda, :estado, :proveedor_adjudicado, :monto_adjudicado, :url
)
ON CONFLICT(fuente, numero_proceso) DO UPDATE SET
    titulo=excluded.titulo, descripcion=excluded.descripcion, organismo=excluded.organismo,
    jurisdiccion=excluded.jurisdiccion, tipo_procedimiento=excluded.tipo_procedimiento,
    fecha_publicacion=excluded.fecha_publicacion, fecha_apertura=excluded.fecha_apertura,
    monto_estimado=excluded.monto_estimado, moneda=excluded.moneda, estado=excluded.estado,
    proveedor_adjudicado=excluded.proveedor_adjudicado, monto_adjudicado=excluded.monto_adjudicado,
    url=excluded.url, actualizado_en=CURRENT_TIMESTAMP;
"""


def get_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn


def upsert_many(conn, rows):
    """rows: lista de dicts con las claves del esquema `licitaciones` (sin items)."""
    if not rows:
        return 0
    conn.executemany(UPSERT_SQL, rows)
    conn.commit()
    return len(rows)


def upsert_with_items(conn, rows):
    """rows: lista de dicts con las claves de `licitaciones` + opcionalmente 'items'
    (lista de dicts con numero_renglon/codigo_item/descripcion/cantidad/unidad/
    precio_unitario/moneda/clasificacion). Reemplaza los items existentes de cada
    licitacion afectada. Devuelve (n_licitaciones, n_items)."""
    n_licitaciones = 0
    n_items = 0
    for row in rows:
        items = row.pop("items", None)
        conn.execute(UPSERT_SQL, row)
        cur = conn.execute(
            "SELECT id FROM licitaciones WHERE fuente=? AND numero_proceso=?",
            (row["fuente"], row["numero_proceso"]),
        )
        licitacion_id = cur.fetchone()["id"]
        n_licitaciones += 1

        if items is not None:
            conn.execute("DELETE FROM licitacion_items WHERE licitacion_id=?", (licitacion_id,))
            for item in items:
                conn.execute(
                    """INSERT INTO licitacion_items
                       (licitacion_id, numero_renglon, codigo_item, descripcion,
                        cantidad, unidad, precio_unitario, moneda, clasificacion)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        licitacion_id,
                        item.get("numero_renglon"),
                        item.get("codigo_item"),
                        item.get("descripcion"),
                        item.get("cantidad"),
                        item.get("unidad"),
                        item.get("precio_unitario"),
                        item.get("moneda"),
                        item.get("clasificacion"),
                    ),
                )
                n_items += 1
    conn.commit()
    return n_licitaciones, n_items


REFRESH_ESTADO_SQL = """
UPDATE licitaciones SET
    estado = :estado,
    fecha_apertura = :fecha_apertura,
    titulo = :titulo,
    organismo = :organismo,
    tipo_procedimiento = :tipo_procedimiento,
    actualizado_en = CURRENT_TIMESTAMP
WHERE fuente = :fuente AND numero_proceso = :numero_proceso
"""


def upsert_live_estado(conn, rows):
    """Para conectores 'en vivo' que solo traen estado/fecha/titulo (no monto
    ni descripcion, p.ej. comprar_ar_live): si la licitacion ya existe (por
    la carga masiva del CSV) actualiza solo esos campos sin pisar monto/
    descripcion; si no existe, la inserta con lo que hay disponible.
    Devuelve (n_actualizadas, n_insertadas)."""
    n_update = 0
    n_insert = 0
    for row in rows:
        cur = conn.execute(REFRESH_ESTADO_SQL, row)
        if cur.rowcount > 0:
            n_update += 1
        else:
            conn.execute(UPSERT_SQL, {**{k: row.get(k) for k in (
                "fuente", "numero_proceso", "titulo", "descripcion", "organismo",
                "jurisdiccion", "tipo_procedimiento", "fecha_publicacion",
                "fecha_apertura", "monto_estimado", "moneda", "estado",
                "proveedor_adjudicado", "monto_adjudicado", "url",
            )}})
            n_insert += 1
    conn.commit()
    return n_update, n_insert


def set_items(conn, fuente, numero_proceso, items):
    """Reemplaza los items de una licitacion ya existente (identificada por
    fuente+numero_proceso), sin tocar el resto de sus campos. Devuelve
    False si la licitacion no existe."""
    cur = conn.execute(
        "SELECT id FROM licitaciones WHERE fuente=? AND numero_proceso=?",
        (fuente, numero_proceso),
    )
    row = cur.fetchone()
    if not row:
        return False
    licitacion_id = row["id"]
    conn.execute("DELETE FROM licitacion_items WHERE licitacion_id=?", (licitacion_id,))
    for item in items:
        conn.execute(
            """INSERT INTO licitacion_items
               (licitacion_id, numero_renglon, codigo_item, descripcion,
                cantidad, unidad, precio_unitario, moneda, clasificacion)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                licitacion_id,
                item.get("numero_renglon"),
                item.get("codigo_item"),
                item.get("descripcion"),
                item.get("cantidad"),
                item.get("unidad"),
                item.get("precio_unitario"),
                item.get("moneda"),
                item.get("clasificacion"),
            ),
        )
    conn.commit()
    return True


def get_items(conn, licitacion_id):
    return conn.execute(
        "SELECT * FROM licitacion_items WHERE licitacion_id=? ORDER BY id", (licitacion_id,)
    ).fetchall()
