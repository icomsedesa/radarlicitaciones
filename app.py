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
    ("mendoza", "Mendoza (Provincia)"),
    ("mendoza_osep", "Mendoza (OSEP)"),
    ("muni_san_miguel", "San Miguel"),
    ("muni_la_matanza", "La Matanza"),
    ("muni_campana", "Campana"),
    ("muni_vicente_lopez", "Vicente López"),
    ("muni_san_andres_giles", "San Andrés de Giles"),
    ("muni_chivilcoy", "Chivilcoy"),
    ("muni_quilmes", "Quilmes"),
    ("muni_moron", "Morón"),
    ("muni_tres_de_febrero", "Tres de Febrero"),
    ("muni_florencio_varela", "Florencio Varela"),
    ("muni_escobar", "Escobar"),
    ("muni_moreno", "Moreno"),
    ("muni_avellaneda", "Avellaneda"),
    ("muni_ituzaingo", "Ituzaingó"),
    ("muni_lomas_de_zamora", "Lomas de Zamora"),
    ("muni_berazategui", "Berazategui"),
    ("muni_gral_san_martin", "General San Martín"),
    ("muni_capitan_sarmiento", "Capitán Sarmiento"),
    ("muni_san_vicente", "San Vicente"),
    ("muni_san_isidro", "San Isidro"),
    ("muni_general_rodriguez", "General Rodríguez"),
    ("muni_lanus", "Lanús"),
]

