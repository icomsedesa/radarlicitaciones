# Ingesta de PBAC (Provincia de Buenos Aires) desde esta PC.
# Motivo: el servidor de PBAC no responde a las IP de GitHub Actions, por lo
# que el workflow diario lo excluye (--excluir pbac). Esto es TEMPORAL: la
# idea es mover PBAC a un lugar que no dependa de ninguna PC.
# Registra en la base (estado_fuentes) si pudo o no actualizar, igual que el
# resto de las fuentes. Log en data\logs\pbac.log.
$raiz = Split-Path -Parent $PSScriptRoot
Set-Location $raiz
New-Item -ItemType Directory -Force -Path "data\logs" | Out-Null
$log = "data\logs\pbac.log"
"[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] inicio" | Out-File -Append -Encoding utf8 $log
$env:PYTHONIOENCODING = "utf-8"
& ".\.venv\Scripts\python.exe" -m src.ingest_pbac 2>&1 | Out-File -Append -Encoding utf8 $log
"[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] fin (codigo $LASTEXITCODE)" | Out-File -Append -Encoding utf8 $log
