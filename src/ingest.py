"""Orquestador: corre los conectores y carga los resultados normalizados en SQLite.

Uso:
    python -m src.ingest                      # carga completa (comprar_ar full + bac full + pbac 5 paginas)
    python -m src.ingest --rapido              # corrida corta para probar el pipeline
    python -m src.ingest --solo pbac           # solo algunos pasos (ver CLAVES abajo)
    python -m src.ingest --excluir pbac        # todo menos algunos pasos

CLAVES de paso: comprar_ar, bac, pbac, mendoza, pami, pami_ugl,
pami_efectores, pami_actas, el slug de cada municipio (p.ej. muni_moron) y
el grupo "municipios".

Cada fuente registra en `estado_fuentes` si se pudo actualizar; si fallo, el
buscador muestra un aviso al filtrar por ella.
"""
import argparse
import os
import sys

from src import db
from src.connectors import bac, comprar_ar, mendoza, pami, pbac
from src.connectors.municipios import (
    avellaneda, berazategui, chivilcoy, escobar, florencio_varela,
    general_rodriguez, ituzaingo, la_matanza, lanus, lomas_de_zamora, moreno,
    moron, quilmes, san_andres_de_giles, san_isidro, san_miguel, sibom,
    tres_de_febrero, vicente_lopez,
)

# Conectores municipales "simples": basta llamar fetch() sin argumentos.
# (nombre, slug de la fuente en la base, modulo)
# (Los que necesitan parametros especiales -- como SIBOM, por city_id --
# se manejan aparte, mas abajo.)
MUNICIPIOS_SIMPLES = [
    ("San Miguel", "muni_san_miguel", san_miguel),
    ("La Matanza", "muni_la_matanza", la_matanza),
    ("Vicente López", "muni_vicente_lopez", vicente_lopez),
    ("San Andrés de Giles", "muni_san_andres_giles", san_andres_de_giles),
    ("Chivilcoy", "muni_chivilcoy", chivilcoy),
    ("Quilmes", "muni_quilmes", quilmes),
    ("Morón", "muni_moron", moron),
    ("Tres de Febrero", "muni_tres_de_febrero", tres_de_febrero),
    ("Florencio Varela", "muni_florencio_varela", florencio_varela),
    ("Escobar", "muni_escobar", escobar),
    ("Moreno", "muni_moreno", moreno),
    ("Avellaneda", "muni_avellaneda", avellaneda),
    ("Ituzaingó", "muni_ituzaingo", ituzaingo),
    ("Lomas de Zamora", "muni_lomas_de_zamora", lomas_de_zamora),
    ("Berazategui", "muni_berazategui", berazategui),
    ("San Isidro", "muni_san_isidro", san_isidro),
    ("General Rodríguez", "muni_general_rodriguez", general_rodriguez),
    ("Lanús", "muni_lanus", lanus),
]

# Municipios que reutilizan el conector generico de SIBOM (boletin oficial
# compartido de la Provincia), parametrizados por city_id.
MUNICIPIOS_SIBOM = [
    ("Campana", 18, "muni_campana", "Municipalidad de Campana", "Municipio de Campana (GBA)"),
    ("General San Martín", 57, "muni_gral_san_martin", "Municipalidad de General San Martín", "Municipio de General San Martín (GBA norte)"),
    ("Capitán Sarmiento", 20, "muni_capitan_sarmiento", "Municipalidad de Capitán Sarmiento", "Municipio de Capitán Sarmiento (interior bonaerense)"),
    ("San Vicente", 119, "muni_san_vicente", "Municipalidad de San Vicente", "Municipio de San Vicente (GBA sur)"),
]


