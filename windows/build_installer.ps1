# Build Lucy.exe and Lucy-Setup.exe on Windows.
# Requires: Python 3, pip, PyInstaller, NSIS (https://nsis.sourceforge.io/Download)
#
# Usage (from repo root):
#   powershell -ExecutionPolicy Bypass -File windows/build_installer.ps1
#   powershell -ExecutionPolicy Bypass -File windows/build_installer.ps1 -Version 1.0.0

param(
    [string]$Version = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

Write-Host "=== Generating releases manifest ==="
python windows/generate_releases.py

Write-Host "=== Building Lucy.exe (PyInstaller) ==="
python -m pip install --quiet pyinstaller
$icon = Join-Path $Root "windows\assets\lucy-icon.ico"
if (-not (Test-Path $icon)) {
    Write-Error "Missing icon: $icon"
}
python -m PyInstaller --noconfirm --onefile --name Lucy `
    --icon $icon `
    --hidden-import install_ops `
    --hidden-import install_runner `
    --paths (Join-Path $Root "windows") `
    (Join-Path $Root "windows\Lucy.py")

if (-not (Test-Path "dist\Lucy.exe")) {
    Write-Error "PyInstaller did not produce dist\Lucy.exe"
}

$MakeNsis = @(
    (Get-Command makensis -ErrorAction SilentlyContinue).Source,
    "${env:ProgramFiles(x86)}\NSIS\makensis.exe",
    "$env:ProgramFiles\NSIS\makensis.exe"
) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1

if (-not $MakeNsis) {
    Write-Warning "NSIS (makensis) not found. Lucy.exe is at dist\Lucy.exe"
    Write-Warning "Install NSIS to build Lucy-Setup.exe: https://nsis.sourceforge.io/Download"
    exit 0
}

if (-not $Version) {
    try {
        $tag = git describe --tags --exact-match 2>$null
        if ($tag -match '^v(.+)$') { $Version = $Matches[1] }
    } catch {}
}
if (-not $Version) { $Version = "0.0.0-dev" }

Write-Host "=== Building Lucy-Setup.exe (NSIS, version $Version) ==="
& $MakeNsis "/DMyAppVersion=$Version" (Join-Path $Root "windows\installer\Lucy.nsi")

Write-Host "=== Done ==="
Write-Host "  dist\Lucy.exe"
Write-Host "  dist\Lucy-Setup-$Version.exe"
