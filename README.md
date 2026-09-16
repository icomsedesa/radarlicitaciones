# Radar de Licitaciones

PoC del buscador propio de licitaciones públicas argentinas (alternativa a Falcontenders). Ver el plan completo: `docs/plan-licitaciones.html` (también publicado como artifact: https://claude.ai/artifact/MTaSoSVbHf63AtN26d4xMn).

## Fuentes conectadas

| Fuente | Jurisdicción | Formato | Renglones (líneas)? |
|---|---|---|---|
| COMPR.AR | Nación (bienes/servicios) | CSV propio (ONC) | Sí, on-demand por proceso (`src/backfill_items.py`, vía Playwright) |
| BAC | CABA | OCDS 1.1 | Sí, incluidos en la carga masiva |
| PBAC | Provincia de Buenos Aires | Scraping (ASP.NET postback) | No — PBAC no publica renglones estructurados, solo dentro del PDF del pliego |

Pendiente: municipios de la Provincia de Buenos Aires.

## Hallazgos importantes del recorrido (para no repetir la investigación)

- **COMPR.AR no trae renglones en su CSV masivo.** Los ítems de cada proceso ("Detalle de productos o servicios") solo existen en la página individual del proceso en comprar.gob.ar, detrás de un buscador ASP.NET/DevExpress. `src/connectors/comprar_ar_items.py` lo resuelve con Playwright (headless). Por el volumen, `backfill_items.py` solo trae renglones de licitaciones **vigentes** (apertura entre hoy y +180 días — ese límite superior existe porque el CSV de la ONC tiene errores de carga propios, con años como "2099" o "3015" usados como placeholder).
- **El CSV masivo de COMPR.AR está desfasado ~6 semanas** (última actualización: 3-ago-2026 al momento de escribir esto) — para cuando se publica, la enorme mayoría de los procesos que trae ya cerraron. De ~25 procesos que parecían "vigentes" en la carga, solo 1 lo era realmente tras descartar fechas basura. **Para saber qué se puede ofertar HOY, este CSV no alcanza** — haría falta un conector contra el buscador en vivo de comprar.gob.ar (mismo mecanismo que ya reverseamos para los renglones).
- **El recurso `bac_anual.json` de BAC está mal etiquetado**: pese a actualizarse a diario, sus ~23.000 releases son TODOS de 2022 (bug del lado de CABA, no nuestro). El conector usa en cambio `bac_anual.csv` ("Buenos Aires Compras - Anual"), que sí trae datos de 2026 reales. Limitación conocida: por ser un CSV ya compilado (no el release-level `tender.csv` de 620MB), procesos con más de un renglón solo muestran el primero.

## Setup

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m playwright install chromium
```

## Cargar datos

```
.venv\Scripts\python -m src.ingest --rapido   # carga acotada, rápida, para probar
.venv\Scripts\python -m src.ingest            # carga completa (COMPR.AR + BAC completos, PBAC 5 páginas)
.venv\Scripts\python -m src.backfill_items    # renglones de COMPR.AR vigentes (correr después del ingest)
```

Guarda todo en `data/licitaciones.db` (SQLite). Los CSV/JSON descargados se cachean en `data/<fuente>/` — borrar esa carpeta para forzar una nueva descarga.

## Buscador web

```
.venv\Scripts\python app.py
```

Abre http://localhost:5000

## Estado

Prueba de concepto (Fase 1 del plan): valida que la ingesta, normalización y búsqueda funcionan de punta a punta con datos reales. Todavía no tiene: alertas, deduplicación entre fuentes, ni scraping de municipios.
