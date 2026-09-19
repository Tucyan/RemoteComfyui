[CmdletBinding()]
param(
    [string]$ProjectRoot = "",
    [string]$PythonExe = "",
    [string]$ComfyUiUrl = "http://127.0.0.1:8188",
    [string]$PublicHost = "0.0.0.0",
    [int]$PublicPort = 3000,
    [string]$DataDir = "",
    [switch]$Reload
)

$ErrorActionPreference = "Stop"

if ($PublicPort -lt 1 -or $PublicPort -gt 65535) {
    throw "PublicPort 必须在 1 到 65535 之间。"
}

try {
    $comfyUri = [Uri]$ComfyUiUrl
    $parsedIp = $null
    $isIp = [System.Net.IPAddress]::TryParse($comfyUri.Host, [ref]$parsedIp)
    if (-not $comfyUri.IsAbsoluteUri -or $comfyUri.Scheme -notin @("http", "https")) {
        throw "ComfyUiUrl 必须是 HTTP(S) 地址。"
    }
    if (($isIp -and -not [System.Net.IPAddress]::IsLoopback($parsedIp)) -or (-not $isIp -and $comfyUri.Host -ne "localhost")) {
        throw "ComfyUiUrl 必须指向 loopback 地址。"
    }
} catch {
    throw "无效的 ComfyUiUrl：$ComfyUiUrl。$($_.Exception.Message)"
}

if ([string]::IsNullOrWhiteSpace($ProjectRoot)) {
    $ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
} else {
    $ProjectRoot = (Resolve-Path $ProjectRoot).Path
}

if ([string]::IsNullOrWhiteSpace($PythonExe)) {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonCommand) {
        throw "找不到 Python。请使用 -PythonExe 指定 Python 3.11 的完整路径。"
    }
    $PythonExe = $pythonCommand.Source
} else {
    $PythonExe = (Resolve-Path $PythonExe).Path
}

if ([string]::IsNullOrWhiteSpace($DataDir)) {
    $DataDir = Join-Path $ProjectRoot "data"
} elseif (-not [System.IO.Path]::IsPathRooted($DataDir)) {
    $DataDir = Join-Path $ProjectRoot $DataDir
}
$DataDir = [System.IO.Path]::GetFullPath($DataDir)
New-Item -ItemType Directory -Force -Path $DataDir | Out-Null

$env:REMOTE_COMFYUI_COMFYUI_URL = $ComfyUiUrl.TrimEnd('/')
$env:REMOTE_COMFYUI_PUBLIC_HOST = $PublicHost
$env:REMOTE_COMFYUI_PUBLIC_PORT = [string]$PublicPort
$env:REMOTE_COMFYUI_DATA_DIR = $DataDir

Set-Location $ProjectRoot
$arguments = @(
    "-m", "uvicorn", "app.main:create_public_app",
    "--factory", "--app-dir", "server",
    "--host", $PublicHost, "--port", [string]$PublicPort
)
if ($Reload) {
    # Reload is intentionally opt-in for stable Windows operation.
    $arguments += "--reload"
}

Write-Host "Remote ComfyUI Gateway: http://${PublicHost}:${PublicPort}"
Write-Host "ComfyUI upstream remains local-only: $($env:REMOTE_COMFYUI_COMFYUI_URL)"
Write-Host "Data directory: $DataDir"
Write-Host "Press Ctrl+C to stop the Gateway."
& $PythonExe @arguments
exit $LASTEXITCODE
