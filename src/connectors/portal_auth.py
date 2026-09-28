"""Login autenticado en COMPR.AR/BAC, compartido entre los conectores de
comparativas (comprar_ar_ofertas.py, bac_ofertas.py) y src/explorar_login.py.

Selectores verificados contra capturas reales del login logueandose con la
cuenta de IcomSalud (25-sep-2026 / 28-sep-2026).
"""
from src import db, secrets_store


def obtener_credencial(portal: str):
    """Usuario + password ya descifrada para `portal` ('comprar_ar' o
    'bac'), leidos de la tabla credenciales_portal. Lanza RuntimeError si
    no hay nada guardado en /configuracion."""
    conn = db.get_connection()
    row = db.obtener_credencial(conn, portal)
    conn.close()
    if not row or not row["password_cifrada"]:
        raise RuntimeError(f"No hay credencial guardada para '{portal}' -- cargala en /configuracion.")
    usuario = row["usuario"]
    password = secrets_store.decrypt(row["password_cifrada"])
    if not password:
        raise RuntimeError(f"No se pudo descifrar la credencial de '{portal}' (¿cambio SECRETS_ENCRYPTION_KEY?).")
    return usuario, password


def login_comprar_ar(page, usuario: str, password: str):
    page.goto("https://comprar.gob.ar/Login.aspx", wait_until="domcontentloaded")
    page.fill("#txtUsername_txtTextBox", usuario)
    page.click("#lnkConfirmar")
    page.wait_for_load_state("networkidle")

    page.wait_for_selector("input[type=password]", timeout=15000)
    page.fill("input[type=password]", password)
    page.keyboard.press("Enter")
    page.wait_for_load_state("networkidle")


def login_bac(page, usuario: str, password: str):
    page.goto("https://buenosairescompras.gob.ar/Default.aspx", wait_until="domcontentloaded")
    page.click("#ctl00_CtrlMenuPortal_lnkIngresar")
    page.wait_for_load_state("networkidle")

    page.wait_for_selector("input[type=text], input[type=email]", timeout=15000)
    campos_texto = page.locator("input[type=text]:visible, input[type=email]:visible")
    campos_texto.first.fill(usuario)
    page.fill("input[type=password]", password)
    page.keyboard.press("Enter")
    page.wait_for_load_state("networkidle")
