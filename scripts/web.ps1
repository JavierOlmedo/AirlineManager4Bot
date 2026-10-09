# Abre el panel web de Airline Manager 4 Bot. Si no hay ningun AM4 Bot en marcha (ni la app de escritorio
# ni el modo web), arranca el bot en modo web (sin ventana) en esta consola y abre el navegador.
# Para pararlo: scripts\web_parar.bat (cierra Chrome bien), o Ctrl+C en esta consola.
# Otro perfil (otra cuenta del juego): web.bat -Perfil realismo
param([string]$Perfil = '')
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$env:PYTHONUTF8 = '1'
if ($Perfil -and $Perfil -ne 'principal') { $dir = "profiles\$Perfil" } else { $Perfil = ''; $dir = 'config' }

function Read-Ini([string]$path, [string]$section, [string]$key) {
    if (-not (Test-Path $path)) { return $null }
    $current = ''
    foreach ($line in Get-Content $path -Encoding UTF8) {
        if ($line -match '^\s*\[(.+?)\]\s*$') { $current = $Matches[1]; continue }
        if ($current -eq $section -and $line -match "^\s*$([regex]::Escape($key))\s*=\s*(.*?)\s*$") { return $Matches[1] }
    }
    return $null
}

$port = Read-Ini "$dir\settings.ini" 'web' 'port'
if (-not $port) { $port = Read-Ini 'config\defaults.ini' 'web' 'port' }
if (-not $port) { $port = '8744' }
$token = Read-Ini "$dir\secrets.ini" 'web' 'token'
$url = "http://127.0.0.1:$port/"
if ($token) { $url += "?token=$token" }

if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) {
    Write-Host "Airline Manager 4 Bot ya esta en marcha: abro el panel."
    Start-Process $url
    exit 0
}
if (-not (Test-Path '.venv\Scripts\python.exe')) {
    Write-Host 'No existe .venv. Crea el entorno primero (ver README: python -m venv .venv y pip install -r requirements.txt).'
    Read-Host 'Pulsa Enter para cerrar'
    exit 1
}

# El navegador se abre unos segundos despues, cuando el servidor ya escucha.
Start-Process powershell -WindowStyle Hidden -ArgumentList '-NoProfile', '-Command', "Start-Sleep -Seconds 4; Start-Process '$url'"
if ($Perfil) {
    & '.venv\Scripts\python.exe' 'src\main.py' '--web' '--profile' $Perfil
} else {
    & '.venv\Scripts\python.exe' 'src\main.py' '--web'
}
if ($LASTEXITCODE -ne 0) { Read-Host 'El bot se ha cerrado con un error. Pulsa Enter para cerrar' }
