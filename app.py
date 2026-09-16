"""Buscador simple (PoC) sobre la base normalizada. Ejecutar: python app.py"""
from flask import Flask, render_template, request

from src import db

app = Flask(__name__)

PAGE_SIZE = 50


@app.route("/")
def index():
    q = request.args.get("q", "").strip()
    fuente = request.args.get("fuente", "").strip()

    conn = db.get_connection()
    where = []
    params = {}

    if q:
        where.append("(titulo LIKE :q OR descripcion LIKE :q OR organismo LIKE :q)")
        params["q"] = f"%{q}%"
    if fuente:
        where.append("fuente = :fuente")
        params["fuente"] = fuente

    where_sql = f"WHERE {' AND '.join(where)}" if where else ""

    rows = conn.execute(
        f"""
        SELECT * FROM licitaciones
        {where_sql}
        ORDER BY fecha_apertura DESC
        LIMIT {PAGE_SIZE}
        """,
        params,
    ).fetchall()

    total = conn.execute(f"SELECT COUNT(*) c FROM licitaciones {where_sql}", params).fetchone()["c"]
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
        por_fuente=por_fuente,
        shown=len(rows),
    )


if __name__ == "__main__":
    app.run(debug=True, port=5000)
