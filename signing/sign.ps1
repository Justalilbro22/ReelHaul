# Signs ReelHaul's exe files if a code-signing certificate is available.
#
# Put the certificate at signing\cert.pfx and set the password once:
#   setx REELHAUL_CERT_PASSWORD "your password"
# Alternatively install the certificate in the Windows user store and set
# the subject in signing\subject.txt.
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("app", "setup")]
    [string]$Stage
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

function Find-Signtool {
    $found = Get-ChildItem "C:\Program Files (x86)\Windows Kits\10\bin" -Recurse -Filter "signtool.exe" -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -like "*x64*" } |
        Sort-Object FullName -Descending |
        Select-Object -First 1 -ExpandProperty FullName
    if (-not $found) { $found = (Get-Command signtool.exe -ErrorAction SilentlyContinue).Source }
    if (-not $found) { throw "signtool.exe not found. Install the Windows SDK." }
    return $found
}

$targets = @()
if ($Stage -eq "app") {
    $targets += Join-Path $root "dist\ReelHaul\ReelHaul.exe"
} else {
    $targets += Get-ChildItem (Join-Path $root "release\ReelHaul-Setup-*.exe") -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty FullName
}
if (-not $targets) {
    Write-Host "sign: nothing to sign for stage '$Stage' (built first?)"
    exit 0
}

$signtool = Find-Signtool
$timeServers = @("http://timestamp.digicert.com", "http://timestamp.sectigo.com")
$common = @("sign", "/fd", "SHA256", "/td", "SHA256", "/d", "ReelHaul - free 4K video & audio downloader")

$certPfx = Join-Path $root "signing\cert.pfx"
$subjectFile = Join-Path $root "signing\subject.txt"
$signedAny = $false

foreach ($target in $targets) {
    if (-not (Test-Path $target)) {
        Write-Host "sign: missing $target"
        continue
    }
    $args = $null
    if (Test-Path $certPfx) {
        $password = [Environment]::GetEnvironmentVariable("REELHAUL_CERT_PASSWORD")
        if (-not $password) {
            $password = Read-Host -Prompt "Password for cert.pfx"
        }
        $args = $common + @("/f", $certPfx, "/p", $password)
    } elseif (Test-Path $subjectFile) {
        $subject = (Get-Content $subjectFile -Raw).Trim()
        $args = $common + @("/n", $subject)
    } else {
        Write-Host "sign: no certificate found - skipping $([IO.Path]::GetFileName($target))"
        Write-Host "      add signing\cert.pfx (+ setx REELHAUL_CERT_PASSWORD) or signing\subject.txt"
        continue
    }

    $signed = $false
    foreach ($server in $timeServers) {
        $fullArgs = $args + @("/tr", $server, $target)
        & $signtool @fullArgs | Out-Null
        if ($LASTEXITCODE -eq 0) { $signed = $true; break }
    }
    if ($signed) {
        Write-Host "sign: OK  $target"
        $signedAny = $true
    } else {
        Write-Warning "sign: FAILED $target"
        exit 1
    }
}

if ($signedAny) {
    foreach ($target in $targets | Where-Object { Test-Path $_ }) {
        & $signtool verify /pa /all $target | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "sign: verification failed for $target"
            exit 1
        }
        Write-Host "sign: verified $target"
    }
}
exit 0
