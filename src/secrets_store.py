"""Cifrado simetrico para credenciales de portales (COMPR.AR, BAC, etc.)
que el usuario carga desde la pantalla de Configuracion -- nunca se
escriben en el codigo ni pasan por un chat/LLM.

La clave de cifrado sale de la variable de entorno
`SECRETS_ENCRYPTION_KEY` si esta definida -- imprescindible en deploys
sin filesystem persistente entre ejecuciones (Vercel), donde un archivo
local no sobrevive de una invocacion a la siguiente: si la clave
cambiara, las credenciales ya guardadas quedarian permanentemente
indescifrables. En local, sin esa variable, se autogenera y persiste en
`data/.secret.key` (fuera de git -- `data/` ya esta en .gitignore),
alcanza para desarrollo. Sea cual sea el origen, la clave es en si misma
sensible: no se comparte, no se commitea, y si se pierde hay que volver
a cargar las credenciales desde cero (no hay forma de recuperrlas).
"""
import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

KEY_PATH = Path(__file__).resolve().parent.parent / "data" / ".secret.key"


def _get_key() -> bytes:
    env_key = os.environ.get("SECRETS_ENCRYPTION_KEY")
    if env_key:
        return env_key.encode("utf-8")
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
