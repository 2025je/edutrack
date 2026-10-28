param(
    [switch]$SkipInstaller
)

$ErrorActionPreference = "Stop"

$uv = Get-Command uv -ErrorAction SilentlyContinue
if (-not $uv) {
    throw "No se encontró uv. Instálalo antes de compilar EduTrack Desktop."
}

$isccPath = $null
$isccCommand = Get-Command ISCC.exe -ErrorAction SilentlyContinue
if ($isccCommand) {
    $isccPath = $isccCommand.Source
}
else {
    $isccCandidates = @()
    if ($env:LOCALAPPDATA) {
        $isccCandidates += Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"
    }
    if (${env:ProgramFiles(x86)}) {
        $isccCandidates += Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"
    }
    if ($env:ProgramFiles) {
        $isccCandidates += Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe"
    }
    $isccPath = $isccCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
}
if (-not $SkipInstaller -and -not $isccPath) {
    throw "No se encontró Inno Setup 6 (ISCC.exe). Instálalo para generar el instalador o ejecuta .\build.ps1 -SkipInstaller para crear solo el ejecutable."
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
    if (-not (Test-Path "dist\EduTrackDesktop.exe")) {
        throw "PyInstaller terminó sin generar dist\EduTrackDesktop.exe."
    }

    if (-not $SkipInstaller) {
        $versionLine = Select-String -Path "pyproject.toml" -Pattern '^\s*version\s*=\s*"([^"]+)"' | Select-Object -First 1
        if (-not $versionLine) {
            throw "No se pudo leer la versión de pyproject.toml."
        }
        $appVersion = $versionLine.Matches[0].Groups[1].Value
        & $isccPath "/DAppVersion=$appVersion" "EduTrackDesktop.iss"
        if ($LASTEXITCODE -ne 0) {
            throw "Inno Setup terminó con código $LASTEXITCODE."
        }
    }
}
finally {
    Pop-Location
}
