# Prepara l'ambiente di sviluppo/build su Windows 10/11.
# Uso: powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

$ModelUrl = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
$ModelSha = "fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1"
$ModelPath = "models\hand_landmarker.task"
$ObsClsid = "Registry::HKEY_CLASSES_ROOT\CLSID\{A3FCE0F5-3493-419F-958A-ABA1250EC20B}"

Write-Host "== Python 3.11 x64"
# Probe without Stop: Windows PowerShell 5.1 turns native stderr into terminating errors.
$ErrorActionPreference = "Continue"
$probe = "import struct, sys; assert sys.version_info[:2] == (3, 11); print(sys.executable + '|' + str(struct.calcsize('P') * 8))"
$found = $null
if (Get-Command py -ErrorAction SilentlyContinue) { $found = & py -3.11 -c $probe 2>$null }
if (-not $found -and (Get-Command python -ErrorAction SilentlyContinue)) { $found = & python -c $probe 2>$null }
$ErrorActionPreference = "Stop"
if (-not $found) {
    throw "Python 3.11 non trovato. Installalo da https://www.python.org/downloads/windows/ (64 bit, con 'py launcher')."
}
$python311, $bits = "$found".Trim() -split '\|'
if ($bits -ne "64") { throw "Serve Python 3.11 a 64 bit (trovato: $bits bit)." }
Write-Host "Uso $python311"

Write-Host "== Ambiente virtuale .venv"
if (-not (Test-Path ".venv\Scripts\python.exe")) { & $python311 -m venv .venv }
$py = ".venv\Scripts\python.exe"
& $py -m pip install --upgrade pip
& $py -m pip install -r requirements-dev.txt
if ($LASTEXITCODE -ne 0) { throw "Installazione dipendenze fallita." }

Write-Host "== Modello MediaPipe Hand Landmarker"
if (-not (Test-Path $ModelPath)) {
    New-Item -ItemType Directory -Force -Path models | Out-Null
    Invoke-WebRequest -Uri $ModelUrl -OutFile $ModelPath
}
if ((Get-FileHash $ModelPath -Algorithm SHA256).Hash.ToLower() -ne $ModelSha) {
    Remove-Item $ModelPath
    throw "Checksum del modello errato: file rimosso, rilancia lo script."
}

Write-Host "== Webcam virtuale (OBS Virtual Camera)"
if (Test-Path $ObsClsid) {
    Write-Host "OBS Virtual Camera registrata." -ForegroundColor Green
} else {
    Write-Warning ("OBS Virtual Camera NON registrata. Installa OBS Studio 30+ (https://obsproject.com), " +
                   "aprilo, premi 'Avvia videocamera virtuale' poi 'Ferma', e chiudi OBS.")
}
Write-Host "Ambiente pronto. Avvio in sviluppo: .venv\Scripts\python.exe -m shinobicam" -ForegroundColor Green
