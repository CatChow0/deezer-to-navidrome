<#
.SYNOPSIS
  Builds and signs the Android app on this PC into dist\android, as Jenkins does.
.DESCRIPTION
  The key and its password come from the folder new-keystore.ps1 made. The
  password is saved with DPAPI, so only this Windows account can read it; it is
  decrypted for this process only, then build-apk.sh runs the Docker build.
.PARAMETER KeyDir
  The folder holding release.jks and keystore-password.dpapi.
#>
param([string]$KeyDir = (Join-Path $env:USERPROFILE ".d2n-android"))

$ErrorActionPreference = "Stop"
$key = Join-Path $KeyDir "release.jks"
$saved = Join-Path $KeyDir "keystore-password.dpapi"
if (-not (Test-Path $key) -or -not (Test-Path $saved)) {
    throw "Create the key first: powershell -File android\scripts\new-keystore.ps1"
}

# Git Bash runs build-apk.sh; WSL's bash would not see this process's variables.
$bash = $null
$folder = Split-Path (Get-Command git -ErrorAction Stop).Source -Parent
for ($i = 0; $i -lt 3 -and $folder; $i++) {
    $candidate = Join-Path $folder "bin\bash.exe"
    if (Test-Path $candidate) { $bash = $candidate; break }
    $folder = Split-Path $folder -Parent
}
if (-not $bash) { throw "Git Bash is needed: bin\bash.exe was not found next to git." }

$secure = Get-Content $saved | ConvertTo-SecureString
$env:D2N_KEYSTORE_FILE = (Resolve-Path $key).Path
$env:D2N_KEYSTORE_PASSWORD = [System.Net.NetworkCredential]::new("", $secure).Password
try {
    & $bash (Join-Path $PSScriptRoot "build-apk.sh")
    if ($LASTEXITCODE -ne 0) { throw "The Android build failed (exit $LASTEXITCODE)." }
}
finally {
    Remove-Item Env:D2N_KEYSTORE_PASSWORD, Env:D2N_KEYSTORE_FILE -ErrorAction SilentlyContinue
}
