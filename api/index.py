"""Punto de entrada para Vercel (convencion de funciones Python:
cualquier archivo en `api/` se convierte en una funcion serverless).
`vercel.json` enruta todo el trafico hacia aca, que a su vez reexpone
la app Flask real definida en `app.py` (raiz del repo)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import app  # noqa: E402

# Vercel (via @vercel/python) espera encontrar un objeto WSGI llamado
# `app` en este modulo -- ya lo tenemos importado con ese mismo nombre.