# (fuente, nombre, descripcion) para el modal "Jurisdicciones adheridas" --
# un solo lugar para mantener al sumar fuentes nuevas.
JURISDICCIONES = [
    ("comprar_ar", "COMPR.AR", "Nación — bienes y servicios (ONC)"),
    ("bac", "BAC", "Ciudad Autónoma de Buenos Aires"),
    ("pbac", "PBAC", "Provincia de Buenos Aires"),
    ("mendoza", "Mendoza", "Provincia de Mendoza y dependencias (hospitales, ministerios, áreas de salud)"),
    ("mendoza_osep", "Mendoza (OSEP)", "Obra Social de Empleados Públicos de Mendoza — insumos médicos"),
    ("muni_san_miguel", "San Miguel", "Municipio (GBA norte)"),
    ("muni_la_matanza", "La Matanza", "Municipio (GBA oeste)"),
    ("muni_campana", "Campana", "Municipio (GBA norte, vía SIBOM)"),
    ("muni_vicente_lopez", "Vicente López", "Municipio (GBA norte)"),
    ("muni_san_andres_giles", "San Andrés de Giles", "Municipio (interior bonaerense)"),
    ("muni_chivilcoy", "Chivilcoy", "Municipio (interior bonaerense)"),
    ("muni_quilmes", "Quilmes", "Municipio (GBA sur)"),
    ("muni_moron", "Morón", "Municipio (GBA oeste)"),
    ("muni_tres_de_febrero", "Tres de Febrero", "Municipio (GBA oeste)"),
    ("muni_florencio_varela", "Florencio Varela", "Municipio (GBA sur)"),
    ("muni_escobar", "Escobar", "Municipio (GBA norte)"),
    ("muni_moreno", "Moreno", "Municipio (GBA oeste)"),
    ("muni_avellaneda", "Avellaneda", "Municipio (GBA sur)"),
    ("muni_ituzaingo", "Ituzaingó", "Municipio (GBA oeste)"),
    ("muni_lomas_de_zamora", "Lomas de Zamora", "Municipio (GBA sur)"),
    ("muni_berazategui", "Berazategui", "Municipio (GBA sur)"),
    ("muni_gral_san_martin", "General San Martín", "Municipio (GBA norte, vía SIBOM)"),
    ("muni_capitan_sarmiento", "Capitán Sarmiento", "Municipio (interior bonaerense, vía SIBOM)"),
    ("muni_san_vicente", "San Vicente", "Municipio (GBA sur, vía SIBOM)"),
    ("muni_san_isidro", "San Isidro", "Municipio (GBA norte)"),
    ("muni_general_rodriguez", "General Rodríguez", "Municipio (GBA oeste)"),
    ("muni_lanus", "Lanús", "Municipio (GBA sur)"),
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


def _fuente_clase(fuente: str) -> str:
    if fuente.startswith("mendoza"):
        return "mendoza"
    if fuente in ("comprar_ar", "bac", "pbac"):
        return fuente.replace("_ar", "")
    return "muni"


app.jinja_env.globals["fuente_clase"] = _fuente_clase


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
    dias = int(horas // 24)
    if dias > 730:
        # el CSV masivo de COMPR.AR tiene fechas placeholder ("2099", "3015")
        # que no son aperturas reales -- se muestran acotadas, no como dato literal
        return f"+{dias // 365} años"
    return f"{dias} días"


def _buscar():
    q = request.args.get("q", "").strip()
    fuente = request.args.get("fuente", "").strip()
    solo_con_renglones = request.args.get("renglones", "") == "1"
    solo_vigentes = request.args.get("vigentes", "") == "1"
    urgencia = request.args.get("urgencia", "").strip()
    apertura_desde = request.args.get("desde", "").strip()
    apertura_hasta = request.args.get("hasta", "").strip()
    mostrar_historial = request.args.get("historial", "") == "1"
    try:
        pagina = max(1, int(request.args.get("pagina", "1")))
    except ValueError:
        pagina = 1

    conn = db.get_connection()
    where = []
    params = {}

    if q:
        where.append("(base.titulo LIKE :q OR base.descripcion LIKE :q OR base.organismo LIKE :q OR base.numero_proceso LIKE :q)")
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
    if not mostrar_historial:
        # por defecto solo se muestran licitaciones con apertura futura --
        # las cerradas y las que no tienen fecha cargada quedan afuera
        # salvo que el usuario pida ver el historial completo.
        where.append("base.urgencia IN ('rojo', 'amarillo', 'verde')")

    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    having_sql = "HAVING COUNT(i.id) > 0" if solo_con_renglones else ""
    # con apertura futura primero (mas proxima primero), despues el resto.
    # OJO: "estado" no sirve como criterio aca -- su significado varia por
    # fuente (el "active" de BAC no implica que siga vigente para ofertar,
    # a diferencia del "Publicado" de COMPR.AR). La fecha real es lo unico
    # comparable entre las tres fuentes.
    order_sql = "CASE WHEN base.urgencia IN ('rojo','amarillo','verde') THEN 0 ELSE 1 END, base.fecha_apertura ASC"

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
        LIMIT {PAGE_SIZE} OFFSET {(pagina - 1) * PAGE_SIZE}
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

    total_paginas = max(1, -(-total // PAGE_SIZE))  # ceil division

    return dict(
        rows=rows,
        total=total,
        q=q,
        fuente=fuente,
        solo_con_renglones=solo_con_renglones,
        solo_vigentes=solo_vigentes,
        urgencia=urgencia,
        apertura_desde=apertura_desde,
        apertura_hasta=apertura_hasta,
        mostrar_historial=mostrar_historial,
        fuentes=FUENTES,
        jurisdicciones=JURISDICCIONES,
        por_fuente=por_fuente,
        shown=len(rows),
        pagina=pagina,
        total_paginas=total_paginas,
    )


@app.route("/")
def index():
    ctx = _buscar()
    if request.headers.get("X-Requested-With") == "fetch":
        return render_template("_resultados.html", **ctx)
    return render_template("index.html", **ctx)


@app.route("/inicio")
def inicio():
    conn = db.get_connection()

    total_vigentes = conn.execute(
        f"""
        WITH base AS (SELECT *, {URGENCIA_CASE} AS urgencia FROM licitaciones)
        SELECT COUNT(*) c FROM base WHERE urgencia IN ('rojo', 'amarillo', 'verde')
        """
    ).fetchone()["c"]

    ultima_actualizacion = conn.execute(
        "SELECT MAX(actualizado_en) m FROM licitaciones"
    ).fetchone()["m"]

    por_fuente_vigentes = conn.execute(
        f"""
        WITH base AS (SELECT *, {URGENCIA_CASE} AS urgencia FROM licitaciones)
        SELECT fuente, COUNT(*) c FROM base
        WHERE urgencia IN ('rojo', 'amarillo', 'verde')
        GROUP BY fuente ORDER BY c DESC
        """
    ).fetchall()

    por_urgencia_rows = conn.execute(
        f"""
        WITH base AS (SELECT *, {URGENCIA_CASE} AS urgencia FROM licitaciones)
        SELECT urgencia, COUNT(*) c FROM base
        WHERE urgencia IN ('rojo', 'amarillo', 'verde')
        GROUP BY urgencia
        """
    ).fetchall()
    por_urgencia = {"rojo": 0, "amarillo": 0, "verde": 0}
    por_urgencia.update({r["urgencia"]: r["c"] for r in por_urgencia_rows})

    conn.close()

    nombres_fuente = dict(FUENTES)
    por_fuente_vigentes = [
        {"fuente": r["fuente"], "nombre": nombres_fuente.get(r["fuente"], r["fuente"]), "cantidad": r["c"]}
        for r in por_fuente_vigentes
    ]

    return render_template(
        "inicio.html",
        total_vigentes=total_vigentes,
        ultima_actualizacion=ultima_actualizacion,
        por_fuente_vigentes=por_fuente_vigentes,
        por_urgencia=por_urgencia,
        jurisdicciones=JURISDICCIONES,
    )


@app.route("/api/contar")
def api_contar():
    q = request.args.get("q", "").strip()
    if not q:
        return {"count": 0}
    conn = db.get_connection()
    count = conn.execute(
        f"""
        WITH base AS (SELECT *, {URGENCIA_CASE} AS urgencia FROM licitaciones)
        SELECT COUNT(*) c FROM base
        WHERE base.urgencia IN ('rojo', 'amarillo', 'verde')
          AND (titulo LIKE :q OR descripcion LIKE :q OR organismo LIKE :q OR numero_proceso LIKE :q)
        """,
        {"q": f"%{q}%"},
    ).fetchone()["c"]
    conn.close()
    return {"count": count}


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
