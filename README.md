# Radar de Licitaciones

PoC del buscador propio de licitaciones públicas argentinas (alternativa a Falcontenders). Ver el plan completo: `docs/plan-licitaciones.html` (también publicado como artifact: https://claude.ai/artifact/MTaSoSVbHf63AtN26d4xMn).

## Fuentes conectadas

| Fuente | Jurisdicción | Formato | Renglones (líneas)? |
|---|---|---|---|
| COMPR.AR | Nación (bienes/servicios) | CSV propio (ONC) | Sí, on-demand por proceso (`src/backfill_items.py`, vía Playwright) |
| BAC | CABA | OCDS 1.1 | Sí, incluidos en la carga masiva |
| PBAC | Provincia de Buenos Aires | Scraping (ASP.NET postback) | No — PBAC no publica renglones estructurados, solo dentro del PDF del pliego |

Pendiente: municipios de la Provincia de Buenos Aires.

## Buscador web

Marca IcomSalud aplicada (`static/`: logo, isotipo/favicon, colores). Fuentes, "Con renglones" y "Vigentes hoy" son pastillas-filtro (no dropdown/checkbox); cada fuente tiene su color y se repite igual en la columna Fuente de la tabla. Columna "Faltan" con semáforo rojo/amarillo/verde/gris según cuánto falta para la apertura (`app.py:_texto_faltante`), con pastillas para filtrar por ese bucket y filtros de fecha desde/hasta. El link "↗" junto al título va al portal oficial cuando se conoce (BAC siempre; COMPR.AR solo en los procesos ya procesados por `backfill_items`, que captura la URL real al scrapear los renglones; PBAC no tiene URL de detalle sin sesión, así que linkea al listado general).

Pendiente conocido: los renglones de COMPR.AR cargados en la primera corrida de `backfill_items` (antes de que capturara la URL) no tienen link oficial — se completa solo, corriendo `backfill_items` de nuevo, con procesos nuevos.

## Hallazgos importantes del recorrido (para no repetir la investigación)

- **COMPR.AR no trae renglones en su CSV masivo.** Los ítems de cada proceso ("Detalle de productos o servicios") solo existen en la página individual del proceso en comprar.gob.ar, detrás de un buscador ASP.NET/DevExpress. `src/connectors/comprar_ar_items.py` lo resuelve con Playwright (headless). Por el volumen, `backfill_items.py` solo trae renglones de licitaciones **vigentes** (apertura entre hoy y +180 días — ese límite superior existe porque el CSV de la ONC tiene errores de carga propios, con años como "2099" o "3015" usados como placeholder).
- **El CSV masivo de COMPR.AR está desfasado ~6 semanas** (última actualización: 3-ago-2026 al momento de escribir esto) — para cuando se publica, la enorme mayoría de los procesos que trae ya cerraron. De ~25 procesos que parecían "vigentes" en la carga, solo 1 lo era realmente tras descartar fechas basura. **Ya resuelto**: `src/connectors/comprar_ar_live.py` scrapea el buscador en vivo de comprar.gob.ar filtrando por Estado="Publicado" (mismo mecanismo de Playwright que los renglones) y `src/refresh_live.py` actualiza el estado/fecha real de lo que ya está en la base, sumando lo que el CSV todavía no tiene. Ojo con la paginación de ese buscador: el paginador solo muestra ~10 números a la vez con un link "..." que en realidad apunta a la página siguiente (no "revela más") — el total real de páginas hay que calcularlo con el conteo de "Se han encontrado (N) resultados" del encabezado, no contando los links visibles.
- **El recurso `bac_anual.json` de BAC está mal etiquetado**: pese a actualizarse a diario, sus ~23.000 releases son TODOS de 2022 (bug del lado de CABA, no nuestro). El conector usa en cambio `bac_anual.csv` ("Buenos Aires Compras - Anual"), que sí trae datos de 2026 reales. Limitación conocida: por ser un CSV ya compilado (no el release-level `tender.csv` de 620MB), procesos con más de un renglón solo muestran el primero.
- **El paginador del buscador en vivo de COMPR.AR es engañoso**: solo muestra ~10 números de página con un link "..." que en realidad apunta a la página siguiente (no "revela más" páginas). Contar los links visibles del paginador da un total incorrecto — hay que leer el conteo real del encabezado "Se han encontrado (N) resultados" y calcular las páginas a partir de ahí (`comprar_ar_live._total_paginas`).
- **La columna "Etapa" del CSV masivo de COMPR.AR (Única/Múltiple) no es un estado real** — se guardaba por error como `estado`, mezclándose visualmente con "Publicado" (que sí viene del buscador en vivo). Corregido: el CSV masivo ya no completa `estado`, queda en null hasta que `refresh_live` lo actualiza con el dato real.
- **Resultado de correr `refresh_live` por primera vez**: de 128.951 procesos en el CSV masivo, solo 467 están realmente "Publicado" (abiertos) hoy — confirma que casi todo el volumen del CSV es historial cerrado, no oportunidades vigentes.
- **El "active" de BAC no equivale al "Publicado" de COMPR.AR.** Hay procesos BAC con `estado="active"` y fecha de apertura ya pasada — ese campo en OCDS refleja que el registro sigue en trámite, no que siga aceptando ofertas. Por eso el orden por defecto del buscador prioriza por la fecha real (bucket de urgencia), no por `estado`, que significa cosas distintas según la fuente.
- **Bug repetido en dos conectores**: tanto `comprar_ar_live.py` como `pbac.py` usaban un selector de filas (`find_all("tr")` / `locator("tr")`) que también agarraba las filas de la tabla ANIDADA dentro del renglón de paginación, colando registros basura (`numero_proceso` = "1", "...", etc.). Se corrigió restringiendo a filas hijas directas (`:scope > tbody > tr` en BeautifulSoup, `> tbody > tr` en Playwright) más una validación de que el número de proceso tenga guiones.

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
.venv\Scripts\python -m src.refresh_live      # estado real de COMPR.AR contra el buscador en vivo (~48 páginas, unos minutos)
.venv\Scripts\python -m src.backfill_items    # renglones de las que quedaron con estado "Publicado"
```

`refresh_live` es el paso que soluciona el desfasaje del CSV masivo (ver más abajo) — conviene correrlo después de cada `ingest` y antes de `backfill_items`.

Guarda todo en `data/licitaciones.db` (SQLite). Los CSV/JSON descargados se cachean en `data/<fuente>/` — borrar esa carpeta para forzar una nueva descarga.

## Buscador web

```
.venv\Scripts\python app.py
```

Abre http://localhost:5000

## Estado

Prueba de concepto (Fase 1 del plan): valida que la ingesta, normalización y búsqueda funcionan de punta a punta con datos reales. Todavía no tiene: alertas, deduplicación entre fuentes, ni scraping de municipios.
