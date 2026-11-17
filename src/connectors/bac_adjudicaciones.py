"""Adjudicatarios de BAC (CABA) desde las ordenes de compra PUBLICAS.

BAC no publica las ofertas perdedoras (el cuadro comparativo solo lo ve el
proveedor que oferto, ver bac_ofertas.py), pero SI publica, sin login, la
orden de compra de cada proceso adjudicado: razon social y CUIT del
adjudicatario, importe total y renglones. Eso permite mostrar quien gano y a
que precio en TODOS los procesos adjudicados -- no la comparativa completa.

Flujo (verificado 17-nov-2026, sin login):
  ListarAperturaUltimos30Dias.aspx -> fila con estado "Adjudicado" ->
  VistaPreviaPliegoCiudadano (link "NNN-NNNNN-OC26") -> VerDocumentoContractual.

Los links son postbacks de ASP.NET (sin URL directa), asi que se navega la UI
y se vuelve con go_back (restaura la pagina de la lista donde se estaba).
"""
import re
import time

from playwright.sync_api import sync_playwright

HOME_URL = "https://buenosairescompras.gob.ar/Default.aspx"
URL = "https://buenosairescompras.gob.ar/ListarAperturaUltimos30Dias.aspx"
TABLA = "table#ctl00_CPH1_GridListaPliegos"
FILAS_POR_PAGINA = 10

RE_OC = re.compile(r"^\d+-\d+-OC\d\d$")


def _num_ar(texto: str):
    """'943.944,30' -> 943944.3"""
    try:
        return float(texto.replace(".", "").replace(",", "."))
    except ValueError:
        return None


def extraer_oc(texto: str) -> dict | None:
    """Datos del adjudicatario a partir del texto de VerDocumentoContractual.
    Devuelve None si no se reconoce la estructura."""
    i = texto.find("Datos adjudicatario")
    if i < 0:
        return None
    resto = texto[i:]
    m_prov = re.search(r"Raz[oó]n social:\s*\n+\s*(.+)", resto)
    if not m_prov:
        return None
    m_cuit = re.search(r"N[uú]mero CUIT:\s*\n+\s*([\d-]+)", resto)
    m_total = re.search(r"Importe total\s*\n+\s*([A-Z]{3})\s*\$?\s*([\d.,]+)", resto)
    m_fecha = re.search(r"Fecha autorizaci[oó]n:\s*\n+\s*(\d{2}/\d{2}/\d{4})", texto)
    return {
        "proveedor": m_prov.group(1).strip(),
        "cuit": m_cuit.group(1).strip() if m_cuit else None,
        "monto": _num_ar(m_total.group(2)) if m_total else None,
        "moneda": m_total.group(1) if m_total else None,
        "fecha_oferta": m_fecha.group(1) if m_fecha else None,
        "es_ganadora": True,
    }


def _esperar_lista(page):
    page.wait_for_selector(TABLA, timeout=30000)
    page.wait_for_timeout(1200)  # sin esto a veces se lee la tabla vacia


def _ir_a_pagina(page, pagina: int):
    """Carga la lista desde cero y salta a la pagina pedida."""
    page.goto(HOME_URL, wait_until="domcontentloaded")
    page.goto(URL, wait_until="domcontentloaded")
    _esperar_lista(page)
    if pagina > 1:
        page.evaluate("__doPostBack('ctl00$CPH1$GridListaPliegos', 'Page$" + str(pagina) + "')")
        _esperar_lista(page)


def _filas(page) -> list[tuple[str, str]]:
    """[(numero_proceso, estado)] de la pagina actual de la lista."""
    filas = []
    for tr in page.locator(TABLA).locator("> tbody > tr, > tr").all():
        tds = tr.locator("> td").all()
        if len(tds) < 6:
            continue
        numero = tds[0].inner_text().strip()
        if numero and "-" in numero:
            filas.append((numero, tds[4].inner_text().strip()))
    return filas


