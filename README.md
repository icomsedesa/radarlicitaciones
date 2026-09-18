# Radar de Licitaciones

PoC del buscador propio de licitaciones públicas argentinas (alternativa a Falcontenders). Ver el plan completo: `docs/plan-licitaciones.html` (también publicado como artifact: https://claude.ai/artifact/MTaSoSVbHf63AtN26d4xMn).

## Fuentes conectadas

| Fuente | Jurisdicción | Formato | Renglones (líneas)? |
|---|---|---|---|
| COMPR.AR | Nación (bienes/servicios) | CSV propio (ONC) | Sí, on-demand por proceso (`src/backfill_items.py`, vía Playwright) |
| BAC | CABA | OCDS 1.1 | Sí, incluidos en la carga masiva |
| PBAC | Provincia de Buenos Aires | Scraping (ASP.NET postback) | No — PBAC no publica renglones estructurados, solo dentro del PDF del pliego |
| Mendoza (Provincia) | Provincia de Mendoza y dependencias (ministerios, hospitales, áreas dptales. de salud, Poder Judicial) | Dataset OCDS 1.1 abierto (histórico, con adjudicaciones) + buscador en vivo (Playwright, vigentes) | Sí, incluidos en el dataset histórico (11.412 renglones) |
| Mendoza (OSEP) | Provincia de Mendoza — Obra Social de Empleados Públicos | Buscador en vivo (Playwright) | No |
| Muni San Miguel | GBA norte | HTML propio (`/pliegos/`) + PDFs | No (fecha de apertura y expediente solo están dentro de los PDF, sin parsear todavía) |
| Muni La Matanza | GBA oeste | Boletín Municipal mensual en PDF (texto real) | No |
| Muni Campana | GBA norte | SIBOM (boletín oficial provincial compartido) | No |
| Muni Vicente López | GBA norte | Tabla real, renderizada por JS (Playwright) | No |
| Muni San Andrés de Giles | Interior bonaerense | HTML propio, página que se sobrescribe | No |
| Muni Chivilcoy | Interior bonaerense | HTML propio, una licitación a la vez | No |
| Muni Quilmes | GBA sur | HTML propio server-side, histórico completo 2000-2026 (sin nada desde fines de 2024) | No |
| Muni Morón | GBA oeste | Portal RAFAM, tabla HTML server-side, histórico 2021-2026 | No |
| Muni Tres de Febrero | GBA oeste | HTML propio (`<h3>`+`<p>` regular), por año | No |
| Muni Florencio Varela | GBA sur | HTML simple → PDF con texto real, solo lo vigente (4 licitaciones) | No |
| Muni Escobar | GBA norte | WordPress, posts individuales con permalink predecible | No |
| Muni Moreno | GBA oeste | API JSON abierta + páginas de detalle, texto muy regular | No |
| Muni Avellaneda | GBA sur | HTML propio server-side, histórico completo (862 tarjetas) | No |
| Muni Ituzaingó | GBA oeste | Boletín Oficial mensual en PDF a dos columnas | No |
| Muni Lomas de Zamora | GBA sur | Boletín Oficial vía AJAX (ASP.NET PageMethod) + PDFs con texto real | No |
| Muni Berazategui | GBA sur | Listado vía Playwright + PDFs con patrón muy regular (expediente, apertura, presupuesto) | No |
| Muni San Isidro | GBA norte | Páginas individuales por licitación (numeración forzada, sin índice) | No |
| Muni General Rodríguez | GBA oeste | HTML propio server-side, listados actuales + pasadas | No |
| Muni Lanús | GBA sur | HTML propio server-side, paginado por año (2020-2026) | No |
| Muni General San Martín | GBA norte | SIBOM (boletín oficial provincial compartido) | No |
| Muni Capitán Sarmiento | Interior bonaerense | SIBOM | No |
| Muni San Vicente | GBA sur | SIBOM | No |

Investigados y **sin fuente digital viable hoy**: Tigre, Malvinas Argentinas, Esteban Echeverría, Ezeiza, José C. Paz, y (con reservas — sitio muy inestable) Hurlingham; Almirante Brown también se recomienda descartar (boletines 100% escaneados, sin licitaciones estructuradas); Pilar y Merlo están en SIBOM pero sus boletines no mencionan licitaciones (posible migración a otro sistema no identificado); San Fernando tiene portal de proveedores con login (CUIT) y su Boletín en PDF tiene muy bajo rendimiento por redacción irregular. Ver hallazgos abajo.

**Interior de la provincia (fuera de GBA): sin explorar todavía**, más allá de San Andrés de Giles, Chivilcoy y Capitán Sarmiento. SIBOM tiene `city_id` para los ~135 partidos de la provincia (`src/connectors/municipios/sibom.py`, reutilizable), así que sumar más municipios del interior es en gran parte cuestión de probar cada `city_id` contra el conector genérico — pendiente de una pasada cuando haya pedido concreto del área comercial.

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
- **Ningún municipio tiene un sistema de compras online como Nación/CABA/Provincia.** Investigación sobre 11 municipios del GBA + interior bonaerense (ver `docs/plan-licitaciones.html`): ninguno tiene tabla HTML con paginación tipo "sistema de compras". Los 3 que sí se pudieron incorporar:
  - **San Miguel**: página única acumulando TODO el histórico 2020-2026 (535 licitaciones) agrupadas por heading + links a PDFs, sin tabla. Sin fecha de apertura en el HTML.
  - **La Matanza** (el municipio más poblado de la provincia): sin sistema de compras propio (el único link es un PDF muerto de 2017) — la fuente real es el **Boletín Municipal mensual en PDF** (texto real, no escaneado), con un patrón de redacción muy regular ("Llámase a Licitación Pública Nº X/AAAA, para el día...") que se parsea con regex vía `pdfplumber`, incluyendo fecha de apertura y monto real.
  - **Campana**: su página propia de compras está casi vacía (1 licitación cargada a mano) — la fuente real es **SIBOM** (`sibom.slyt.gba.gob.ar`), una plataforma que comparten decenas de municipios bonaerenses para su Boletín Oficial. Cada boletín trae el texto completo de todos sus decretos en una sola página (no hace falta abrir cada decreto aparte); se filtra por la palabra "licitación" entre todo tipo de actos administrativos. El conector (`src/connectors/municipios/sibom.py`) es genérico por `city_id`, reutilizable para cualquier otro municipio que use SIBOM.
  - **San Isidro** quedó pendiente pese a tener los mejores datos individuales (expediente, fecha de apertura, PDFs) porque el índice de licitaciones vigentes del sitio da 404, y ni la búsqueda numérica de URLs ni el portal de Boletín Oficial (bloqueado a bots headless, aunque responde a `curl` simple) permiten descubrir de forma confiable qué licitaciones 2025/2026 existen.
  - **Vicente López**: la tabla de "Consulta de pliegos" (`ventadepliegos.php`) tiene columnas reales (Contratación, Número, Año, Objeto, Presupuesto, Fecha de Apertura) pero se llena por JS — con `requests` da vacía, hace falta Playwright. Resultado: el mejor de los 6 municipios conectados, 10 licitaciones abiertas con fecha y monto reales.
  - **San Andrés de Giles**: página propia con patrón de texto regular ("Llámese a Licitación Pública Nº X/AAAA... Presupuesto Oficial... Apertura de Ofertas..."), parseable con regex. Al momento de conectarla, la página no se había actualizado desde marzo de 2025 — sigue siendo la única fuente del municipio, solo que desactualizada.
  - **Chivilcoy**: mismo patrón de página única que se sobrescribe con cada llamado nuevo; regex sobre un formato de texto también regular ("APERTURA DE PROPUESTAS: Día... Hora...", "PRESUPUESTO OFICIAL: $...").
  - **Quilmes**: histórico completo 2000-2026 en HTML server-side (500+ links), con página de detalle propia por licitación — pero nada publicado desde fines de 2024, es una fuente viva y bien hecha que el municipio dejó de alimentar.
  - **Morón**: portal RAFAM (software de gestión financiera que comparten varios municipios bonaerenses), tabla HTML estática sin paginación. Algunas filas traen el número de licitación vacío en origen (dato faltante real, no bug del scraper) — se descartan.
  - **Tres de Febrero**: páginas por año con patrón `<h3>`+`<p>` muy regular (objeto, presupuesto, fecha de apertura, expediente, decreto).
  - **Florencio Varela**: solo lo vigente (4 licitaciones al conectarlo), HTML simple con links directos a PDF con texto real y patrón muy regular.
  - **Moreno**: la fuente más rica de todas — una **API JSON abierta** (`moreno.gob.ar/services/noticias/list.php?list_last_id=N`, paginable) con una noticia por licitación, y cada noticia trae MOTIVO/EXPEDIENTE/PRESUPUESTO OFICIAL/APERTURA DE OFERTAS en texto muy regular.
  - **Avellaneda** (mda.gob.ar): 862 tarjetas HTML con todo el histórico en una sola página — el número, objeto y fecha del decreto ya están en el listado mismo, sin necesidad de abrir el PDF "Nota" (que sí tendría fecha de apertura, no parseado todavía).
  - **Ituzaingó**: Boletín Oficial mensual en PDF, pero **a dos columnas** — `extract_text()` de pdfplumber intercala líneas de ambas columnas y arma frases sin sentido; hubo que recortar cada página por la mitad (`page.crop(...)`) y extraer columna por columna. Rendimiento más bajo que los demás (solo 2 licitaciones en las primeras pruebas, con descripciones a veces demasiado largas por partes irregulares del boletín).
  - **Lomas de Zamora**: el Boletín Oficial se sirve por un endpoint ASP.NET PageMethod (`POST .../BoletinOficial.aspx/getHTMLs` con `{subseccion: id_del_año}`, respuesta `{"d": "<html>"}`) — reproducible sin browser una vez encontrado el id de "subseccion" por año en el HTML de la página. La fecha de apertura casi siempre figura como "a determinar" en el decreto de llamado, así que queda en `None` la mayoría de las veces.
  - **Berazategui**: el listado se carga por AJAX (WordPress/WPBakery, requiere nonce, no vale la pena replicarlo a mano) — se usa Playwright solo para levantar los links, pero el PDF de cada licitación sigue un patrón de URL predecible (`/descargas/licitaciones/{año}/licitacion-publica-{numero}-{año}.pdf`) que permite bajarlo directo sin pasar por la página intermedia. Algunos números "vecinos" al rango vigente devuelven HTML de error en vez de PDF (`No /Root object!` al abrir con pdfplumber) — normal, no todos los números están publicados.
  - **San Isidro** (resuelto, era el más difícil): el índice `/tramites-y-servicios/compras` sigue devolviendo 404 y no hay sitemap ni buscador accesible sin login, pero cada licitación vive en una página individual con path predecible (`/tramites-y-servicios/licitación-pública-nºN`, con o sin guion antes del número — ambas variantes conviven) y devuelve 404 real cuando el número no existe. Sin índice, se fuerza la numeración en un rango (continua, no reinicia por año) y se detecta la existencia por status code. Cada página trae una tabla HTML simple (`<strong>Etiqueta</strong>` / valor) con Expediente, Objeto, Presupuesto, Fecha y Horario de apertura.
  - **General Rodríguez**: HTML estático sin JS, con páginas de listado separadas para "actuales" y "pasadas" (`/licitaciones/` y `/licitaciones/pasadas`) — cada licitación es un bloque secuencial `<h3>` (título+objeto) seguido de `<p><b>Fecha de apertura</b></p>` dentro de un `<section>` común, sin contenedor propio por licitación.
  - **Lanús**: tras un error 525 de Cloudflare en un intento anterior, el sitio volvió a estar disponible. Tiene un listado HTML server-side con categorías por año (`/documentos-oficiales?categoria=N&page=M`, un id de categoría distinto por año de "Licitaciones Públicas", de 2020 a 2026) y tarjetas `<article>` con `.volanta` (número + fecha de apertura), `<h3>` (objeto) y link de descarga. Algunas tarjetas son "Circulares" aclaratorias sobre una licitación ya cargada, no llamados nuevos — se prioriza quedarse con la versión del llamado original cuando existen ambas.
  - **General San Martín**: usa SIBOM (city_id=57) igual que Campana — funciona bien (37+ licitaciones), aunque la `descripcion` incluye metadata del decreto sin limpiar (fecha de publicación, tags de búsqueda) además del objeto real.
  - **Capitán Sarmiento y San Vicente**: se suman a la lista de municipios que sí publican licitaciones reconocibles en su boletín SIBOM (a diferencia de Tigre, Malvinas Argentinas, Esteban Echeverría, Ezeiza, José C. Paz, Hurlingham, Pilar y Merlo, probados contra SIBOM en esta misma ronda y sin resultado).
- **Varios sitios municipales tienen la cadena de certificados SSL incompleta** (falta el certificado intermedio) — funcionan con `curl` (usa el almacén de certificados del SO) pero fallan con `requests` de Python (usa `certifi`, más estricto). Se resuelve con `verify=False` en esos conectores puntuales (Tres de Febrero, Moreno, Avellaneda, Lomas de Zamora, Berazategui, San Isidro, General Rodríguez, Lanús) — son fuentes públicas de solo lectura, sin dato sensible en juego.
- **SIBOM cubre prácticamente toda la provincia**: la lista de ciudades (`sibom.slyt.gba.gob.ar/cities`) tiene `city_id` para los ~135 partidos bonaerenses, GBA e interior por igual — no solo los que ya probamos. El conector genérico (`src/connectors/municipios/sibom.py`) sirve para cualquiera de ellos; el trabajo pendiente es solo probar cada `city_id` y ver si ese municipio en particular usa el boletín para publicar licitaciones (muchos no lo hacen, como se ve en la lista de "sin fuente viable" de arriba).
- **Mendoza usa el mismo software COMPRAR que la Nación** (misma versión de sistema, mismos ids de control ASP.NET `ctl00_CPH1_ddlEstadoProceso` / `ctl00_CPH1_GridListaPliegos`, mismo valor "Publicado"=6, misma paginación `__doPostBack('...GridListaPliegos','Page$N')`) — hallazgo que permitió adaptar `comprar_ar_live.py` casi directo. Dos particularidades: (1) la página de búsqueda (`BuscarAvanzado2.aspx`) redirige al home si no se entra por el botón "BÚSQUEDA DE PROCESOS" del home (requiere un paso previo de "calentamiento" de sesión vía `__doPostBack`); (2) la grilla trae una columna extra de monto estimado que el buscador nacional no tiene.
  - **Mendoza Provincia** además tiene un dataset abierto real ("Contrataciones Abiertas Mendoza", `datosabiertos-compras.mendoza.gov.ar`) en **OCDS 1.1 sin aplanar** (no un CSV compilado como el `bac_anual.csv` de CABA) — cada release trae tender + planning + awards + contracts completos, **incluyendo renglones y adjudicaciones con proveedor y monto real**, sin necesitar backfill aparte vía Playwright. Como todo dataset masivo, está desfasado (el archivo más reciente llega hasta enero 2026) — se complementa con el buscador en vivo para lo realmente vigente hoy. `buyer.name` en el dataset ya identifica muchísimas dependencias de salud (hospitales, áreas departamentales de salud, Ministerio de Salud) sin necesitar un conector separado por cada una.
  - **OSEP (Obra Social de Empleados Públicos de Mendoza)** — `comprarosep.mendoza.gov.ar` — es un **deployment separado** del portal provincial (versión de software distinta, v5 vs v1.0.5), sin dataset abierto propio, pero con el mismo buscador en vivo (grilla de 7 columnas, sin monto, igual a la nacional). Muy relevante para IcomSalud: compra insumos médicos directos (catéteres, stents, prótesis, implantes cocleares), no solo servicios administrativos.

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
.venv\Scripts\python -m src.refresh_live      # estado real contra los buscadores en vivo (COMPR.AR, Mendoza, OSEP), unos minutos
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

Prueba de concepto (Fase 1-2 del plan): valida que la ingesta, normalización y búsqueda funcionan de punta a punta con datos reales, ya con **14 municipios sumados** (San Miguel, La Matanza, Campana, Vicente López, San Andrés de Giles, Chivilcoy, Quilmes, Morón, Tres de Febrero, Florencio Varela, Escobar, Moreno, Avellaneda, Ituzaingó). Todavía no tiene: alertas, deduplicación entre fuentes, ni los municipios pendientes de una próxima pasada (San Isidro, San Fernando, Lanús, Berazategui, Lomas de Zamora, General San Martín, Pilar, General Rodríguez, Merlo — ver detalle arriba). Quedan además sin explorar Hurlingham (dudoso, sitio inestable) y los descartados por falta de fuente digital (Tigre, Malvinas Argentinas, Esteban Echeverría, Ezeiza, José C. Paz, Almirante Brown).
