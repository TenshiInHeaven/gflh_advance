param(
    [switch]$WithEmulator,
    [switch]$CheckOnly,
    [switch]$NoPause
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

    Write-Step 'Starting TargetForge ...'
    Write-Host 'A browser tab will open. Keep this window open while TargetForge is running.'
    & $pythonExe -m targetforge --open
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
