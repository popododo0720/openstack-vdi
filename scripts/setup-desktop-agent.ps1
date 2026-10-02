# Run elevated. Enrollment JSON must arrive through an administrator-controlled channel.
param(
    [Parameter(Mandatory=$true)][string]$EnrollmentPath,
    [Parameter(Mandatory=$true)][string]$CaPath
)
$ErrorActionPreference = 'Stop'
$root = Join-Path $env:ProgramData 'OpenStackVDI'
New-Item -ItemType Directory -Force $root | Out-Null
& icacls.exe $root /inheritance:r /grant:r '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Could not protect agent enrollment.' }
$cfg = Get-Content -LiteralPath $EnrollmentPath -Raw | ConvertFrom-Json
if (([Uri]$cfg.broker_url).Scheme -ne 'https' -or -not $cfg.token -or -not $cfg.vm_id) { throw 'Invalid enrollment.' }
Import-Certificate -FilePath $CaPath -CertStoreLocation Cert:\LocalMachine\Root | Out-Null
Copy-Item -LiteralPath $EnrollmentPath -Destination (Join-Path $root 'agent.json') -Force
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'windows-desktop-agent.ps1') -Destination $root -Force
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument ('-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + (Join-Path $root 'windows-desktop-agent.ps1') + '"')
$principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -MultipleInstances IgnoreNew -StartWhenAvailable
Stop-ScheduledTask -TaskName 'OpenStackVDI-DesktopAgent' -ErrorAction SilentlyContinue
Register-ScheduledTask -TaskName 'OpenStackVDI-DesktopAgent' -Action $action -Principal $principal -Trigger (New-ScheduledTaskTrigger -AtStartup) -Settings $settings -Force | Out-Null
Start-ScheduledTask -TaskName 'OpenStackVDI-DesktopAgent'
Set-Service RustDesk -StartupType Automatic
& sc.exe failure RustDesk reset= 86400 actions= restart/5000/restart/15000/restart/30000 | Out-Null
Write-Output 'Desktop readiness agent installed.'
