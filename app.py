"""Buscador simple (PoC) sobre la base normalizada. Ejecutar: python app.py"""
import base64
import os
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode

from dotenv import load_dotenv
from flask import Flask, abort, flash, redirect, render_template, request, session, url_for

from src import db, secrets_store

load_dotenv()

app = Flask(__name__)

# clave de sesion de Flask (firma las cookies de sesion) -- NO es la clave
# que cifra las contraseñas de portales (esa es SECRETS_ENCRYPTION_KEY, en
# secrets_store.py). En deploys sin filesystem persistente entre
# ejecuciones (Vercel) hay que definir FLASK_SECRET_KEY como variable de
# entorno -- si no, cada arranque frío generaria una clave distinta y
# invalidaria las sesiones activas. En local, sin esa variable, se
# autogenera y persiste en disco (alcanza para desarrollo).
_flask_secret_env = os.environ.get("FLASK_SECRET_KEY")
if _flask_secret_env:
    app.secret_key = base64.urlsafe_b64decode(_flask_secret_env)
else:
    _FLASK_SECRET_PATH = Path(__file__).resolve().parent / "data" / ".flask_secret.key"
    _FLASK_SECRET_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not _FLASK_SECRET_PATH.exists():
        _FLASK_SECRET_PATH.write_bytes(os.urandom(32))
    app.secret_key = _FLASK_SECRET_PATH.read_bytes()

# contraseña para acceder a /configuracion (donde se cargan credenciales de
# portales) -- se define por variable de entorno, nunca queda en el codigo.
# Si no esta configurada, /configuracion queda inaccesible (falla cerrado).
ADMIN_PASSWORD = os.environ.get("RADAR_ADMIN_PASSWORD")

PAGE_SIZE = 50

PORTALES_CONFIGURABLES = [
    ("comprar_ar", "COMPR.AR (Nación)", "https://comprar.gob.ar/"),
    ("bac", "BAC (CABA)", "https://buenosairescompras.gob.ar/"),
]

FUENTES = [
    ("comprar_ar", "COMPR.AR (Nación)"),
    ("bac", "BAC (CABA)"),
    ("pbac", "PBAC (Provincia)"),
    ("mendoza", "Mendoza (Provincia)"),
    ("mendoza_osep", "Mendoza (OSEP)"),
    ("pami", "PAMI"),
    ("pami_ugl", "PAMI (UGL)"),
    ("pami_efectores", "PAMI (Efectores)"),
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
    ("pami", "PAMI", "INSSJP — Nivel Central. Incluye comparativas públicas (Actas de Apertura con todas las ofertas recibidas)"),
    ("pami_ugl", "PAMI (UGL)", "INSSJP — 38 Unidades de Gestión Local en todo el país"),
    ("pami_efectores", "PAMI (Efectores)", "INSSJP — Gerencia de Efectores Sanitarios Propios (hospitales operados directamente por PAMI)"),
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
    return request.path + (f"?{qs}" if qs else "")


app.jinja_env.globals["url_with"] = _url_with


def _fuente_clase(fuente: str) -> str:
    if fuente.startswith("mendoza"):
        return "mendoza"
    if fuente.startswith("pami"):
        return "pami"
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
    vista = "renglones" if request.args.get("vista") == "renglones" else "documentos"
    try:
        pagina = max(1, int(request.args.get("pagina", "1")))
    except ValueError:
        pagina = 1

    conn = db.get_connection()

    # filtros a nivel del proceso -- se aplican igual en las dos vistas
    # (documentos y renglones), porque un renglon "pertenece" al proceso
    # que lo trae (fuente, apertura, urgencia, etc. son del proceso).
    where = []
    params = {}
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
        # por defecto solo se muestran procesos con apertura futura -- los
        # cerrados y los que no tienen fecha cargada quedan afuera salvo
        # que el usuario pida ver el historial completo.
        where.append("base.urgencia IN ('rojo', 'amarillo', 'verde')")

    # con apertura futura primero (mas proxima primero), despues el resto.
    # OJO: "estado" no sirve como criterio aca -- su significado varia por
    # fuente (el "active" de BAC no implica que siga vigente para ofertar,
    # a diferencia del "Publicado" de COMPR.AR). La fecha real es lo unico
    # comparable entre las tres fuentes.
    order_sql = "CASE WHEN base.urgencia IN ('rojo','amarillo','verde') THEN 0 ELSE 1 END, base.fecha_apertura ASC"

    if vista == "renglones":
        # en esta vista lo que importa es el renglon (el articulo puntual
        # que se puede o no ofertar) -- el texto libre busca en el propio
        # renglon (descripcion/codigo) o por numero de proceso exacto, no
        # en el titulo/organismo del proceso (que traeria renglones sin
        # relacion real con la busqueda).
        where_renglon = list(where)
        if q:
            where_renglon.append("(i.descripcion LIKE :q OR i.codigo_item LIKE :q OR base.numero_proceso LIKE :q)")
            params["q"] = f"%{q}%"
        where_sql = f"WHERE {' AND '.join(where_renglon)}" if where_renglon else ""

        query = f"""
            WITH base AS (
                SELECT *, {URGENCIA_CASE} AS urgencia FROM licitaciones
            )
            SELECT
                i.id AS item_id, i.numero_renglon, i.codigo_item,
                i.descripcion AS item_descripcion, i.cantidad, i.unidad,
                i.clasificacion,
                base.id, base.fuente, base.numero_proceso, base.titulo,
                base.organismo, base.fecha_apertura, base.urgencia,
                base.estado, base.url
            FROM licitacion_items i
            JOIN base ON base.id = i.licitacion_id
            {where_sql}
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
            SELECT COUNT(*) c
            FROM licitacion_items i
            JOIN base ON base.id = i.licitacion_id
            {where_sql}
            """,
            params,
        ).fetchone()["c"]
    else:
        where_doc = list(where)
        if q:
            where_doc.append("(base.titulo LIKE :q OR base.descripcion LIKE :q OR base.organismo LIKE :q OR base.numero_proceso LIKE :q)")
            params["q"] = f"%{q}%"
        where_sql = f"WHERE {' AND '.join(where_doc)}" if where_doc else ""
        having_sql = "HAVING COUNT(i.id) > 0" if solo_con_renglones else ""

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
        vista=vista,
        fuentes=FUENTES,
        jurisdicciones=JURISDICCIONES,
        por_fuente=por_fuente,
        shown=len(rows),
        pagina=pagina,
        total_paginas=total_paginas,
    )


