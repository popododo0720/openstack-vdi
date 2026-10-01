# Run elevated on the separate Windows endpoint, after installing RustDesk.
# This script stores connection preferences only, never account passwords.
param(
    [Parameter(Mandatory = $true)][string]$PackagePath,
    [Parameter(Mandatory = $true)][string]$PackageSha256,
    [Parameter(Mandatory = $true)][string]$CaPath,
    [Parameter(Mandatory = $true)][string]$AuthUrl,
    [Parameter(Mandatory = $true)][string]$Username,
    [Parameter(Mandatory = $true)][string]$ProjectName,
    [Parameter(Mandatory = $true)][string]$ProjectId,
    [Parameter(Mandatory = $true)][string]$DesktopId,
    [Parameter(Mandatory = $true)][string]$PeerId,
    [string]$UserDomain = 'Default',
    [string]$ProjectDomain = 'Default',
    [string]$ProfileDirectory = (Join-Path $env:LOCALAPPDATA 'OpenStackVDI')
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
if ((Get-FileHash $PackagePath -Algorithm SHA256).Hash -ne $PackageSha256) {
    throw 'Launcher package checksum mismatch.'
}
$rustdesk = Join-Path $env:ProgramFiles 'RustDesk\rustdesk.exe'
if (-not (Test-Path $rustdesk)) { throw 'Install and configure RustDesk first.' }
$installDirectory = Join-Path $env:ProgramFiles 'OpenStackVDI'
New-Item -ItemType Directory -Force $installDirectory | Out-Null
Expand-Archive -LiteralPath $PackagePath -DestinationPath $installDirectory -Force
$launcher = Join-Path $installDirectory 'OpenStackVDI.exe'
if (-not (Test-Path $launcher)) { throw 'The package does not contain OpenStackVDI.exe.' }
$ca = Join-Path $installDirectory 'openstack-ca.pem'
Copy-Item -LiteralPath $CaPath -Destination $ca -Force

$identityUrl = $AuthUrl.Trim().TrimEnd('/')
if (([Uri]$identityUrl).AbsolutePath -eq '/') { $identityUrl += '/v3' }
$scopeText = "$identityUrl`n$ProjectId`n$UserDomain`n$Username"
$sha = [Security.Cryptography.SHA256]::Create()
try {
    $scope = ([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($scopeText)))).Replace('-', '').ToLowerInvariant()
} finally { $sha.Dispose() }
New-Item -ItemType Directory -Force $ProfileDirectory | Out-Null
$settingsFile = Join-Path $ProfileDirectory 'settings.json'
if (Test-Path $settingsFile) {
    throw 'Existing launcher preferences found. Back them up and remove them before provisioning.'
}
$settings = @{
    profile = @{
        auth_url = $identityUrl; username = $Username; project_name = $ProjectName
        user_domain = $UserDomain; project_domain = $ProjectDomain
        region_name = ''; ca_file = $ca; interface = 'public'
    }
    rustdesk_path = $rustdesk
    peers = @{ $scope = @{ $DesktopId = $PeerId } }
}
# Python reads plain UTF-8; Windows PowerShell's -Encoding UTF8 adds a BOM.
[IO.File]::WriteAllText($settingsFile, ($settings | ConvertTo-Json -Depth 5), (New-Object Text.UTF8Encoding($false)))
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut((Join-Path $env:PUBLIC 'Desktop\OpenStack VDI.lnk'))
$shortcut.TargetPath = $launcher
$shortcut.WorkingDirectory = $installDirectory
$shortcut.Description = 'OpenStack VDI native desktop launcher'
$shortcut.Save()
@{ launcher = $launcher; settings = $settingsFile; shortcut = 'OpenStack VDI' } | ConvertTo-Json -Compress
