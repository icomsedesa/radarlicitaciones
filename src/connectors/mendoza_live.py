"""Buscadores en vivo de portales COMPR.AR de Mendoza (procesos con
Estado = "Publicado", es decir realmente abiertos ahora mismo).

Dos portales, mismo software (el mismo sistema COMPRAR que usa la Nacion
en comprar.gob.ar -- mismos ids de control ASP.NET
`ctl00_CPH1_ddlEstadoProceso`/`ctl00_CPH1_GridListaPliegos`, mismo valor
"Publicado"=6, misma paginacion via __doPostBack('...GridListaPliegos',
'Page$N')), pero deployments/versiones distintas:

  - **Provincia** (comprar.mendoza.gov.ar, v1.0.5): grilla de 8 columnas,
    agrega el monto estimado al final.
  - **OSEP** (comprarosep.mendoza.gov.ar, v5.0 -- la obra social de
    empleados publicos, muy relevante para IcomSalud por ser insumos
    medicos): grilla de 7 columnas, igual a la nacional, sin monto.

En ambos casos la pagina de busqueda NO se puede pedir directo -- redirige
al home si no se llega via el boton "BUSQUEDA DE PROCESOS" del home
(`__doPostBack('...CtrlBusquedasHome$btnBusquedaProcesos')`), asi que hace
falta ese paso previo de "calentamiento" de sesion.

Complementa a `mendoza.py` (datos historicos con adjudicaciones via el
dataset OCDS abierto de la Provincia -- OSEP no publica un dataset
abierto equivalente, solo tiene este buscador en vivo).
"""
import re
from datetime import datetime

from playwright.sync_api import sync_playwright

ESTADO_PUBLICADO = "6"
FILAS_POR_PAGINA = 10


def _parse_fecha(text: str):
    text = text.strip().replace("Hrs.", "").strip()
    try:
        return datetime.strptime(text, "%d/%m/%Y %H:%M").isoformat()
    except ValueError:
        return None


def _parse_monto(text: str):
    text = (text or "").strip().replace(".", "").replace(",", ".")
    try:
        valor = float(text)
        return valor if valor > 0 else None
    except ValueError:
        return None


def _parse_rows(page, fuente: str, jurisdiccion: str, tiene_monto: bool, url_busqueda: str) -> list[dict]:
    table = page.locator("table#ctl00_CPH1_GridListaPliegos")
    trs = table.locator("> tbody > tr, > tr").all()
    min_cols = 8 if tiene_monto else 7
    items = []
    for tr in trs:
        cls = tr.get_attribute("class") or ""
        if "pagination" in cls:
            continue
        tds = tr.locator("> td").all()
        if len(tds) < min_cols:
            continue
        numero = tds[0].inner_text().strip()
        if not numero or "-" not in numero:
            continue
        dependencia = tds[5].inner_text().strip()
        unidad = tds[6].inner_text().strip()
        items.append(
            {
                "fuente": fuente,
                "numero_proceso": numero,
                "titulo": tds[1].inner_text().strip(),
                "descripcion": None,
                "organismo": f"{dependencia} — {unidad}" if unidad else dependencia,
                "jurisdiccion": jurisdiccion,
                "tipo_procedimiento": tds[2].inner_text().strip(),
                "fecha_publicacion": None,
                "fecha_apertura": _parse_fecha(tds[3].inner_text()),
                "monto_estimado": _parse_monto(tds[7].inner_text()) if tiene_monto else None,
                "moneda": "ARS",
                "estado": tds[4].inner_text().strip(),
                "proveedor_adjudicado": None,
                "monto_adjudicado": None,
                "url": url_busqueda,
            }
        )
    return items


def _total_paginas(page) -> int:
    heading = page.locator("text=/Se han encontrado \\(\\d+\\) resultados/").first
    text = heading.inner_text()
    m = re.search(r"\((\d+)\)", text)
    total = int(m.group(1)) if m else FILAS_POR_PAGINA
    return max(1, -(-total // FILAS_POR_PAGINA))


def _fetch_portal(
    home_url: str, url_busqueda: str, fuente: str, jurisdiccion: str,
    tiene_monto: bool, max_paginas: int | None,
) -> list[dict]:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        try:
            page.goto(home_url, wait_until="load", timeout=45000)
            page.wait_for_timeout(1200)
            # la pagina de busqueda redirige al home si no se entra por este
            # boton -- deja algo de estado de sesion/postback armado.
            with page.expect_navigation(timeout=20000):
                page.evaluate(
                    "__doPostBack('ctl00$CPH1$CtrlBusquedasHome$btnBusquedaProcesos', '')"
                )
            page.wait_for_load_state("load")
            page.wait_for_timeout(1000)

            page.select_option("#ctl00_CPH1_ddlEstadoProceso", ESTADO_PUBLICADO)
            page.evaluate("__doPostBack('ctl00$CPH1$btnListarPliegoAvanzado', '')")
            page.wait_for_selector("table#ctl00_CPH1_GridListaPliegos", timeout=20000)
            page.wait_for_timeout(1000)

            resultados = _parse_rows(page, fuente, jurisdiccion, tiene_monto, url_busqueda)
            total_paginas = _total_paginas(page)
            if max_paginas:
                total_paginas = min(total_paginas, max_paginas)

            pagina = 2
            while pagina <= total_paginas:
                try:
                    page.evaluate(
                        "__doPostBack('ctl00$CPH1$GridListaPliegos', 'Page$" + str(pagina) + "')"
                    )
                    page.wait_for_timeout(1500)
                    page.wait_for_selector("table#ctl00_CPH1_GridListaPliegos", timeout=15000)
                    resultados.extend(_parse_rows(page, fuente, jurisdiccion, tiene_monto, url_busqueda))
                except Exception as e:
                    print(f"  ! error en pagina {pagina}: {e}")
                pagina += 1

            return resultados
        finally:
            browser.close()


def fetch(max_paginas: int | None = None) -> list[dict]:
    """Portal provincial (todas las dependencias -- ministerios, hospitales,
    areas departamentales de salud, poder judicial, etc.)."""
    return _fetch_portal(
        home_url="https://comprar.mendoza.gov.ar/",
        url_busqueda="https://comprar.mendoza.gov.ar/BuscarAvanzado2.aspx",
        fuente="mendoza",
        jurisdiccion="Provincia de Mendoza",
        tiene_monto=True,
        max_paginas=max_paginas,
    )


def fetch_osep(max_paginas: int | None = None) -> list[dict]:
    """OSEP (Obra Social de Empleados Publicos de Mendoza) -- portal propio,
    deployment separado del provincial. Muy relevante para IcomSalud:
    compra insumos medicos directamente (cateteres, stents, camillas,
    etc.), no solo servicios administrativos."""
    return _fetch_portal(
        home_url="https://comprarosep.mendoza.gov.ar/",
        url_busqueda="https://comprarosep.mendoza.gov.ar/BuscarAvanzado.aspx",
        fuente="mendoza_osep",
        jurisdiccion="Provincia de Mendoza — OSEP",
        tiene_monto=False,
        max_paginas=max_paginas,
    )


if __name__ == "__main__":
    import sys

    max_p = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    data = fetch(max_paginas=max_p)
    print(f"{len(data)} licitaciones publicadas (abiertas) encontradas -- Provincia")
    for row in data[:3]:
        print(row)
    data_osep = fetch_osep(max_paginas=max_p)
    print(f"{len(data_osep)} licitaciones publicadas (abiertas) encontradas -- OSEP")
    for row in data_osep[:3]:
        print(row)
