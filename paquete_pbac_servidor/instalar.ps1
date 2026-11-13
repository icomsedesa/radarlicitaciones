# Instala la ingesta de PBAC en este servidor (ejecutar UNA vez, como Administrador).
# Requisitos previos: Python 3.12+ instalado ("Add python.exe to PATH") y el
# archivo .env creado en esta carpeta (copiar .env.example -> .env y completar).
$ErrorActionPreference = "Stop"
$carpeta = $PSScriptRoot
Set-Location $carpeta

if (-not (Test-Path ".env")) { throw "Falta el archivo .env (copiar .env.example a .env y completar las 2 variables)." }
if (-not (Get-Command python -ErrorAction SilentlyContinue)) { throw "No se encontro Python en el PATH." }

Write-Host "1/4 Creando entorno virtual..."
python -m venv .venv
Write-Host "2/4 Instalando dependencias..."
& .\.venv\Scripts\python.exe -m pip install --quiet -r requirements-pbac.txt

Write-Host "3/4 Probando una corrida real..."
& .\.venv\Scripts\python.exe -m src.ingest_pbac
if ($LASTEXITCODE -ne 0) { throw "La prueba fallo (ver el mensaje de arriba). Probar abrir https://pbac.cgp.gba.gov.ar en un navegador de este servidor." }

Write-Host "4/4 Registrando la tarea diaria (07:00)..."
$accion = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$carpeta\ejecutar.ps1`""
$trigger = New-ScheduledTaskTrigger -Daily -At 7:00AM
$cfg = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 20)
Register-ScheduledTask -TaskName "Radar - Ingesta PBAC" -Action $accion -Trigger $trigger -Settings $cfg `
    -User "SYSTEM" -RunLevel Highest -Description "Ingesta diaria de PBAC para Radar de Licitaciones" -Force | Out-Null
Write-Host "Listo. La tarea 'Radar - Ingesta PBAC' corre todos los dias a las 07:00. Log: $carpeta\log.txt"
