<#
.SYNOPSIS
    Installs, updates or uninstalls Escriba on Windows.

.DESCRIPTION
    1. Installs uv (Astral's Python manager) if it's missing.
    2. With uv, installs Escriba and everything it needs (Python included) in
       its own environment, without touching any other Python on the system.
    3. Creates the "Escriba" shortcut on the desktop and in the Start menu.

    Running it again updates to the latest version. Your data (voices,
    glossary, keys) is in %LOCALAPPDATA%\escriba and is never touched.

    Messages are shown in Spanish if Windows is in Spanish, in English otherwise.

.PARAMETER Local
    Also installs the "on this PC" mode (faster-whisper and pyannote): ~1.5 GB
    more. It can also be added later from Escriba (Settings), and an update
    keeps it if it's there. Without it, cloud only.

.PARAMETER Gpu
    Local mode for NVIDIA cards (experimental): torch for CUDA 12, ~5 GB
    instead of ~1.5. Implies -Local. If the GPU fails, the CPU is used.

.PARAMETER Source
    Where to get Escriba from: a folder with the code or the URL of a .zip.
    By default, this script's folder if it holds the code; otherwise, GitHub.

.PARAMETER Uninstall
    Removes Escriba and its shortcuts. Your data stays.

.PARAMETER NoPause
    Doesn't wait for Enter at the end (to run it from another script).

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File install.ps1
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File install.ps1 -Local
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File install.ps1 -Gpu
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File install.ps1 -Uninstall
#>
[CmdletBinding()]
param(
    [switch]$Local,
    [switch]$Gpu,
    [string]$Source,
    [switch]$Uninstall,
    [switch]$NoPause
)

$ErrorActionPreference = 'Stop'
$GitHubZip = 'https://github.com/Carlolius/escriba/archive/refs/heads/main.zip'
$PythonVersion = '3.11'
$Spanish = (Get-UICulture).TwoLetterISOLanguageName -eq 'es'

function T($en, $es) { if ($Spanish) { $es } else { $en } }
function Step($text) { Write-Host "`n==> $text" -ForegroundColor Cyan }
# With right click > "Run with PowerShell" the window closes when done:
# wait for Enter so there's time to read the result
function Wait-Enter { if (-not $NoPause) { Read-Host "`n$(T 'Press Enter to close' 'Pulsa Enter para cerrar')" | Out-Null } }
function Fail($text) { Write-Host "`nERROR: $text" -ForegroundColor Red; Wait-Enter; exit 1 }

function Shortcuts {
    @(
        (Join-Path ([Environment]::GetFolderPath('Desktop')) 'Escriba.lnk'),
        (Join-Path ([Environment]::GetFolderPath('Programs')) 'Escriba.lnk')
    )
}

# ── 1. uv ────────────────────────────────────────────────────────────────────
# The official installer puts it in %USERPROFILE%\.local\bin; add it to this
# session in case it's the first time and PATH doesn't have it yet.
$env:Path = "$(Join-Path $env:USERPROFILE '.local\bin');$env:Path"
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    if ($Uninstall) { Fail (T 'uv is not installed, so Escriba is not either.' 'uv no está instalado, así que Escriba tampoco.') }
    Step (T "Installing uv (Astral's Python manager)" 'Instalando uv (gestor de Python de Astral)')
    powershell -NoProfile -ExecutionPolicy Bypass -Command 'irm https://astral.sh/uv/install.ps1 | iex'
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { Fail (T "Couldn't install uv." 'No se pudo instalar uv.') }
}

# ── Uninstall ────────────────────────────────────────────────────────────────
if ($Uninstall) {
    Step (T 'Uninstalling Escriba' 'Desinstalando Escriba')
    uv tool uninstall escriba
    foreach ($lnk in Shortcuts) { Remove-Item $lnk -ErrorAction SilentlyContinue }
    Write-Host "`n$(T 'Done. Your data is still in' 'Listo. Tus datos siguen en') $env:LOCALAPPDATA\escriba $(T '(delete it by hand if you want).' '(bórralos a mano si quieres).')"
    Wait-Enter
    exit 0
}

