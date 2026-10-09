# Lleva el codigo de este equipo a la Raspberry y reinicia alli los bots que esten en marcha.
#   scripts\desplegar_pi.bat              copia el codigo (src, assets, scripts, requirements) y reinicia los bots
#   scripts\desplegar_pi.bat -Instalar    la primera vez: ademas crea el entorno y deja los bots como servicios
#   scripts\desplegar_pi.bat -SinReiniciar  solo copia
# Nunca copia datos, ajustes propios, credenciales ni sesiones de Chrome: cada maquina tiene los suyos
# (solo config/defaults.ini, que es parte del codigo).
# Usa la clave SSH %USERPROFILE%\.ssh\am4bot_pi (autorizada en la Raspberry), sin contrasenas.
# La IP y el usuario de tu Raspberry no van en el repositorio: guardalos una vez en variables de entorno
#   setx AM4BOT_PI_HOST 192.168.1.50      (o su nombre, por defecto raspberrypi.local)
#   setx AM4BOT_PI_USER pi                (por defecto pi)
# o pasalos cada vez: scripts\desplegar_pi.bat -Equipo 192.168.1.50 -Usuario pi
param(
    [string]$Equipo = $env:AM4BOT_PI_HOST,
    [string]$Usuario = $env:AM4BOT_PI_USER,
    [string[]]$Perfiles = @('principal', 'secundario'),
    [switch]$Instalar,
    [switch]$SinReiniciar
)
$ErrorActionPreference = 'Stop'
if (-not $Equipo) { $Equipo = 'raspberrypi.local' }
if (-not $Usuario) { $Usuario = 'pi' }
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$key = Join-Path $env:USERPROFILE '.ssh\am4bot_pi'
if (-not (Test-Path $key)) { throw "No encuentro la clave SSH $key" }
$destino = "$Usuario@$Equipo"
$opciones = @('-i', $key, '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=accept-new', '-o', 'ConnectTimeout=10')

function Remoto([string]$script) {
    # Viaja como fichero (UTF-8 sin BOM y saltos de linea de Linux): PowerShell 5.1 antepone un BOM a lo que
    # pasa por la entrada estandar de ssh, y bash no lo entiende.
    $local = Join-Path $env:TEMP 'am4bot-desplegar.sh'
    [IO.File]::WriteAllText($local, ($script -replace "`r", ''), (New-Object System.Text.UTF8Encoding $false))
    & scp.exe @opciones -q $local "${destino}:/tmp/am4bot-desplegar.sh"
    if ($LASTEXITCODE -ne 0) { throw 'No he podido copiar el script de instalacion.' }
    Remove-Item $local
    & ssh.exe @opciones $destino 'bash /tmp/am4bot-desplegar.sh; s=$?; rm -f /tmp/am4bot-desplegar.sh; exit $s'
    if ($LASTEXITCODE -ne 0) { throw "La Raspberry ha devuelto un error ($LASTEXITCODE)." }
}

Write-Host "1/3 Empaquetando el codigo ..."
$paquete = Join-Path $env:TEMP 'am4bot-codigo.tgz'
& tar.exe -czf $paquete --exclude '__pycache__' --exclude '*.pyc' src assets scripts config/defaults.ini requirements.txt README.md
if ($LASTEXITCODE -ne 0) { throw 'No he podido empaquetar el codigo.' }

Write-Host "2/3 Copiando a $Equipo ..."
& scp.exe @opciones -q $paquete "${destino}:/tmp/am4bot-codigo.tgz"
if ($LASTEXITCODE -ne 0) { throw 'No he podido copiar el codigo (esta encendida la Raspberry?).' }
Remove-Item $paquete

Write-Host "3/3 Instalando en la Raspberry ..."
$servicios = ($Perfiles | ForEach-Object { "am4bot@$_" }) -join ' '
$script = @'
set -e
mkdir -p ~/AirlineManager4Bot && cd ~/AirlineManager4Bot
old_req="$(cat requirements.txt 2>/dev/null || true)"
rm -rf src assets scripts
tar -xzf /tmp/am4bot-codigo.tgz && rm -f /tmp/am4bot-codigo.tgz
[ -x .venv/bin/python ] || python3 -m venv .venv
if [ "$old_req" != "$(cat requirements.txt)" ] || [ ! -f .venv/.instalado ]; then
  echo "   instalando dependencias de Python ..."
  .venv/bin/pip install -q --upgrade pip && .venv/bin/pip install -q -r requirements.txt && touch .venv/.instalado
fi
if [ "__INSTALAR__" = "1" ]; then
  # The unit in the repository names the user pi: install it with this account and its home folder.
  sed -e "s|^User=.*|User=$(id -un)|" -e "s|/home/pi/AirlineManager4Bot|$HOME/AirlineManager4Bot|g" \
    scripts/raspberry/am4bot@.service | sudo tee /etc/systemd/system/am4bot@.service >/dev/null
  sudo systemctl daemon-reload
  sudo systemctl enable __SERVICIOS__ >/dev/null 2>&1
  echo "   servicios activados: __SERVICIOS__"
fi
if [ "__REINICIAR__" = "1" ]; then
  for s in __SERVICIOS__; do
    if [ "__INSTALAR__" = "1" ]; then sudo systemctl restart "$s"; else sudo systemctl try-restart "$s"; fi
    echo "   $s: $(systemctl is-active "$s")"
  done
fi
echo "   codigo actualizado: $(date '+%d/%m/%Y %H:%M')"
'@
$script = $script.Replace('__INSTALAR__', $(if ($Instalar) { '1' } else { '0' })).Replace('__REINICIAR__', $(if ($SinReiniciar) { '0' } else { '1' })).Replace('__SERVICIOS__', $servicios)
Remoto $script
Write-Host "Listo. Paneles: http://${Equipo}:8744 (principal) y http://${Equipo}:8745 (secundario)."
