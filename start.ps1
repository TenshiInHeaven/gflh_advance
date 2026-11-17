param(
    [switch]$WithEmulator,
    [switch]$CheckOnly,
    [switch]$NoPause,
    [int]$Port = 0
)

$ErrorActionPreference = 'Stop'
$Root = $PSScriptRoot
Set-Location -LiteralPath $Root

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

function Write-Step {
    param([string]$Message)
    Write-Host ''
    Write-Host "==> $Message" -ForegroundColor Cyan
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
    $candidates = @(9178, 7813, 9191)
    if ($Requested -gt 0) {
        if ($Requested -lt 1024 -or $Requested -gt 65535) {
            Stop-WithMessage "Port $Requested is invalid. Use 1024-65535."
        }
        if (-not (Test-PortAvailable $Requested)) {
            Stop-WithMessage "Port $Requested is already in use. Close the other program or choose another port."
        }
        return $Requested
    }
    foreach ($candidate in $candidates) {
        if (Test-PortAvailable $candidate) { return $candidate }
    }
    Stop-WithMessage "All preferred ports are in use: $($candidates -join ', ').`nClose one of those programs, or start manually with a custom port:`n  .\start.ps1 -Port 8765`n  python -m targetforge --port 8765 --open"
}

try {
    Write-Host 'TargetForge one-click setup' -ForegroundColor Green
    Write-Host "Folder: $Root"

    if (-not (Test-Path -LiteralPath (Join-Path $Root 'targetforge'))) {
        Stop-WithMessage "This folder does not look like TargetForge (targetforge/ not found).`nPut this script in the TargetForge folder."
    }

    $venvDir = Join-Path $Root '.venv'
    $venvPython = Join-Path $venvDir 'Scripts\python.exe'
    $haveVenv = Test-Path -LiteralPath $venvPython
    $pythonExe = $null
    $pythonArgs = @()

    if ($haveVenv) {
        Write-Step "Virtual environment found: $venvDir"
        $pythonExe = $venvPython
    } else {
        if (Test-Path -LiteralPath $venvDir) {
            Stop-WithMessage ".venv exists but Scripts\python.exe is missing. Delete the .venv folder and run again."
        }

        $py = Get-Command python -ErrorAction SilentlyContinue
        if ($null -ne $py) {
            $pythonExe = $py.Source
        } else {
            $pyLauncher = Get-Command py -ErrorAction SilentlyContinue
            if ($null -ne $pyLauncher) {
                $pythonExe = $pyLauncher.Source
                $pythonArgs = @('-3')
            }
        }

        if ($null -eq $pythonExe) {
            Stop-WithMessage "Python was not found.`nInstall Python 3.10+ from https://www.python.org/downloads/`nDuring installation, tick 'Add python.exe to PATH', then run start.bat again."
        }

        Write-Step "Python found: $pythonExe"
        & $pythonExe @pythonArgs -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 2)"
        if ($LASTEXITCODE -ne 0) {
            Stop-WithMessage "Python 3.10 or newer is required. Please install it from https://www.python.org/downloads/."
        }

        if ($CheckOnly) {
            Write-Host ''
            Write-Host '[OK] Python is available. .venv does not exist yet; normal start.bat would create it.' -ForegroundColor Green
            Write-Host '     -CheckOnly was used, so nothing was created.'
            exit 0
        }

        Write-Step 'Creating local virtual environment .venv ...'
        & $pythonExe @pythonArgs -m venv $venvDir
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $venvPython)) {
            Stop-WithMessage "Failed to create .venv. If Python came from Microsoft Store, install it from python.org instead."
        }
        $pythonExe = $venvPython
    }

    & $pythonExe -c "import sys; print(sys.version.split()[0])"
    if ($LASTEXITCODE -ne 0) {
        Stop-WithMessage "The Python environment is broken. Delete .venv and run start.bat again."
    }

    if ($CheckOnly) {
        Write-Host ''
        Write-Host '[OK] Python and virtual environment checks passed.' -ForegroundColor Green
        Write-Host '     -CheckOnly was used, so no packages were installed and TargetForge was not started.'
        exit 0
    }

    $requirements = Join-Path $Root 'requirements.lock'
    if (-not (Test-Path -LiteralPath $requirements)) {
        Stop-WithMessage 'requirements.lock not found. The download is incomplete; re-extract the release package.'
    }

    Write-Step 'Installing locked dependencies (first run may take a few minutes) ...'
    & $pythonExe -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) {
        Stop-WithMessage 'pip upgrade failed. Check your network connection or proxy.'
    }
    & $pythonExe -m pip install --require-hashes -r $requirements
    if ($LASTEXITCODE -ne 0) {
        Stop-WithMessage 'Dependency installation failed. Check your network connection or proxy.'
    }

    if ($WithEmulator) {
        $emuRequirements = Join-Path $Root 'requirements-emulator.txt'
        if (-not (Test-Path -LiteralPath $emuRequirements)) {
            Stop-WithMessage 'requirements-emulator.txt not found. Use the full release package or run without -WithEmulator.'
        }
        Write-Step 'Installing optional emulator capture dependencies ...'
        & $pythonExe -m pip install -r $emuRequirements
        if ($LASTEXITCODE -ne 0) {
            Stop-WithMessage 'Optional emulator dependency installation failed. You can run without -WithEmulator for PC mode.'
        }
    }

    $chosenPort = Select-ServicePort $Port
    Write-Step "Starting TargetForge on port $chosenPort ..."
    Write-Host "Web page: http://127.0.0.1:$chosenPort/ (the console title will also include the token URL)"
    Write-Host 'A browser tab will open. Keep this window open while TargetForge is running.'
    & $pythonExe -m targetforge --port $chosenPort --open
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
        Stop-WithMessage "TargetForge exited with code $exitCode. Check the messages above."
    }
    if (-not $NoPause) {
        Write-Host ''
        Write-Host 'TargetForge stopped.' -ForegroundColor Yellow
        Read-Host 'Press Enter to close'
    }
    exit 0
} catch {
    Stop-WithMessage ("Unexpected error: " + $_.Exception.Message)
}
