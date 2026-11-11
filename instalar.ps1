<#
.SYNOPSIS
    Instala, actualiza o desinstala Escriba en Windows.

.DESCRIPTION
    1. Instala uv (el gestor de Python de Astral) si no está.
    2. Con uv, instala Escriba y todo lo que necesita (incluido Python) en
       un entorno propio, sin tocar ningún otro Python del sistema.
    3. Crea el acceso directo "Escriba" en el escritorio y en el menú Inicio.

    Volver a ejecutarlo actualiza a la última versión. Tus datos (voces,
    glosario, claves) están en %LOCALAPPDATA%\escriba y no se tocan nunca.

.PARAMETER Local
    Instala también el modo "en este PC" (faster-whisper y pyannote): unos
    2-3 GB más y transcribir es lento sin tarjeta NVIDIA. Sin él, solo nube.

.PARAMETER Origen
    De dónde sacar Escriba: una carpeta con el código o la URL de un .zip.
    Por defecto, la carpeta de este script si tiene el código; si no, GitHub.

.PARAMETER Desinstalar
    Quita Escriba y sus accesos directos. Tus datos se quedan.

.PARAMETER SinPausa
    No espera a que se pulse Enter al terminar (para ejecutarlo desde otro script).

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File instalar.ps1
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File instalar.ps1 -Local
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File instalar.ps1 -Desinstalar
#>
[CmdletBinding()]
param(
    [switch]$Local,
    [string]$Origen,
    [switch]$Desinstalar,
    [switch]$SinPausa
)

$ErrorActionPreference = 'Stop'
$ZipGitHub = 'https://github.com/Carlolius/escriba/archive/refs/heads/main.zip'
$VersionPython = '3.11'

function Paso($texto) { Write-Host "`n==> $texto" -ForegroundColor Cyan }
# Con clic derecho > "Ejecutar con PowerShell" la ventana se cierra al acabar:
# se espera a Enter para que dé tiempo a leer el resultado
function Pausa { if (-not $SinPausa) { Read-Host "`nPulsa Enter para cerrar" | Out-Null } }
function Fallo($texto) { Write-Host "`nERROR: $texto" -ForegroundColor Red; Pausa; exit 1 }

function Accesos-Directos {
    @(
        (Join-Path ([Environment]::GetFolderPath('Desktop')) 'Escriba.lnk'),
        (Join-Path ([Environment]::GetFolderPath('Programs')) 'Escriba.lnk')
    )
}

# ── 1. uv ────────────────────────────────────────────────────────────────────
# El instalador oficial lo deja en %USERPROFILE%\.local\bin; se añade a la
# sesión actual por si es la primera vez y el PATH aún no lo tiene.
$env:Path = "$(Join-Path $env:USERPROFILE '.local\bin');$env:Path"
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    if ($Desinstalar) { Fallo 'uv no está instalado, así que Escriba tampoco.' }
    Paso 'Instalando uv (gestor de Python de Astral)'
    powershell -NoProfile -ExecutionPolicy Bypass -Command 'irm https://astral.sh/uv/install.ps1 | iex'
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { Fallo 'No se pudo instalar uv.' }
}

# ── Desinstalar ──────────────────────────────────────────────────────────────
if ($Desinstalar) {
    Paso 'Desinstalando Escriba'
    uv tool uninstall escriba
    foreach ($lnk in Accesos-Directos) { Remove-Item $lnk -ErrorAction SilentlyContinue }
    Write-Host "`nListo. Tus datos siguen en $env:LOCALAPPDATA\escriba (bórralos a mano si quieres)."
    Pausa
    exit 0
}

# ── 2. Escriba ───────────────────────────────────────────────────────────────
if (-not $Origen) {
    if ($PSScriptRoot -and (Test-Path (Join-Path $PSScriptRoot 'pyproject.toml'))) {
        $Origen = $PSScriptRoot
    } else {
        $Origen = $ZipGitHub
    }
}
if (Test-Path $Origen) {
    $Origen = ([System.Uri](Resolve-Path $Origen).Path).AbsoluteUri   # C:\x -> file:///C:/x
}
$extra = if ($Local) { '[local]' } else { '' }
$paquete = "escriba$extra @ $Origen"

# resemblyzer pide webrtcvad, que en Windows hay que compilar; escriba ya trae
# webrtcvad-wheels, que instala el mismo módulo ya compilado.
$excluir = Join-Path $env:TEMP 'escriba-excluir.txt'
Set-Content -Path $excluir -Value 'webrtcvad' -Encoding ascii

Paso "Instalando Escriba desde $Origen"
if ($Local) { Write-Host 'Con el modo local: son varios GB, puede tardar un buen rato.' }
uv tool install --force --python $VersionPython --excludes $excluir `
    --reinstall-package escriba --refresh-package escriba $paquete
if ($LASTEXITCODE -ne 0) { Fallo 'La instalación con uv no terminó bien (mira los mensajes de arriba).' }
Remove-Item $excluir -ErrorAction SilentlyContinue

$exe = Join-Path (uv tool dir --bin).Trim() 'escriba.exe'
if (-not (Test-Path $exe)) { Fallo "No encuentro $exe tras instalar." }

# ── 3. Accesos directos ──────────────────────────────────────────────────────
Paso 'Creando el acceso directo en el escritorio y en el menú Inicio'
$shell = New-Object -ComObject WScript.Shell
foreach ($ruta in Accesos-Directos) {
    $lnk = $shell.CreateShortcut($ruta)
    $lnk.TargetPath = $exe
    $lnk.Arguments = 'web'
    $lnk.WorkingDirectory = $env:USERPROFILE
    $lnk.Description = 'Grabar, transcribir e identificar hablantes en reuniones'
    $lnk.Save()
}

Write-Host "`nEscriba está instalado." -ForegroundColor Green
Write-Host @"

- Ábrelo con el acceso directo "Escriba": se abre una ventana negra (déjala
  abierta mientras lo uses) y el navegador con la aplicación.
- La primera vez, ve a Ajustes y pon tu clave de AssemblyAI.
- Si al grabar el micrófono no recoge nada: Configuración de Windows >
  Privacidad y seguridad > Micrófono > "Permitir que las aplicaciones de
  escritorio accedan al micrófono".
- Para actualizar, vuelve a ejecutar este script.
"@
Pausa
