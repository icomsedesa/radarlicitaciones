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
import math
import os
import time

import libsql_client

BATCH_SIZE = 500


def _limpiar_valor(v):
    # Turso/Hrana rechaza NaN e Infinity ("Only finite floats...") y eso
    # tiraba abajo toda la ingesta diaria -- se guardan como NULL.
    if isinstance(v, float) and not math.isfinite(v):
        return None
    return v


def _limpiar_params(params):
    if params is None:
        return None
    if isinstance(params, dict):
        return {k: _limpiar_valor(v) for k, v in params.items()}
    return [_limpiar_valor(v) for v in params]


def _normalizar_url(url: str) -> str:
    # libsql_client soporta libsql:// (via websocket/Hrana) pero en este
    # entorno esa via se cuelga -- se fuerza https:// (HTTP simple, ya
    # probado que funciona) salvo que ya venga explicito.
    if url.startswith("libsql://"):
        return "https://" + url[len("libsql://"):]
    return url


def _con_reintentos(fn, intentos=4):
    """Turso a veces devuelve 5xx transitorios (502 en medio de una carga
    larga) y eso dejaba fuentes enteras sin actualizar. Se reintenta con
    espera creciente; los errores de SQL/parametros (no transitorios) se
    propagan de inmediato."""
    for i in range(intentos):
        try:
            return fn()
        except Exception as e:
            transitorio = "SERVER_ERROR" in str(e) or "HTTP status 5" in str(e)
            if not transitorio or i == intentos - 1:
                raise
            time.sleep(3 * (i + 1))


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
        rs = _con_reintentos(lambda: self._client.execute(sql, _limpiar_params(params)))
        return TursoCursor(rs)

    def executemany(self, sql, seq_of_params):
        seq_of_params = list(seq_of_params)
        for i in range(0, len(seq_of_params), BATCH_SIZE):
            lote = seq_of_params[i:i + BATCH_SIZE]
            stmts = [libsql_client.Statement(sql, _limpiar_params(p)) for p in lote]
            _con_reintentos(lambda: self._client.batch(stmts))

    def executescript(self, script: str):
        statements = [s.strip() for s in script.split(";")]
        statements = [s for s in statements if s]
        if statements:
            _con_reintentos(lambda: self._client.batch(statements))

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
