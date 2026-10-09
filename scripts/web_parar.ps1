# Para Airline Manager 4 Bot (modo web o app de escritorio) de forma limpia: le pide al bot que pare y cierre
# Chrome, espera a que el programa termine y solo como ultimo recurso mata el proceso.
# Otro perfil: web_parar.bat -Perfil realismo
param([string]$Perfil = '')
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
if ($Perfil -and $Perfil -ne 'principal') { $dir = "profiles\$Perfil"; $session = "profiles\$Perfil\session" } else { $dir = 'config'; $session = 'config\session' }

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
$listening = { Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue }

$pids = & $listening | Select-Object -ExpandProperty OwningProcess -Unique
if (-not $pids) {
    Write-Host "Airline Manager 4 Bot no estaba en marcha (nadie escucha en el puerto $port)."
    Start-Sleep -Seconds 2
    exit 0
}
foreach ($id in $pids) {
    $cmd = (Get-CimInstance Win32_Process -Filter "ProcessId=$id").CommandLine
    if ($cmd -notlike '*main.py*') {
        Write-Host "El puerto $port lo usa otro programa (PID $id), no lo toco: $cmd"
        Start-Sleep -Seconds 4
        exit 1
    }
}

Write-Host 'Parando el bot (cierra Chrome y sale) ...'
try {
    $headers = @{ 'X-AM4' = '1' }
    if ($token) { $headers['X-Token'] = $token }
    Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:$port/api/control" -Headers $headers `
        -ContentType 'application/json' -Body '{"action": "quit"}' -TimeoutSec 5 | Out-Null
} catch {
    Write-Host "El panel no ha respondido ($($_.Exception.Message))."
}
$deadline = (Get-Date).AddSeconds(45)
while ((Get-Date) -lt $deadline -and (& $listening)) { Start-Sleep -Seconds 1 }

if (& $listening) {
    Write-Host 'No ha terminado a tiempo: lo cierro a la fuerza.'
    foreach ($id in $pids) { Stop-Process -Id $id -Force -ErrorAction SilentlyContinue }
    # Chrome del perfil del bot que haya quedado abierto
    Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'chrome.exe' -and $_.CommandLine -like "*AirlineManager4Bot\$session*" } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
}
Write-Host 'Airline Manager 4 Bot parado.'
Start-Sleep -Seconds 2
