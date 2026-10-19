$ErrorActionPreference = 'Stop'
$desktopRoot = Split-Path $PSScriptRoot -Parent
$repoRoot = Split-Path $desktopRoot -Parent
if (Test-Path G:\) {
    if ((Get-PSDrive G).Free -lt 5GB) { throw 'At least 5 GB of free space is required on G:.' }
    $env:npm_config_cache = 'G:\DevCache\npm'
    $env:PIP_CACHE_DIR = 'G:\DevCache\pip'
    $env:ELECTRON_CACHE = 'G:\DevCache\electron'
    $env:ELECTRON_BUILDER_CACHE = 'G:\DevCache\electron-builder'
    $env:TEMP = 'G:\DevCache\Temp\easy-coding-agents'
    $env:TMP = $env:TEMP
    New-Item -ItemType Directory -Force -Path $env:TEMP | Out-Null
}
$env:CSC_IDENTITY_AUTO_DISCOVERY = 'false'
Push-Location $desktopRoot
try {
    npm ci
    if ($LASTEXITCODE) { throw 'npm ci failed' }
    if (!(Test-Path '.venv\Scripts\python.exe')) { python -m venv .venv }
    & .venv\Scripts\python.exe -m pip install -r requirements-build.lock
    if ($LASTEXITCODE) { throw 'Python dependency installation failed' }
    & .venv\Scripts\python.exe scripts/build-runtime.py
    if ($LASTEXITCODE) { throw 'Backend build failed' }
    npm run package
    if ($LASTEXITCODE) { throw 'Installer build failed' }
    $hashLines = Get-ChildItem "$repoRoot\output\release\desktop\*.exe" | ForEach-Object {
        $digest = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        "$digest  $($_.Name)"
    }
    $hashLines | Set-Content -LiteralPath "$repoRoot\output\release\desktop\SHA256SUMS.txt" -Encoding ascii
    $hashLines
} finally { Pop-Location }
