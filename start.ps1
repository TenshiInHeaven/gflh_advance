param(
    [switch]$WithEmulator
)

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

$venv = Join-Path $PSScriptRoot '.venv'
$python = Join-Path $venv 'Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    Write-Host 'Creating virtual environment .venv ...' -ForegroundColor Cyan
    python -m venv $venv
}

Write-Host 'Installing locked core dependencies (requirements.lock) ...' -ForegroundColor Cyan
& $python -m pip install --upgrade pip | Out-Host
& $python -m pip install --require-hashes -r requirements.lock | Out-Host

if ($WithEmulator) {
    if (-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'requirements-emulator.txt'))) {
        throw 'requirements-emulator.txt not found'
    }
    Write-Host 'Installing optional emulator capture dependencies (mitmproxy / cryptography) ...' -ForegroundColor Cyan
    & $python -m pip install -r requirements-emulator.txt | Out-Host
} else {
    Write-Host 'Emulator capture is optional. Re-run with  .\start.ps1 -WithEmulator  to install mitmproxy/cryptography.' -ForegroundColor DarkGray
}

Write-Host 'Starting TargetForge ...' -ForegroundColor Cyan
& $python -m targetforge --open
