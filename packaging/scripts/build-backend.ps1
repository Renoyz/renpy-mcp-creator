$ErrorActionPreference = "Stop"

function Invoke-Checked {
    param([scriptblock]$Command)
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code $LASTEXITCODE"
    }
}

Push-Location "$PSScriptRoot/../.."
Invoke-Checked { uv run --extra packaging python -m PyInstaller packaging/pyinstaller/renpy-mcp-electron.spec --distpath packaging/dist --workpath packaging/build --noconfirm }
$backendExe = Join-Path (Get-Location) "packaging/dist/renpy-mcp-electron/renpy-mcp-electron.exe"
if (-not (Test-Path $backendExe)) {
    throw "Backend executable was not created: $backendExe"
}
Pop-Location
