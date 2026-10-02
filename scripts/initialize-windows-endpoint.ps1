# Invoked by the installer with elevation. Enrollment contains public connection settings only.
param(
    [Parameter(Mandatory=$true)][string]$InstallDirectory,
    [string]$EnrollmentPath = '',
    [string]$RustDeskInstaller = ''
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$deployment = Join-Path $InstallDirectory 'deployment.json'
if ($EnrollmentPath) {
    $cfg = Get-Content -LiteralPath $EnrollmentPath -Raw | ConvertFrom-Json
    if (([Uri]$cfg.profile.broker_url).Scheme -ne 'https') { throw 'Enrollment requires HTTPS.' }
    $caSource = $cfg.profile.ca_file
    if (-not [IO.Path]::IsPathRooted($caSource)) {
        $caSource = Join-Path (Split-Path -Parent $EnrollmentPath) $caSource
    }
    $ca = Join-Path $InstallDirectory 'broker-ca.pem'
    if ([IO.Path]::GetFullPath($caSource) -ne [IO.Path]::GetFullPath($ca)) { Copy-Item -LiteralPath $caSource -Destination $ca -Force }
    $cfg.profile.ca_file = $ca
    [IO.File]::WriteAllText($deployment, ($cfg | ConvertTo-Json -Depth 6), (New-Object Text.UTF8Encoding($false)))
} elseif (Test-Path $deployment) {
    $cfg = Get-Content -LiteralPath $deployment -Raw | ConvertFrom-Json
} else { throw 'A company enrollment JSON is required on first installation.' }
$exe = Join-Path $env:ProgramFiles 'RustDesk\rustdesk.exe'
if (-not (Test-Path $exe)) {
    & (Join-Path $PSScriptRoot 'setup-windows-rustdesk.ps1') -IdServer $cfg.rustdesk.id_server -RelayServer $cfg.rustdesk.relay_server -ServerKey $cfg.rustdesk.key -InstallerPath $RustDeskInstaller
} else {
    & $exe --option custom-rendezvous-server $cfg.rustdesk.id_server | Out-Null
    & $exe --option relay-server $cfg.rustdesk.relay_server | Out-Null
    & $exe --option key $cfg.rustdesk.key | Out-Null
}
if (-not (Test-Path $exe)) { throw 'RustDesk is not installed.' }
Set-Service RustDesk -StartupType Automatic
Start-Service RustDesk
& sc.exe failure RustDesk reset= 86400 actions= restart/5000/restart/15000/restart/30000 | Out-Null
Write-Output 'Endpoint enrollment complete.'
