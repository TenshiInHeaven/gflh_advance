param(
    [int]$Port = 0,
    [switch]$NoPause,
    [switch]$CheckOnly
)

$ErrorActionPreference = 'Stop'
$Root = $PSScriptRoot
Set-Location -LiteralPath $Root
$PreferredPorts = @(9178, 7813, 9191)

function Stop-WithMessage {
    param([string]$Message, [int]$Code = 1)
    Write-Host ''
    Write-Host "[ERROR] $Message" -ForegroundColor Red
    if (-not $NoPause) {
        Write-Host ''
        Read-Host 'Press Enter to close'
    }
    exit $Code
}

function Test-PortAvailable {
    param([int]$Candidate)
    $listener = $null
    try {
        $listener = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Loopback, $Candidate)
        $listener.Start()
        return $true
    } catch {
        return $false
    } finally {
        if ($null -ne $listener) { $listener.Stop() }
    }
}

function Select-ServicePort {
    param([int]$Requested)
    if ($Requested -gt 0) {
        if ($Requested -lt 1024 -or $Requested -gt 65535) {
            Stop-WithMessage "Port $Requested is invalid. Use 1024-65535."
        }
        if (-not (Test-PortAvailable $Requested)) {
            Stop-WithMessage "Port $Requested is already in use."
        }
        return $Requested
    }
    foreach ($candidate in $PreferredPorts) {
        if (Test-PortAvailable $candidate) { return $candidate }
    }
    Stop-WithMessage "All preferred ports are in use: $($PreferredPorts -join ', ').`nClose one of those programs, or start with a custom port:`n  pwsh -File .\serve.ps1 -Port 8765"
}

if (-not (Test-Path -LiteralPath (Join-Path $Root 'targetforge'))) {
    Stop-WithMessage 'targetforge/ not found. Put serve.ps1 in the TargetForge folder.'
}

$venvPython = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $venvPython)) {
    Stop-WithMessage 'No .venv found. Double-click start.bat once to install the environment, then use serve.bat.'
}

& $venvPython -c "import sys; print('Python ' + sys.version.split()[0])"
if ($LASTEXITCODE -ne 0) {
    Stop-WithMessage '.venv is broken. Delete .venv and run start.bat again.'
}

$chosenPort = Select-ServicePort $Port
$Host.UI.RawUI.WindowTitle = "TargetForge - port $chosenPort"

Write-Host ''
Write-Host 'TargetForge service launcher' -ForegroundColor Green
Write-Host "Local web page: http://127.0.0.1:$chosenPort/"
Write-Host 'The console title will include the application name and the token URL.'
Write-Host ''

if ($CheckOnly) {
    Write-Host "[OK] Python and .venv are ready; selected port $chosenPort is free." -ForegroundColor Green
    Write-Host '     -CheckOnly was used, so the service was not started.'
    exit 0
}

& $venvPython -m targetforge --port $chosenPort --open
$exitCode = $LASTEXITCODE
if ($exitCode -ne 0) {
    Stop-WithMessage "TargetForge exited with code $exitCode. See the messages above."
}
if (-not $NoPause) {
    Write-Host ''
    Write-Host 'TargetForge stopped.' -ForegroundColor Yellow
    Read-Host 'Press Enter to close'
}
exit 0
