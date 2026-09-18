"""Cifrado simetrico para credenciales de portales (COMPR.AR, BAC, etc.)
que el usuario carga desde la pantalla de Configuracion -- nunca se
escriben en el codigo ni pasan por un chat/LLM.

La clave de cifrado vive en `data/.secret.key` (autogenerada la primera
vez, fuera de git -- `data/` ya esta en .gitignore). Sin esa clave los
valores cifrados en la base son inutiles, asi que el archivo de la clave
es en si mismo sensible: no se comparte, no se commitea, y si se pierde
hay que volver a cargar las credenciales desde cero (no hay forma de
recuperarlas).
"""
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

KEY_PATH = Path(__file__).resolve().parent.parent / "data" / ".secret.key"


def _get_key() -> bytes:
    KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not KEY_PATH.exists():
        KEY_PATH.write_bytes(Fernet.generate_key())
    return KEY_PATH.read_bytes()


def encrypt(texto: str) -> bytes:
    return Fernet(_get_key()).encrypt(texto.encode("utf-8"))


def decrypt(token: bytes) -> str | None:
    try:
        return Fernet(_get_key()).decrypt(token).decode("utf-8")
    except InvalidToken:
        return None
