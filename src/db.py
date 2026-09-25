"""Esquema y acceso a la base de datos.

Local (default): SQLite en `data/licitaciones.db`, via el modulo estandar
`sqlite3`. Si estan definidas `TURSO_DATABASE_URL` y `TURSO_AUTH_TOKEN`
(en el entorno o en un `.env` -- ver `src/db_turso.py`), se conecta en
cambio a esa base remota en Turso, con el mismo esquema y las mismas
consultas -- ver `db_turso.TursoConnection`, un shim que imita lo minimo
de la API de `sqlite3` que este archivo usa."""
import sqlite3
from pathlib import Path

from dotenv import load_dotenv

from src import db_turso

load_dotenv()

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

CREATE TABLE IF NOT EXISTS licitacion_ofertas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    licitacion_id INTEGER NOT NULL REFERENCES licitaciones(id) ON DELETE CASCADE,
    proveedor TEXT,
    cuit TEXT,
    monto REAL,
    moneda TEXT,
    fecha_oferta TEXT,
    es_ganadora INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_ofertas_licitacion ON licitacion_ofertas(licitacion_id);
CREATE INDEX IF NOT EXISTS idx_ofertas_proveedor ON licitacion_ofertas(proveedor);

CREATE TABLE IF NOT EXISTS credenciales_portal (
    portal TEXT PRIMARY KEY,
    usuario TEXT,
    password_cifrada BLOB,
    actualizado_en TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS palabras_clave (
    palabra TEXT PRIMARY KEY,
    creado_en TEXT DEFAULT CURRENT_TIMESTAMP
);
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
    conn = db_turso.conectar_desde_env()
    if conn is None:
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


def set_items(conn, fuente, numero_proceso, items, url=None):
    """Reemplaza los items de una licitacion ya existente (identificada por
    fuente+numero_proceso), sin tocar el resto de sus campos (salvo `url`,
    si se pasa). Devuelve False si la licitacion no existe."""
    cur = conn.execute(
        "SELECT id FROM licitaciones WHERE fuente=? AND numero_proceso=?",
        (fuente, numero_proceso),
    )
    row = cur.fetchone()
    if not row:
        return False
    licitacion_id = row["id"]
    if url:
        conn.execute("UPDATE licitaciones SET url=? WHERE id=?", (url, licitacion_id))
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


def set_ofertas(conn, fuente, numero_proceso, ofertas):
    """Reemplaza las ofertas (comparativas: quien cotizo, a que precio) de una
    licitacion ya existente, identificada por fuente+numero_proceso. Cada
    oferta es un dict con proveedor/cuit/monto/moneda/fecha_oferta/
    es_ganadora. Devuelve False si la licitacion no existe."""
    cur = conn.execute(
        "SELECT id FROM licitaciones WHERE fuente=? AND numero_proceso=?",
        (fuente, numero_proceso),
    )
    row = cur.fetchone()
    if not row:
        return False
    licitacion_id = row["id"]
    conn.execute("DELETE FROM licitacion_ofertas WHERE licitacion_id=?", (licitacion_id,))
    for oferta in ofertas:
        conn.execute(
            """INSERT INTO licitacion_ofertas
               (licitacion_id, proveedor, cuit, monto, moneda, fecha_oferta, es_ganadora)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                licitacion_id,
                oferta.get("proveedor"),
                oferta.get("cuit"),
                oferta.get("monto"),
                oferta.get("moneda"),
                oferta.get("fecha_oferta"),
                1 if oferta.get("es_ganadora") else 0,
            ),
        )
    conn.commit()
    return True


def get_ofertas(conn, licitacion_id):
    return conn.execute(
        "SELECT * FROM licitacion_ofertas WHERE licitacion_id=? ORDER BY monto ASC", (licitacion_id,)
    ).fetchall()


def procesos_con_ofertas(conn, fuente):
    """Numeros de proceso de `fuente` que ya tienen ofertas cargadas -- para
    que una ingesta incremental (ej. actas de apertura de PAMI, que hay que
    descargar y parsear en PDF una por una) no tenga que volver a bajar algo
    que ya se proceso en una corrida anterior."""
    rows = conn.execute(
        """
        SELECT DISTINCT l.numero_proceso
        FROM licitacion_ofertas o
        JOIN licitaciones l ON l.id = o.licitacion_id
        WHERE l.fuente = ?
        """,
        (fuente,),
    ).fetchall()
    return {r["numero_proceso"] for r in rows}


def guardar_credencial(conn, portal, usuario, password_cifrada):
    """`password_cifrada` ya debe venir cifrada (ver src/secrets_store.py) --
    esta funcion no cifra, solo persiste."""
    conn.execute(
        """
        INSERT INTO credenciales_portal (portal, usuario, password_cifrada, actualizado_en)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(portal) DO UPDATE SET
            usuario=excluded.usuario, password_cifrada=excluded.password_cifrada,
            actualizado_en=CURRENT_TIMESTAMP
        """,
        (portal, usuario, password_cifrada),
    )
    conn.commit()


def eliminar_credencial(conn, portal):
    conn.execute("DELETE FROM credenciales_portal WHERE portal=?", (portal,))
    conn.commit()


def obtener_credencial(conn, portal):
    """Devuelve la fila cruda (con password_cifrada sin descifrar) o None.
    Descifrar es responsabilidad de quien vaya a USAR la credencial (el
    conector autenticado), nunca de una vista que la vaya a mostrar."""
    return conn.execute(
        "SELECT * FROM credenciales_portal WHERE portal=?", (portal,)
    ).fetchone()


def listar_credenciales(conn):
    """Para la pantalla de Configuracion: estado por portal (configurado o
    no, usuario, fecha) SIN el contenido de la contraseña."""
    return conn.execute(
        "SELECT portal, usuario, actualizado_en FROM credenciales_portal"
    ).fetchall()


def listar_palabras_clave(conn):
    """Palabras clave guardadas -- compartidas entre todos los que usan el
    radar (antes vivian en localStorage, por lo que cada PC/usuario tenia
    su propia lista y no se veian entre si)."""
    rows = conn.execute(
        "SELECT palabra FROM palabras_clave ORDER BY creado_en ASC"
    ).fetchall()
    return [r["palabra"] for r in rows]


def agregar_palabra_clave(conn, palabra):
    conn.execute(
        "INSERT OR IGNORE INTO palabras_clave (palabra) VALUES (?)", (palabra,)
    )
    conn.commit()


def eliminar_palabra_clave(conn, palabra):
    conn.execute("DELETE FROM palabras_clave WHERE palabra=?", (palabra,))
    conn.commit()
