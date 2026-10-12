# Test + build PyInstaller (onedir) + selftest dell'eseguibile + zip distribuibile.
# Uso: powershell -ExecutionPolicy Bypass -File scripts\build.ps1 [-SkipTests]
param([switch]$SkipTests)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

$py = ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { throw "Ambiente assente: esegui prima scripts\setup.ps1" }
if (-not (Test-Path "models\hand_landmarker.task")) { throw "Modello mancante: esegui prima scripts\setup.ps1" }

if (-not $SkipTests) {
    Write-Host "== Test"
    & $py -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw "Test falliti: build annullata." }
}

Write-Host "== PyInstaller"
& $py -m PyInstaller --noconfirm --clean ShinobiCam.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller fallito." }
$exe = "dist\ShinobiCam\ShinobiCam.exe"
if (-not (Test-Path $exe)) { throw "$exe non generato." }

Write-Host "== Selftest dell'eseguibile"
$home_ = Join-Path $env:TEMP "shinobicam-selftest"
$env:SHINOBICAM_HOME = $home_
try {
    $p = Start-Process -FilePath $exe -ArgumentList "--selftest" -Wait -PassThru
    Get-Content (Join-Path $home_ "selftest.txt")
    if ($p.ExitCode -ne 0) { throw "Selftest fallito (exit $($p.ExitCode))." }
} finally {
    Remove-Item Env:SHINOBICAM_HOME
}

Write-Host "== Pacchetto"
Compress-Archive -Path "dist\ShinobiCam" -DestinationPath "dist\ShinobiCam-win64.zip" -Force

Write-Host "== Installer"
$iscc = @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
          "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { $iscc = (Get-Command iscc -ErrorAction SilentlyContinue).Source }
if ($iscc) {
    $version = (Select-String -Path "shinobicam\__init__.py" -Pattern '__version__ = "(.+)"').Matches[0].Groups[1].Value
    & $iscc /Qp "/DMyAppVersion=$version" "installer\ShinobiCam.iss"
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup fallito." }
    Write-Host "Fatto: dist\ShinobiCam-$version-setup.exe  e  dist\ShinobiCam-win64.zip" -ForegroundColor Green
} else {
    Write-Warning "Inno Setup 6 non trovato: installer saltato. Installalo con: winget install JRSoftware.InnoSetup"
    Write-Host "Fatto: $exe  e  dist\ShinobiCam-win64.zip" -ForegroundColor Green
}
