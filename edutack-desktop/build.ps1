$ErrorActionPreference = "Stop"

$uv = Get-Command uv -ErrorAction SilentlyContinue
if (-not $uv) {
    throw "No se encontró uv. Instálalo antes de compilar EduTrack Desktop."
}

Push-Location $PSScriptRoot
try {
    & uv sync --group dev
    if ($LASTEXITCODE -ne 0) {
        throw "uv sync terminó con código $LASTEXITCODE."
    }

    & uv run pyinstaller --noconfirm --clean "EduTrackDesktop.spec"
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller terminó con código $LASTEXITCODE."
    }
}
finally {
    Pop-Location
}
