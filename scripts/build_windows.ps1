# Build "Rinse Tracker" for Windows and the installer dist\Rinse-Tracker-Setup.exe.
# Run in PowerShell on Windows (or the GitHub Actions Windows runner).
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

python -m pip install --upgrade pip
python -m pip install -r requirements.txt -r requirements-desktop.txt

if (Test-Path build) { Remove-Item -Recurse -Force build }
if (Test-Path dist) { Remove-Item -Recurse -Force dist }
New-Item -ItemType Directory build | Out-Null
python scripts/make_icon.py build/icon.ico

python -m PyInstaller --noconfirm --windowed `
  --name "Rinse Tracker" `
  --icon build/icon.ico `
  --add-data "rinse_tracker/static;rinse_tracker/static" `
  desktop.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

# Check the packaged app actually starts and serves its pages (windowed exe: check the exit code).
$test = Start-Process -FilePath "dist\Rinse Tracker\Rinse Tracker.exe" -ArgumentList "--self-test" -Wait -PassThru
if ($test.ExitCode -ne 0) { throw "Packaged app self-test failed (exit code $($test.ExitCode))" }

# Installer (Inno Setup).
$iscc = (Get-Command iscc.exe -ErrorAction SilentlyContinue).Source
if (-not $iscc) { $iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" }
if (-not (Test-Path $iscc)) {
  choco install innosetup -y --no-progress
  $iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
}
& $iscc installer\rinse-tracker.iss
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed" }

Write-Host "Built dist\Rinse-Tracker-Setup.exe"
