$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Error "uv가 필요합니다. https://docs.astral.sh/uv/getting-started/installation/ 에서 설치하세요."
}
uv sync --frozen
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
uv run openstack-vdi @args
exit $LASTEXITCODE

