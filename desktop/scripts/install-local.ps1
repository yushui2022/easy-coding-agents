param(
    [string]$InstallDirectory = 'G:\Apps\ECA Desktop',
    [string]$Installer
)
$ErrorActionPreference = 'Stop'
$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$version = (Get-Content -LiteralPath (Join-Path $projectRoot 'desktop\package.json') -Raw | ConvertFrom-Json).version
if (-not $Installer) { $Installer = Join-Path $projectRoot "output\release\desktop\ECA-Desktop-$version-x64-Setup.exe" }
$Installer = (Resolve-Path -LiteralPath $Installer).Path
$appPath = Join-Path ([System.IO.Path]::GetFullPath($InstallDirectory)) 'ECA Desktop.exe'
if (Get-Process -Name 'ECA Desktop' -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $appPath }) {
    throw 'Exit ECA Desktop before replacing its installed files.'
}
$installerTemp = if (Test-Path -LiteralPath 'G:\') { 'G:\DevCache\Temp\easy-coding-agents\installer' } else { Join-Path $projectRoot 'output\installer-temp' }
$drive = Get-PSDrive -Name ([System.IO.Path]::GetPathRoot($installerTemp).Substring(0,1))
if ($drive.Free -lt 2GB) { throw 'At least 2 GiB of temporary disk space is required.' }
New-Item -ItemType Directory -Path $installerTemp -Force | Out-Null
$previousTemp, $previousTmp = $env:TEMP, $env:TMP
try {
    $env:TEMP = $installerTemp
    $env:TMP = $installerTemp
    Write-Output "Install: $InstallDirectory; extraction: $installerTemp"
    $process = Start-Process -FilePath $Installer -ArgumentList "/S /D=$InstallDirectory" -WindowStyle Hidden -Wait -PassThru
    if ($process.ExitCode -ne 0) { throw "Installer failed with exit code $($process.ExitCode)." }
    # This developer verification script uses Node; the installed app does not.
    & node (Join-Path $PSScriptRoot 'verify-install.cjs') $InstallDirectory
    if ($LASTEXITCODE -ne 0) { throw 'Installed files or backend handshake failed verification.' }
} finally {
    $env:TEMP, $env:TMP = $previousTemp, $previousTmp
}
