$ErrorActionPreference = "Continue"

$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot ".venv\Scripts\python.exe"
$logDirectory = Join-Path $projectRoot "data\logs"
$logPath = Join-Path $logDirectory "local-server.log"

New-Item -ItemType Directory -Force -Path $logDirectory | Out-Null
Set-Location -LiteralPath $projectRoot

while ($true) {
    try {
        $response = Invoke-WebRequest `
            -UseBasicParsing `
            -Uri "http://127.0.0.1:8000/health" `
            -TimeoutSec 3
        if ($response.StatusCode -eq 200) {
            Start-Sleep -Seconds 15
            continue
        }
    }
    catch {
        # No healthy server is listening; start or restart it below.
    }

    if (-not (Test-Path -LiteralPath $pythonPath)) {
        Add-Content -LiteralPath $logPath -Value (
            "$(Get-Date -Format o) Python virtual environment is missing."
        )
        Start-Sleep -Seconds 30
        continue
    }

    Add-Content -LiteralPath $logPath -Value (
        "$(Get-Date -Format o) Starting FastAPI server."
    )
    & $pythonPath -m uvicorn app.main:app `
        --host 127.0.0.1 `
        --port 8000 *>> $logPath

    Add-Content -LiteralPath $logPath -Value (
        "$(Get-Date -Format o) Server stopped; retrying in 5 seconds."
    )
    Start-Sleep -Seconds 5
}
