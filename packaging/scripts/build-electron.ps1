$ErrorActionPreference = "Stop"

function Invoke-Checked {
    param([scriptblock]$Command)
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code $LASTEXITCODE"
    }
}

Push-Location "$PSScriptRoot/../../desktop"
Invoke-Checked { npm ci }
Invoke-Checked { npm run dist }
Pop-Location
