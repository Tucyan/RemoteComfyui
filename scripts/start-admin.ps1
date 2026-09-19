[CmdletBinding()]
param(
    [string]$ProjectRoot = "",
    [string]$PythonExe = "",
    [string]$AdminHost = "127.0.0.1",
    [int]$AdminPort = 3001,
    [string]$DataDir = ""
)

$ErrorActionPreference = "Stop"

if ($AdminPort -lt 1 -or $AdminPort -gt 65535) {
    throw "AdminPort 必须在 1 到 65535 之间。"
}
if ($AdminHost -notin @("127.0.0.1", "localhost", "::1")) {
    throw "AdminHost 必须保持 loopback（127.0.0.1、localhost 或 ::1）。"
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

$StaticDir = [System.IO.Path]::GetFullPath((Join-Path $ProjectRoot "apps\windows-admin\dist"))

$env:REMOTE_COMFYUI_ADMIN_HOST = $AdminHost
$env:REMOTE_COMFYUI_ADMIN_PORT = [string]$AdminPort
$env:REMOTE_COMFYUI_DATA_DIR = $DataDir

Set-Location $ProjectRoot
$arguments = @(
    "-m", "uvicorn", "app.main:create_admin_app",
    "--factory", "--app-dir", "server",
    "--host", $AdminHost, "--port", [string]$AdminPort
)
if (Test-Path $StaticDir) {
    Write-Host "Admin UI assets: $StaticDir"
} else {
    Write-Warning "未找到管理页构建目录：$StaticDir。请先在 apps/windows-admin 执行 npm run build。"
}

Write-Host "Windows admin: http://${AdminHost}:${AdminPort}/admin"
Write-Host "This listener is loopback-only; it is not available from the LAN."
& $PythonExe @arguments
exit $LASTEXITCODE
