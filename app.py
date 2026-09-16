"""Buscador simple (PoC) sobre la base normalizada. Ejecutar: python app.py"""
from flask import Flask, abort, render_template, request

from src import db

app = Flask(__name__)

PAGE_SIZE = 50


@app.route("/")
def index():
    q = request.args.get("q", "").strip()
    fuente = request.args.get("fuente", "").strip()
    solo_con_renglones = request.args.get("renglones", "") == "1"
    solo_vigentes = request.args.get("vigentes", "") == "1"

    conn = db.get_connection()
    where = []
    params = {}

    if q:
        where.append("(l.titulo LIKE :q OR l.descripcion LIKE :q OR l.organismo LIKE :q)")
        params["q"] = f"%{q}%"
    if fuente:
        where.append("l.fuente = :fuente")
        params["fuente"] = fuente
    if solo_vigentes:
        where.append("l.estado IN ('Publicado', 'active')")

    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    having_sql = "HAVING COUNT(i.id) > 0" if solo_con_renglones else ""
    order_sql = "l.fecha_apertura ASC" if solo_vigentes else "l.fecha_apertura DESC"

    rows = conn.execute(
        f"""
        SELECT l.*, COUNT(i.id) AS n_renglones
        FROM licitaciones l
        LEFT JOIN licitacion_items i ON i.licitacion_id = l.id
        {where_sql}
        GROUP BY l.id
        {having_sql}
        ORDER BY {order_sql}
        LIMIT {PAGE_SIZE}
        """,
        params,
    ).fetchall()

    total = conn.execute(
        f"""
        SELECT COUNT(*) c FROM (
            SELECT l.id
            FROM licitaciones l
            LEFT JOIN licitacion_items i ON i.licitacion_id = l.id
            {where_sql}
            GROUP BY l.id
            {having_sql}
        )
        """,
        params,
    ).fetchone()["c"]
    por_fuente = conn.execute(
        "SELECT fuente, COUNT(*) c FROM licitaciones GROUP BY fuente"
    ).fetchall()
    conn.close()

    return render_template(
        "index.html",
        rows=rows,
        total=total,
        q=q,
        fuente=fuente,
        solo_con_renglones=solo_con_renglones,
        por_fuente=por_fuente,
        shown=len(rows),
    )


@app.route("/licitacion/<int:licitacion_id>")
def detalle(licitacion_id):
    conn = db.get_connection()
    lic = conn.execute("SELECT * FROM licitaciones WHERE id=?", (licitacion_id,)).fetchone()
    if not lic:
        conn.close()
        abort(404)
    items = db.get_items(conn, licitacion_id)
    conn.close()
    return render_template("detalle.html", lic=lic, items=items)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
