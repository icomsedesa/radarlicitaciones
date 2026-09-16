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
    conn.executescript(SCHEMA)
    return conn


def upsert_many(conn, rows):
    """rows: lista de dicts con las claves del esquema `licitaciones`."""
    if not rows:
        return 0
    conn.executemany(UPSERT_SQL, rows)
    conn.commit()
    return len(rows)