# ── 2. Escriba ───────────────────────────────────────────────────────────────
if (-not $Source) {
    if ($PSScriptRoot -and (Test-Path (Join-Path $PSScriptRoot 'pyproject.toml'))) {
        $Source = $PSScriptRoot
    } else {
        $Source = $GitHubZip
    }
}
if (Test-Path $Source) {
    $Source = ([System.Uri](Resolve-Path $Source).Path).AbsoluteUri   # C:\x -> file:///C:/x
}
# Local mode may have been added later from escriba itself (Settings or
# `escriba install-local`): keep it when updating
$sitePackages = Join-Path (uv tool dir).Trim() 'escriba\Lib\site-packages'
if (-not $Local -and (Test-Path (Join-Path $sitePackages 'faster_whisper'))) {
    $Local = $true
    Write-Host (T 'Local mode is installed: it is kept.' 'El modo local está instalado: se mantiene.')
}
if (-not $Gpu -and (Test-Path (Join-Path $sitePackages 'torch\lib\torch_cuda.dll'))) {
    $Gpu = $true
    Write-Host (T 'The GPU version is installed: it is kept.' 'La versión para GPU está instalada: se mantiene.')
}
if ($Gpu) { $Local = $true }
# CUDA 12.6: faster-whisper's engine (CTranslate2 4.x) doesn't work with CUDA 13
$torchBackend = if ($Gpu) { 'cu126' } else { 'cpu' }
$extra = if ($Local) { '[local]' } else { '' }
$package = "escriba$extra @ $Source"

Step "$(T 'Installing Escriba from' 'Instalando Escriba desde') $Source"
if ($Gpu) { Write-Host (T 'With local mode for the GPU (experimental): ~5 GB, it may take a good while.' 'Con el modo local para GPU (experimental): ~5 GB, puede tardar un buen rato.') }
elseif ($Local) { Write-Host (T 'With local mode: ~1.5 GB, it may take a while.' 'Con el modo local: ~1,5 GB, puede tardar un rato.') }
uv tool install --force --python $PythonVersion --torch-backend $torchBackend `
    --reinstall-package escriba --refresh-package escriba $package
if ($LASTEXITCODE -ne 0) { Fail (T "The installation with uv didn't finish well (see the messages above)." 'La instalación con uv no terminó bien (mira los mensajes de arriba).') }

$exe = Join-Path (uv tool dir --bin).Trim() 'escriba.exe'
if (-not (Test-Path $exe)) { Fail "$(T "Can't find" 'No encuentro') $exe" }

# ── 3. Shortcuts ─────────────────────────────────────────────────────────────
Step (T 'Creating the shortcut on the desktop and in the Start menu' 'Creando el acceso directo en el escritorio y en el menú Inicio')
$shell = New-Object -ComObject WScript.Shell
foreach ($path in Shortcuts) {
    $lnk = $shell.CreateShortcut($path)
    $lnk.TargetPath = $exe
    $lnk.Arguments = 'web'
    $lnk.WorkingDirectory = $env:USERPROFILE
    $lnk.Description = T 'Record, transcribe and identify speakers in meetings' 'Grabar, transcribir e identificar hablantes en reuniones'
    $lnk.Save()
}

Write-Host "`n$(T 'Escriba is installed.' 'Escriba está instalado.')" -ForegroundColor Green
if ($Spanish) {
    Write-Host @"

- Ábrelo con el acceso directo "Escriba": se abre una ventana negra (déjala
  abierta mientras lo uses) y el navegador con la aplicación.
- La primera vez, ve a Ajustes y pon tu clave de AssemblyAI.
- Si al grabar el micrófono no recoge nada: Configuración de Windows >
  Privacidad y seguridad > Micrófono > "Permitir que las aplicaciones de
  escritorio accedan al micrófono".
- Para actualizar, vuelve a ejecutar este script.
"@
} else {
    Write-Host @"

- Open it with the "Escriba" shortcut: a black window opens (keep it open
  while you use it) and the browser with the app.
- The first time, go to Settings and paste your AssemblyAI key.
- If the microphone records nothing: Windows Settings > Privacy & security >
  Microphone > "Let desktop apps access your microphone".
- To update, run this script again.
"@
}
Wait-Enter
