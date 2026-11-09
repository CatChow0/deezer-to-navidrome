<#
.SYNOPSIS
  Creates the Android app's signing key, once.
.DESCRIPTION
  Run it in a PowerShell window of your own, so the password never passes
  through anything else. The key goes in %USERPROFILE%\.d2n-android\release.jks,
  and its password is saved there with DPAPI, readable by this Windows account
  only, for build-apk.ps1.

  Keep the key and its password: phones can only update the app with this same
  key. Without them, the app must be uninstalled on every phone.
.PARAMETER KeyDir
  Where to create release.jks and keystore-password.dpapi.
#>
param([string]$KeyDir = (Join-Path $env:USERPROFILE ".d2n-android"))

$ErrorActionPreference = "Stop"
$key = Join-Path $KeyDir "release.jks"
if (Test-Path $key) {
    throw "A key already exists in $KeyDir. Keep it: phones can only update the app with this same key, and losing it means reinstalling the app on every phone."
}

$first = Read-Host "Choose the key's password (12 characters or more)" -AsSecureString
$second = Read-Host "Type it again" -AsSecureString
$plain = [System.Net.NetworkCredential]::new("", $first).Password
if ($plain -ne [System.Net.NetworkCredential]::new("", $second).Password) { throw "The two passwords differ." }
if ($plain.Length -lt 12) { throw "Use 12 characters or more." }

# keytool comes with the JDK; Oracle's installer only puts java on the PATH.
$keytool = if ($env:JAVA_HOME -and (Test-Path (Join-Path $env:JAVA_HOME "bin\keytool.exe"))) {
    Join-Path $env:JAVA_HOME "bin\keytool.exe"
} elseif (Get-Command keytool -ErrorAction SilentlyContinue) {
    (Get-Command keytool).Source
} else {
    $javaHome = (& java -XshowSettings:properties -version 2>&1 | Select-String "java.home = (.+)").Matches.Groups[1].Value.Trim()
    Join-Path $javaHome "bin\keytool.exe"
}
if (-not (Test-Path $keytool)) { throw "keytool was not found: install a JDK, or set JAVA_HOME." }

New-Item -ItemType Directory -Force $KeyDir | Out-Null
# keytool reads the password from this variable, never from its command line.
$env:D2N_KS_PASS = $plain
try {
    & $keytool -genkeypair -keystore $key -storetype PKCS12 -storepass:env D2N_KS_PASS -alias d2n `
        -keyalg RSA -keysize 4096 -validity 10950 -dname "CN=Deezer to Navidrome, O=CatChow0"
    if ($LASTEXITCODE -ne 0) { throw "keytool failed (exit $LASTEXITCODE)." }
}
finally {
    Remove-Item Env:D2N_KS_PASS -ErrorAction SilentlyContinue
}
ConvertFrom-SecureString $first | Set-Content -Encoding ascii (Join-Path $KeyDir "keystore-password.dpapi")

Write-Host ""
Write-Host "The key is in $key, and its password is saved for this Windows account only."
Write-Host "Back up release.jks and its password now, somewhere safe off this PC, such as a password manager."
Write-Host "Without them, phones must uninstall the app to update it."
Write-Host "Jenkins needs them too: credentials android-keystore (secret file) and android-keystore-password (secret text)."
