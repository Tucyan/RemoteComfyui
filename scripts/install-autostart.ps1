[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$ProjectRoot = "",
    [string]$PythonExe = "",
    [string]$TaskPrefix = "RemoteComfyUI",
    [switch]$Remove
)

$ErrorActionPreference = "Stop"

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

$serverScript = Join-Path $ProjectRoot "scripts\start-server.ps1"
$adminScript = Join-Path $ProjectRoot "scripts\start-admin.ps1"
foreach ($path in @($serverScript, $adminScript)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "启动脚本不存在：$path"
    }
}

$serverTask = "$TaskPrefix Gateway"
$adminTask = "$TaskPrefix Admin"
$powerShell = (Get-Command powershell.exe -ErrorAction Stop).Source
$common = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden"
$quote = [char]34
$serverArgs = "$common -File $quote$serverScript$quote -ProjectRoot $quote$ProjectRoot$quote -PythonExe $quote$PythonExe$quote"
$adminArgs = "$common -File $quote$adminScript$quote -ProjectRoot $quote$ProjectRoot$quote -PythonExe $quote$PythonExe$quote"

if ($Remove) {
    foreach ($task in @($serverTask, $adminTask)) {
        if ($PSCmdlet.ShouldProcess($task, "删除登录启动任务")) {
            Unregister-ScheduledTask -TaskName $task -Confirm:$false -ErrorAction SilentlyContinue
        }
    }
    Write-Host "已移除：$serverTask / $adminTask"
    exit 0
}

$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
foreach ($entry in @(
    @{ Name = $serverTask; Arguments = $serverArgs },
    @{ Name = $adminTask; Arguments = $adminArgs }
)) {
    if ($PSCmdlet.ShouldProcess($entry.Name, "安装登录启动任务")) {
        $action = New-ScheduledTaskAction -Execute $powerShell -Argument $entry.Arguments -WorkingDirectory $ProjectRoot
        Register-ScheduledTask -TaskName $entry.Name -Action $action -Trigger $trigger -Settings $settings -Description "Remote ComfyUI local gateway" -Force | Out-Null
    }
}

if ($WhatIfPreference) {
    Write-Host "WhatIf：未写入登录启动任务。"
} else {
    Write-Host "已安装登录启动任务：$serverTask / $adminTask"
    Write-Host "卸载：.\scripts\install-autostart.ps1 -ProjectRoot $quote$ProjectRoot$quote -Remove"
}
