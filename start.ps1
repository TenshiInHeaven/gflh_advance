# TargetForge 一键启动（Windows / Python 3.10+）
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
Write-Host '检查依赖...' -ForegroundColor Cyan
python -m pip install -r requirements.txt | Out-Host
Write-Host '启动靶机工坊...' -ForegroundColor Cyan
python -m targetforge --open
