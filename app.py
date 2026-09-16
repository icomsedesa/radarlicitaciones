"""Buscador simple (PoC) sobre la base normalizada. Ejecutar: python app.py"""
from datetime import datetime
from urllib.parse import urlencode

from flask import Flask, abort, render_template, request

from src import db

app = Flask(__name__)

PAGE_SIZE = 50

FUENTES = [
    ("comprar_ar", "COMPR.AR (Nación)"),
    ("bac", "BAC (CABA)"),
    ("pbac", "PBAC (Provincia)"),
]

URGENCIA_CASE = """
    CASE
        WHEN fecha_apertura IS NULL THEN 'sin_fecha'
        WHEN julianday(fecha_apertura) < julianday('now') THEN 'cerrada'
        WHEN julianday(fecha_apertura) - julianday('now') <= 2 THEN 'rojo'
        WHEN julianday(fecha_apertura) - julianday('now') <= 7 THEN 'amarillo'
        ELSE 'verde'
    END
"""


def _url_with(**overrides):
    args = request.args.to_dict()
    for k, v in overrides.items():
        if v is None or v is False or v == "":
            args.pop(k, None)
        else:
            args[k] = "1" if v is True else v
    qs = urlencode(args)
    return "/" + (f"?{qs}" if qs else "")


app.jinja_env.globals["url_with"] = _url_with


def _texto_faltante(fecha_apertura, urgencia):
    if not fecha_apertura or urgencia in ("sin_fecha", "cerrada"):
        return "Cerrada" if urgencia == "cerrada" else None
    try:
        dt = datetime.fromisoformat(fecha_apertura)
    except ValueError:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone().replace(tzinfo=None)
    segundos = (dt - datetime.now()).total_seconds()
    if segundos < 0:
        return "Cerrada"
    horas = segundos / 3600
    if horas < 1:
        return f"{max(1, int(segundos // 60))} min"
    if horas < 48:
        return f"{int(horas)} h"
    return f"{int(horas // 24)} días"


@app.route("/")
def index():
    q = request.args.get("q", "").strip()
    fuente = request.args.get("fuente", "").strip()
    solo_con_renglones = request.args.get("renglones", "") == "1"
    solo_vigentes = request.args.get("vigentes", "") == "1"
    urgencia = request.args.get("urgencia", "").strip()
    apertura_desde = request.args.get("desde", "").strip()
    apertura_hasta = request.args.get("hasta", "").strip()

    conn = db.get_connection()
    where = []
    params = {}

    if q:
        where.append("(base.titulo LIKE :q OR base.descripcion LIKE :q OR base.organismo LIKE :q)")
        params["q"] = f"%{q}%"
    if fuente:
        where.append("base.fuente = :fuente")
        params["fuente"] = fuente
    if solo_vigentes:
        where.append("base.estado IN ('Publicado', 'active')")
    if urgencia:
        where.append("base.urgencia = :urgencia")
        params["urgencia"] = urgencia
    if apertura_desde:
        where.append("date(base.fecha_apertura) >= :desde")
        params["desde"] = apertura_desde
    if apertura_hasta:
        where.append("date(base.fecha_apertura) <= :hasta")
        params["hasta"] = apertura_hasta

    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    having_sql = "HAVING COUNT(i.id) > 0" if solo_con_renglones else ""
    order_sql = "base.fecha_apertura ASC" if (solo_vigentes or urgencia) else "base.fecha_apertura DESC"

    query = f"""
        WITH base AS (
            SELECT *, {URGENCIA_CASE} AS urgencia FROM licitaciones
        )
        SELECT base.*, COUNT(i.id) AS n_renglones
        FROM base
        LEFT JOIN licitacion_items i ON i.licitacion_id = base.id
        {where_sql}
        GROUP BY base.id
        {having_sql}
        ORDER BY {order_sql}
        LIMIT {PAGE_SIZE}
    """
    rows = [dict(r) for r in conn.execute(query, params).fetchall()]
    for r in rows:
        r["faltan"] = _texto_faltante(r["fecha_apertura"], r["urgencia"])

    total = conn.execute(
        f"""
        WITH base AS (
            SELECT *, {URGENCIA_CASE} AS urgencia FROM licitaciones
        )
        SELECT COUNT(*) c FROM (
            SELECT base.id
            FROM base
            LEFT JOIN licitacion_items i ON i.licitacion_id = base.id
            {where_sql}
            GROUP BY base.id
            {having_sql}
        )
        """,
        params,
    ).fetchone()["c"]
    por_fuente = {r["fuente"]: r["c"] for r in conn.execute(
        "SELECT fuente, COUNT(*) c FROM licitaciones GROUP BY fuente"
    ).fetchall()}
    conn.close()

    return render_template(
        "index.html",
        rows=rows,
        total=total,
        q=q,
        fuente=fuente,
        solo_con_renglones=solo_con_renglones,
        solo_vigentes=solo_vigentes,
        urgencia=urgencia,
        apertura_desde=apertura_desde,
        apertura_hasta=apertura_hasta,
        fuentes=FUENTES,
        por_fuente=por_fuente,
        shown=len(rows),
    )


@app.route("/licitacion/<int:licitacion_id>")
def detalle(licitacion_id):
    conn = db.get_connection()
    lic = conn.execute(
        f"""
        SELECT *, {URGENCIA_CASE} AS urgencia FROM licitaciones WHERE id=?
        """,
        (licitacion_id,),
    ).fetchone()
    if not lic:
        conn.close()
        abort(404)
    lic = dict(lic)
    lic["faltan"] = _texto_faltante(lic["fecha_apertura"], lic["urgencia"])
    items = db.get_items(conn, licitacion_id)
    conn.close()
    return render_template("detalle.html", lic=lic, items=items)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
