@echo off
chcp 65001 >nul
pushd "%~dp0"
start "TargetForge" powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0serve.ps1" %*
popd
