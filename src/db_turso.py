"""Shim de compatibilidad para que `src/db.py` (escrito contra la API de
`sqlite3` de la libreria estandar) funcione sin cambios contra una base
remota en Turso (libSQL), usando `libsql_client.ClientSync`.

Por que un shim y no reescribir db.py: todo el codigo existente ya usa el
patron `conn.execute(sql, params).fetchone()["columna"]` con placeholders
con nombre (`:param`) -- eso es identico entre sqlite3 y libsql_client, asi
que alcanza con imitar la superficie de la API que db.py realmente usa
(`execute`, `executemany`, `executescript`, `commit`, `close`, cursores
con `.fetchone()`/`.fetchall()`/`.rowcount`, filas accesibles por nombre)
en vez de tocar cada consulta.

Notas:
- No hay `executemany` nativo en libsql_client -- se arma con `batch()`
  (una sola tanda de statements) en lotes de `BATCH_SIZE`, para no mandar
  decenas de miles de statements en un solo request HTTP.
- No hay `executescript` nativo -- se separa el SQL por `;` (asume que no
  hay `;` dentro de strings/datos, cierto para nuestro esquema fijo) y se
  manda como batch.
- `commit()` es un no-op: cada statement ya queda persistido al ejecutarse
  (no hay transacciones explicitas multi-statement en este codigo).
"""
import os

import libsql_client

BATCH_SIZE = 500


def _normalizar_url(url: str) -> str:
    # libsql_client soporta libsql:// (via websocket/Hrana) pero en este
    # entorno esa via se cuelga -- se fuerza https:// (HTTP simple, ya
    # probado que funciona) salvo que ya venga explicito.
    if url.startswith("libsql://"):
        return "https://" + url[len("libsql://"):]
    return url


class TursoCursor:
    def __init__(self, result_set):
        self._rs = result_set
        self._idx = 0

    def fetchone(self):
        if self._idx >= len(self._rs.rows):
            return None
        row = self._rs.rows[self._idx]
        self._idx += 1
        return row.asdict()

    def fetchall(self):
        rows = self._rs.rows[self._idx:]
        self._idx = len(self._rs.rows)
        return [row.asdict() for row in rows]

    def __iter__(self):
        return (row.asdict() for row in self._rs.rows)

    @property
    def rowcount(self):
        return self._rs.rows_affected

    @property
    def lastrowid(self):
        return self._rs.last_insert_rowid


class TursoConnection:
    def __init__(self, url: str, auth_token: str):
        self._client = libsql_client.create_client_sync(
            url=_normalizar_url(url), auth_token=auth_token,
        )
        self.row_factory = None  # compatibilidad de interfaz -- no se usa

    def execute(self, sql, params=None):
        rs = self._client.execute(sql, params)
        return TursoCursor(rs)

    def executemany(self, sql, seq_of_params):
        seq_of_params = list(seq_of_params)
        for i in range(0, len(seq_of_params), BATCH_SIZE):
            lote = seq_of_params[i:i + BATCH_SIZE]
            self._client.batch([libsql_client.Statement(sql, p) for p in lote])

    def executescript(self, script: str):
        statements = [s.strip() for s in script.split(";")]
        statements = [s for s in statements if s]
        if statements:
            self._client.batch(statements)

    def commit(self):
        pass  # cada execute/batch ya persiste -- no hay transaccion abierta que cerrar

    def close(self):
        self._client.close()


def conectar_desde_env() -> "TursoConnection | None":
    """Devuelve una TursoConnection si TURSO_DATABASE_URL y
    TURSO_AUTH_TOKEN estan definidas en el entorno, o None si no (en cuyo
    caso db.get_connection() sigue usando el sqlite3 local de siempre)."""
    url = os.environ.get("TURSO_DATABASE_URL")
    token = os.environ.get("TURSO_AUTH_TOKEN")
    if not url or not token:
        return None
    return TursoConnection(url, token)
