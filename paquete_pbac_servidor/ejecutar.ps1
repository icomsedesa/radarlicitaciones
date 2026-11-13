# Corrida diaria de PBAC (la llama la tarea programada). Log en log.txt.
Set-Location $PSScriptRoot
$env:PYTHONIOENCODING = "utf-8"
"[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] inicio" | Out-File -Append -Encoding utf8 log.txt
& .\.venv\Scripts\python.exe -m src.ingest_pbac 2>&1 | Out-File -Append -Encoding utf8 log.txt
"[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] fin (codigo $LASTEXITCODE)" | Out-File -Append -Encoding utf8 log.txt
