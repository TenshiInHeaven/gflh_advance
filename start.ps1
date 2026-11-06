# TargetForge 一键启动（Windows / Python 3.10+）
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

$venv = Join-Path $PSScriptRoot '.venv'
$python = Join-Path $venv 'Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    Write-Host '创建虚拟环境 .venv ...' -ForegroundColor Cyan
    python -m venv $venv
}

Write-Host '安装锁定依赖（hash 校验）...' -ForegroundColor Cyan
& $python -m pip install --upgrade pip | Out-Host
& $python -m pip install --require-hashes -r requirements.lock | Out-Host

Write-Host '启动靶机工坊...' -ForegroundColor Cyan
& $python -m targetforge --open
