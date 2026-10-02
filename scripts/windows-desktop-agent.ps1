# Runs as SYSTEM from a scheduled task. No user passwords are collected.
param([string]$ConfigPath = "$env:ProgramData\OpenStackVDI\agent.json")
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$config = Get-Content -LiteralPath $ConfigPath -Raw | ConvertFrom-Json
$bootId = (Get-CimInstance Win32_OperatingSystem).LastBootUpTime.ToUniversalTime().ToString('o')
$healthyChecks = 0
while ($true) {
    try {
        $service = Get-Service RustDesk -ErrorAction SilentlyContinue
        $ready = $false
        if ($service -and $service.Status -eq 'Running') {
            $tcp = New-Object Net.Sockets.TcpClient
            try {
                $pending = $tcp.BeginConnect($config.id_server, 21116, $null, $null)
                if ($pending.AsyncWaitHandle.WaitOne(2000)) {
                    $tcp.EndConnect($pending)
                    $ready = $tcp.Connected
                }
            } catch { $ready = $false } finally { $tcp.Dispose() }
        }
        if ($ready) { $healthyChecks++ } else { $healthyChecks = 0 }
        $body = @{ boot_id = $bootId; ready = ($healthyChecks -ge 3) } | ConvertTo-Json -Compress
        Invoke-RestMethod -Method Post -TimeoutSec 8 -Uri "$($config.broker_url)/agent/$($config.vm_id)/heartbeat" `
            -Headers @{ Authorization = "Bearer $($config.token)" } -ContentType 'application/json' -Body $body | Out-Null
    } catch {
        # Retry without writing tokens, raw exceptions or response bodies to logs.
    }
    Start-Sleep -Seconds 5
}
