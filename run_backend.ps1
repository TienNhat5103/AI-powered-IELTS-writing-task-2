param(
    [switch]$Install,
    [switch]$NoReload,
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$projectRoot = $PSScriptRoot
$venvPython = Join-Path $projectRoot "venv\Scripts\python.exe"
$requirementsFile = Join-Path $projectRoot "requirements.txt"
$backendDirectory = Join-Path $projectRoot "backend"
$envFile = Join-Path $backendDirectory ".env"
$envExample = Join-Path $backendDirectory ".env.example"

if (-not (Test-Path -LiteralPath $venvPython)) {
    $pythonLauncher = Get-Command py -ErrorAction SilentlyContinue
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue

    if ($pythonLauncher) {
        & $pythonLauncher.Source -3.12 -m venv (Join-Path $projectRoot "venv")
        if ($LASTEXITCODE -ne 0) {
            & $pythonLauncher.Source -3.11 -m venv (Join-Path $projectRoot "venv")
        }
        if ($LASTEXITCODE -ne 0) {
            throw "Python 3.11 or 3.12 is required. Install Python, then run this script again."
        }
    }
    elseif ($pythonCommand) {
        & $pythonCommand.Source -m venv (Join-Path $projectRoot "venv")
    }
    else {
        throw "Python 3.11 or 3.12 is required. Install Python, then run this script again."
    }

    $Install = $true
}

if ($Install) {
    & $venvPython -m pip install --upgrade pip
    & $venvPython -m pip install -r $requirementsFile
}

if (-not (Test-Path -LiteralPath $envFile)) {
    Copy-Item -LiteralPath $envExample -Destination $envFile
    Write-Host "Created backend/.env. Add GEMINI_API_KEY before evaluating an essay."
}

$uvicornArguments = @(
    "-m", "uvicorn",
    "backend.main:app",
    "--host", "0.0.0.0",
    "--port", $Port.ToString()
)

if (-not $NoReload) {
    $uvicornArguments += "--reload"
}

Push-Location $projectRoot
try {
    & $venvPython @uvicornArguments
}
finally {
    Pop-Location
}
