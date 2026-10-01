# Run elevated inside the Windows VM. Never pass a Windows/OpenStack password here.
param(
    [Parameter(Mandatory = $true)][string]$IdServer,
    [Parameter(Mandatory = $true)][string]$RelayServer,
    [Parameter(Mandatory = $true)][string]$ServerKey,
    [string]$InstallerPath = ''
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this script as administrator.'
}

$stateDir = Join-Path $env:ProgramData 'OpenStackVDI'
New-Item -ItemType Directory -Force $stateDir | Out-Null
# The saved unattended-access password is readable only by SYSTEM/Administrators.
& icacls.exe $stateDir /inheritance:r /grant:r '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Could not protect the credential directory.' }

$exe = Join-Path $env:ProgramFiles 'RustDesk\rustdesk.exe'
$freshInstall = -not (Test-Path $exe)
if ($freshInstall) {
    $installer = $InstallerPath
    if (-not $installer) {
        $installer = Join-Path $stateDir 'rustdesk-1.4.9-x86_64.exe'
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -UseBasicParsing -TimeoutSec 300 `
            -Uri 'https://github.com/rustdesk/rustdesk/releases/download/1.4.9/rustdesk-1.4.9-x86_64.exe' `
            -OutFile $installer
    }
    $expected = 'eaedeb0088e687bf46f7c46a9c6ea5493ce51f3134dfd6acbedb47b5b9136274'
    if ((Get-FileHash $installer -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected) {
        throw 'RustDesk installer checksum mismatch.'
    }
    # Start-Process -Wait also waits for long-lived child processes on Windows.
    $process = Start-Process -FilePath $installer -ArgumentList '--silent-install' -PassThru
    if (-not $process.WaitForExit(120000)) { throw 'RustDesk installer timed out.' }
    if ($process.ExitCode -ne 0) { throw 'RustDesk installation failed.' }
    for ($attempt = 0; $attempt -lt 30 -and -not (Test-Path $exe); $attempt++) { Start-Sleep 2 }
    if (-not (Test-Path $exe)) { throw 'RustDesk executable was not installed.' }
    if (-not $InstallerPath) { Remove-Item $installer }
}

$service = Get-CimInstance Win32_Service -Filter "Name='RustDesk'"
if (-not $freshInstall -and (-not $service -or $service.PathName -notmatch '--service(?:\s|$)')) {
    $process = Start-Process -FilePath $exe -ArgumentList '--install-service' -PassThru
    if (-not $process.WaitForExit(120000)) { throw 'RustDesk service installation timed out.' }
    if ($process.ExitCode -ne 0) { throw 'RustDesk service installation failed.' }
}
# The installer creates a temporary --import-config service before the real one.
# Executable presence and the installer's parent exit do not mean this is finished.
$deadline = [DateTime]::UtcNow.AddSeconds(180)
do {
    $service = Get-CimInstance Win32_Service -Filter "Name='RustDesk'"
    if ($service -and $service.PathName -match '--service(?:\s|$)') { break }
    Start-Sleep 2
} while ([DateTime]::UtcNow -lt $deadline)
if (-not $service -or $service.PathName -notmatch '--service(?:\s|$)') {
    throw 'RustDesk installer has not finished creating its runtime service. Retry after Windows setup completes.'
}
Set-Service RustDesk -StartupType Automatic
Start-Service RustDesk
(Get-Service RustDesk).WaitForStatus('Running', [TimeSpan]::FromSeconds(60))
Start-Sleep 5
& $exe --option custom-rendezvous-server $IdServer | Out-Null
& $exe --option relay-server $RelayServer | Out-Null
& $exe --option key $ServerKey | Out-Null

$credentialFile = Join-Path $stateDir 'rustdesk-access.json'
if (Test-Path $credentialFile) {
    $password = (Get-Content $credentialFile -Raw | ConvertFrom-Json).password
} else {
    $bytes = New-Object byte[] 24
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    $password = [Convert]::ToBase64String($bytes)
}
if (-not $password) { throw 'Unattended password is empty.' }
& $exe --option verification-method use-permanent-password | Out-Null
$passwordResult = ((& $exe --password $password | Out-String).Trim())
if ($passwordResult -ne 'Done!') {
    throw 'RustDesk did not acknowledge the unattended password setting.'
}
Start-Sleep 3
Restart-Service RustDesk
Start-Sleep 10
$id = ((& $exe --get-id | Out-String).Trim())
if ($id -notmatch '^\d{6,}$') { throw 'RustDesk has not returned a valid ID yet.' }
$actualServer = ((& $exe --option custom-rendezvous-server | Out-String).Trim())
if ($actualServer -ne $IdServer) { throw 'RustDesk server setting was not applied.' }
$actualMethod = ((& $exe --option verification-method | Out-String).Trim())
if ($actualMethod -ne 'use-permanent-password') {
    throw 'RustDesk permanent-password authentication was not applied.'
}
@{ id = $id; password = $password; server = $IdServer } |
    ConvertTo-Json | Set-Content -Encoding UTF8 $credentialFile
# Intentionally never print the password.
@{ id = $id; server = $actualServer; service = (Get-Service RustDesk).Status.ToString(); credential_file = $credentialFile } |
    ConvertTo-Json -Compress