def _total_paginas(page) -> int:
    texto = page.locator("text=/Se han encontrado \\(\\d+\\) resultados/").first.inner_text()
    m = re.search(r"\((\d+)\)", texto)
    total = int(m.group(1)) if m else FILAS_POR_PAGINA
    return max(1, -(-total // FILAS_POR_PAGINA))


def _leer_proceso(page, numero: str) -> list[dict]:
    """Abre el proceso (en la pagina de lista actual), lee cada orden de
    compra y deja la pagina de nuevo en la lista."""
    with page.expect_navigation(timeout=30000):
        page.locator(TABLA).get_by_role("link", name=numero, exact=True).click()

    def links_oc():
        return [a for a in page.locator("a").all() if RE_OC.match(a.inner_text().strip())]

    n_oc = len(links_oc())
    adjudicatarios = []
    for j in range(n_oc):
        with page.expect_navigation(timeout=30000):
            links_oc()[j].click()
        dato = extraer_oc(page.inner_text("body"))
        if dato:
            adjudicatarios.append(dato)
        page.go_back(wait_until="domcontentloaded")
    page.go_back(wait_until="domcontentloaded")
    _esperar_lista(page)
    return adjudicatarios


def fetch(conocidos=None, max_procesos: int | None = 150, max_paginas: int | None = None,
          presupuesto_seg: float | None = 1500) -> list[dict]:
    """[{"numero_proceso", "ofertas": [adjudicatario, ...]}] de los procesos
    "Adjudicado" de los ultimos 30 dias que todavia no estan en `conocidos`.
    `max_procesos` acota el trabajo por corrida (el resto queda para la
    siguiente: la ingesta es incremental). `presupuesto_seg` corta la corrida
    por tiempo (el portal es lento y el workflow tiene un tope total)."""
    inicio = time.time()

    def sin_tiempo():
        return presupuesto_seg is not None and time.time() - inicio > presupuesto_seg

    conocidos = set(conocidos or [])
    resultado = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        try:
            _ir_a_pagina(page, 1)
            total = _total_paginas(page)
            if max_paginas:
                total = min(total, max_paginas)
            for pagina in range(1, total + 1):
                if (max_procesos and len(resultado) >= max_procesos) or sin_tiempo():
                    break
                try:
                    if pagina > 1:
                        page.evaluate("__doPostBack('ctl00$CPH1$GridListaPliegos', 'Page$" + str(pagina) + "')")
                        _esperar_lista(page)
                    objetivos = [n for n, e in _filas(page) if e == "Adjudicado" and n not in conocidos]
                except Exception as e:
                    print(f"  ! error leyendo pagina {pagina}: {e}")
                    continue
                for numero in objetivos:
                    if (max_procesos and len(resultado) >= max_procesos) or sin_tiempo():
                        break
                    try:
                        adjudicatarios = _leer_proceso(page, numero)
                    except Exception as e:
                        print(f"  ! {numero}: {str(e)[:120]}")
                        recuperada = False
                        for intento in range(3):  # recuperar la lista donde estabamos
                            try:
                                _ir_a_pagina(page, pagina)
                                recuperada = True
                                break
                            except Exception as e2:
                                print(f"  (recuperando la lista, intento {intento + 1}: {str(e2)[:80]})")
                                page.wait_for_timeout(5000)
                        if not recuperada:
                            print("  ! no se pudo volver a la lista, se corta la corrida")
                            return resultado
                        continue
                    if adjudicatarios:
                        resultado.append({"numero_proceso": numero, "ofertas": adjudicatarios})
                        print(f"  {numero}: {', '.join(a['proveedor'] for a in adjudicatarios)}")
                    conocidos.add(numero)
        finally:
            browser.close()
    return resultado


if __name__ == "__main__":
    import sys

    max_p = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    datos = fetch(max_procesos=max_p, max_paginas=12)
    print(f"{len(datos)} procesos con adjudicatario")
    for d in datos:
        print(d)
