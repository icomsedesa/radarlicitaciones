"""Paso exploratorio para el conector autenticado de comparativas (COMPR.AR
y BAC): inicia sesion con la credencial guardada en /configuracion y
guarda una captura + el HTML de la pantalla resultante en data/explorar/,
para poder mapear la navegacion posterior (buscar un proceso, ver sus
ofertas) sin tener que loguearse a mano cada vez.

IMPORTANTE (seguridad): este script tiene que correrlo una persona de Icom
con acceso legitimo a la cuenta del portal -- nunca lo corre Claude, y
nunca se suma a la ingesta automatica hasta no haber verificado a mano,
con estas capturas, que el flujo de login realmente funciona como se
espera.

Los selectores del primer paso (usuario) estan confirmados contra el HTML
publico de cada portal. Los del segundo paso (password + confirmar) son
una primera aproximacion -- si fallan, el script igual guarda captura y
HTML del estado en el que quedo, para poder ajustarlos.

Uso:
    python -m src.explorar_login comprar_ar
    python -m src.explorar_login bac
"""
import argparse
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

from src import db, secrets_store

SALIDA_DIR = Path(__file__).resolve().parent.parent / "data" / "explorar"


def _obtener_credencial(portal: str):
    conn = db.get_connection()
    row = db.obtener_credencial(conn, portal)
    conn.close()
    if not row or not row["password_cifrada"]:
        print(f"No hay credencial guardada para '{portal}' -- cargala primero en /configuracion.")
        sys.exit(1)
    usuario = row["usuario"]
    password = secrets_store.decrypt(row["password_cifrada"])
    if not password:
        print(f"No se pudo descifrar la credencial de '{portal}' (¿cambio SECRETS_ENCRYPTION_KEY?).")
        sys.exit(1)
    return usuario, password


def _guardar_estado(page, nombre: str):
    SALIDA_DIR.mkdir(parents=True, exist_ok=True)
    png = SALIDA_DIR / f"{nombre}.png"
    html = SALIDA_DIR / f"{nombre}.html"
    try:
        page.screenshot(path=str(png), full_page=True)
        print(f"  guardado: {png}")
    except Exception as e:
        print(f"  ! no se pudo guardar captura: {e}")
    try:
        html.write_text(page.content(), encoding="utf-8")
        print(f"  guardado: {html}")
    except Exception as e:
        print(f"  ! no se pudo guardar HTML: {e}")


def _login_comprar_ar(page, usuario: str, password: str):
    page.goto("https://comprar.gob.ar/Login.aspx", wait_until="domcontentloaded")
    page.fill("#txtUsername_txtTextBox", usuario)
    page.click("#lnkConfirmar")
    page.wait_for_load_state("networkidle")
    _guardar_estado(page, "comprar_ar_1_post_usuario")

    page.wait_for_selector("input[type=password]", timeout=15000)
    page.fill("input[type=password]", password)
    page.keyboard.press("Enter")
    page.wait_for_load_state("networkidle")
    _guardar_estado(page, "comprar_ar_2_post_login")


def _login_bac(page, usuario: str, password: str):
    page.goto("https://buenosairescompras.gob.ar/Default.aspx", wait_until="domcontentloaded")
    page.click("#ctl00_CtrlMenuPortal_lnkIngresar")
    page.wait_for_load_state("networkidle")
    _guardar_estado(page, "bac_1_post_click_ingresar")

    page.wait_for_selector("input[type=text], input[type=email]", timeout=15000)
    # el modal de login de BAC trae usuario y password en la misma pantalla
    # (a diferencia de COMPR.AR, que es en dos pasos) -- se busca el primer
    # campo de texto visible dentro del modal, asumiendo que es el usuario.
    campos_texto = page.locator("input[type=text]:visible, input[type=email]:visible")
    campos_texto.first.fill(usuario)
    page.fill("input[type=password]", password)
    page.keyboard.press("Enter")
    page.wait_for_load_state("networkidle")
    _guardar_estado(page, "bac_2_post_login")


LOGINS = {
    "comprar_ar": _login_comprar_ar,
    "bac": _login_bac,
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("portal", choices=sorted(LOGINS.keys()))
    parser.add_argument("--headless", action="store_true", help="corre sin abrir ventana de navegador")
    args = parser.parse_args()

    usuario, password = _obtener_credencial(args.portal)
    print(f"Iniciando sesion en '{args.portal}' con usuario '{usuario}'...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=args.headless)
        page = browser.new_page()
        try:
            LOGINS[args.portal](page, usuario, password)
            print(f"\nListo. Revisa las capturas en {SALIDA_DIR} y compartilas para armar el siguiente paso")
            print("(buscar un proceso puntual y ver el detalle de sus ofertas).")
        except Exception as e:
            print(f"\n! Alguno de los pasos automaticos fallo: {e}")
            print("  Si tenes el navegador abierto (sin --headless), fijate en que pantalla quedo --")
            print("  si hace falta, termina de loguearte vos a mano ahi mismo antes de cerrar.")
            _guardar_estado(page, f"{args.portal}_error")
        finally:
            if not args.headless:
                input("\nPresiona Enter cuando quieras cerrar el navegador (se va a guardar el estado final antes de cerrar)...")
                _guardar_estado(page, f"{args.portal}_final")
            browser.close()


if __name__ == "__main__":
    main()