MESES_VALIDOS = (12, 6, 3)
MESES_DEFAULT = 12


def _comparativas():
    """Vista cruzada de licitacion_ofertas (a diferencia del detalle de una
    licitacion puntual): todas las ofertas de todos los proveedores, para
    poder buscar por competidor o por rubro sin tener que entrar
    licitacion por licitacion. Acotada por default a los ultimos 12 meses
    (botones 12/6/3 meses) -- comparativas mas viejas pierden utilidad para
    cotizar y solo suman ruido."""
    q = request.args.get("q", "").strip()
    try:
        pagina = max(1, int(request.args.get("pagina", "1")))
    except ValueError:
        pagina = 1
    try:
        meses = int(request.args.get("meses", MESES_DEFAULT))
    except ValueError:
        meses = MESES_DEFAULT
    if meses not in MESES_VALIDOS:
        meses = MESES_DEFAULT

    conn = db.get_connection()
    condiciones = ["l.fecha_apertura >= :desde"]
    params = {"desde": (datetime.now() - timedelta(days=meses * 30.44)).isoformat()}
    if q:
        condiciones.append(
            "(o.proveedor LIKE :q OR l.titulo LIKE :q "
            "OR l.organismo LIKE :q OR l.numero_proceso LIKE :q)"
        )
        params["q"] = f"%{q}%"
    where = "WHERE " + " AND ".join(condiciones)

    query = f"""
        SELECT o.id AS oferta_id, o.proveedor, o.cuit, o.monto, o.moneda,
               o.fecha_oferta, o.es_ganadora,
               l.id AS licitacion_id, l.fuente, l.numero_proceso, l.titulo,
               l.organismo, l.fecha_apertura
        FROM licitacion_ofertas o
        JOIN licitaciones l ON l.id = o.licitacion_id
        {where}
        ORDER BY l.fecha_apertura DESC, o.monto ASC
        LIMIT {PAGE_SIZE} OFFSET {(pagina - 1) * PAGE_SIZE}
    """
    rows = [dict(r) for r in conn.execute(query, params).fetchall()]

    total = conn.execute(
        f"""
        SELECT COUNT(*) c
        FROM licitacion_ofertas o
        JOIN licitaciones l ON l.id = o.licitacion_id
        {where}
        """,
        params,
    ).fetchone()["c"]
    conn.close()

    total_paginas = max(1, -(-total // PAGE_SIZE))
    return dict(
        rows=rows, total=total, q=q, pagina=pagina, total_paginas=total_paginas,
        shown=len(rows), meses=meses, meses_validos=MESES_VALIDOS,
    )


@app.route("/comparativas")
def comparativas():
    return render_template("comparativas.html", **_comparativas())


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
    ofertas = db.get_ofertas(conn, licitacion_id)
    conn.close()
    return render_template("detalle.html", lic=lic, items=items, ofertas=ofertas)


def _autenticado():
    return ADMIN_PASSWORD and session.get("autenticado") is True


@app.route("/login", methods=["GET", "POST"])
def login():
    if not ADMIN_PASSWORD:
        return (
            "Configuración deshabilitada: falta definir la variable de entorno "
            "RADAR_ADMIN_PASSWORD antes de iniciar la app.",
            503,
        )
    if request.method == "POST":
        if request.form.get("password") == ADMIN_PASSWORD:
            session["autenticado"] = True
            return redirect(url_for("configuracion"))
        flash("Contraseña incorrecta.")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.pop("autenticado", None)
    return redirect(url_for("index"))


@app.route("/configuracion", methods=["GET", "POST"])
def configuracion():
    if not _autenticado():
        return redirect(url_for("login"))

    conn = db.get_connection()
    if request.method == "POST":
        accion = request.form.get("accion")
        portal = request.form.get("portal")
        if accion == "guardar":
            usuario = request.form.get("usuario", "").strip()
            password = request.form.get("password", "")
            if usuario and password:
                db.guardar_credencial(conn, portal, usuario, secrets_store.encrypt(password))
                flash(f"Credencial de {portal} guardada.")
        elif accion == "eliminar":
            db.eliminar_credencial(conn, portal)
            flash(f"Credencial de {portal} eliminada.")

    guardadas = {r["portal"]: r for r in db.listar_credenciales(conn)}
    conn.close()
    return render_template(
        "configuracion.html", portales=PORTALES_CONFIGURABLES, guardadas=guardadas
    )


if __name__ == "__main__":
    app.run(debug=True, port=5000)
