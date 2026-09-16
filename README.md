# Radar de Licitaciones

PoC del buscador propio de licitaciones públicas argentinas (alternativa a Falcontenders). Ver el plan completo: `docs/plan-licitaciones.html` (también publicado como artifact: https://claude.ai/artifact/MTaSoSVbHf63AtN26d4xMn).

## Fuentes conectadas

| Fuente | Jurisdicción | Formato | Notas |
|---|---|---|---|
| COMPR.AR | Nación (bienes/servicios) | CSV propio (ONC) | `src/connectors/comprar_ar.py` |
| BAC | CABA | OCDS 1.1 | `src/connectors/bac.py` |
| PBAC | Provincia de Buenos Aires | Scraping (ASP.NET postback) | `src/connectors/pbac.py` |

Pendiente: municipios de la Provincia de Buenos Aires.

## Setup

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

## Cargar datos

```
.venv\Scripts\python -m src.ingest --rapido   # carga acotada, rápida, para probar
.venv\Scripts\python -m src.ingest            # carga completa (COMPR.AR + BAC completos, PBAC 5 páginas)
```

Guarda todo en `data/licitaciones.db` (SQLite). Los CSV/JSON descargados se cachean en `data/<fuente>/` — borrar esa carpeta para forzar una nueva descarga.

## Buscador web

```
.venv\Scripts\python app.py
```

Abre http://localhost:5000

## Estado

Prueba de concepto (Fase 1 del plan): valida que la ingesta, normalización y búsqueda funcionan de punta a punta con datos reales. Todavía no tiene: alertas, deduplicación entre fuentes, ni scraping de municipios.