def run(comprar_limit=None, bac_limit=None, pbac_pages=5, municipios=True, solo=None, excluir=None):
    conn = db.get_connection()
    solo = set(solo or [])
    excluir = set(excluir or [])
    errores = []
    total = 0

    def activo(clave, grupo=None):
        claves = {clave, grupo} - {None}
        if solo and not (claves & solo):
            return False
        return not (claves & excluir)

    def paso(titulo, clave, slugs, fn, grupo=None):
        """Corre una fuente aislada: si falla, las demas igual corren (antes
        una excepcion cortaba toda la ingesta). Registra en estado_fuentes
        si se pudo actualizar, para avisar en el buscador."""
        nonlocal total
        if not activo(clave, grupo):
            return
        print(f"== {titulo} ==")
        try:
            n = fn()
            total += n or 0
            db.registrar_estado_fuente(conn, slugs, ok=True)
        except Exception as e:
            print(f"  ! error: {e!r}")
            errores.append(titulo)
            db.registrar_estado_fuente(conn, slugs, ok=False, mensaje=str(e))

    def cargar(fetch):
        def _f():
            n = db.upsert_many(conn, fetch())
            print(f"  {n} filas cargadas")
            return n
        return _f

    def cargar_con_items(fetch):
        def _f():
            n, n_items = db.upsert_with_items(conn, fetch())
            print(f"  {n} filas cargadas ({n_items} renglones)")
            return n
        return _f

    paso("COMPR.AR (Nación)", "comprar_ar", ["comprar_ar"],
         cargar(lambda: comprar_ar.fetch(limit=comprar_limit)))
    paso("BAC (CABA)", "bac", ["bac"],
         cargar_con_items(lambda: bac.fetch(limit=bac_limit)))
    paso("PBAC (Provincia de Buenos Aires)", "pbac", ["pbac"],
         cargar(lambda: pbac.fetch(max_pages=pbac_pages)))
    paso("Mendoza (Provincia y dependencias)", "mendoza", ["mendoza"],
         cargar_con_items(mendoza.fetch))
    paso("PAMI (Nivel Central)", "pami", ["pami"], cargar(pami.fetch))
    paso("PAMI (UGL, 38 unidades en todo el país)", "pami_ugl", ["pami_ugl"], cargar(pami.fetch_ugl))
    paso("PAMI (Efectores Sanitarios Propios)", "pami_efectores", ["pami_efectores"],
         cargar(pami.fetch_efectores))

    def actas():
        # historico mas amplio que el listado de vigentes -- si el proceso
        # todavia no estaba en la base (ya cerrado, fuera del listado de
        # "vigentes hoy"), se crea aca con lo que trae el acta.
        # `conocidos` evita re-descargar/parsear el PDF de actas que ya se
        # procesaron en una corrida anterior (una vez publicada, un acta no
        # cambia) -- sin esto, esta ingesta crecia sin limite dia a dia.
        conocidos = db.procesos_con_ofertas(conn, "pami")
        actas_con_ofertas = pami.fetch_todas_las_ofertas(conocidos=conocidos)
        n_ofertas = 0
        for row in actas_con_ofertas:
            ofertas = row.pop("ofertas")
            db.upsert_many(conn, [row])
            if db.set_ofertas(conn, "pami", row["numero_proceso"], ofertas):
                n_ofertas += len(ofertas)
        print(f"  {len(actas_con_ofertas)} procesos con ofertas cargadas ({n_ofertas} ofertas)")
        return 0

    paso("PAMI (comparativas: actas de apertura)", "pami_actas", [], actas)

    if municipios:
        for nombre, slug, conector in MUNICIPIOS_SIMPLES:
            paso(f"Municipio de {nombre}", slug, [slug], cargar(conector.fetch), grupo="municipios")

        for nombre, city_id, fuente, organismo, jurisdiccion in MUNICIPIOS_SIBOM:
            paso(
                f"Municipio de {nombre} (vía SIBOM)", fuente, [fuente],
                cargar(lambda c=city_id, f=fuente, o=organismo, j=jurisdiccion:
                       sibom.fetch(city_id=c, fuente=f, organismo=o, jurisdiccion=j)),
                grupo="municipios",
            )

    conn.close()
    print(f"\nTotal: {total} licitaciones en {db.DB_PATH}")
    if errores:
        print(f"Fuentes con error: {', '.join(errores)}")
    return errores


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--rapido", action="store_true", help="corrida corta para probar el pipeline")
    parser.add_argument("--solo", default="", help="solo estos pasos (separados por coma)")
    parser.add_argument("--excluir", default="", help="todos menos estos pasos (separados por coma)")
    args = parser.parse_args()
    solo = [x.strip() for x in args.solo.split(",") if x.strip()]
    excluir = [x.strip() for x in args.excluir.split(",") if x.strip()]

    try:
        if args.rapido:
            run(comprar_limit=500, bac_limit=500, pbac_pages=3, solo=solo, excluir=excluir)
        else:
            run(solo=solo, excluir=excluir)
        # Un portal caido ya queda avisado en el buscador (estado_fuentes);
        # no se marca el job como fallido para no dejarlo en rojo todos los
        # dias por una fuente externa que no controlamos.
        codigo = 0
    except BaseException as e:
        print(f"! la ingesta fallo: {e!r}")
        codigo = 1
    # os._exit: el cliente libsql deja un hilo asyncio no-daemon; ante una
    # excepcion el proceso quedaba colgado hasta el timeout del workflow
    # (2 h) en vez de terminar.
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(codigo)
