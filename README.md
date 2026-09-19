# Remote ComfyUI

这是一个 Windows 主机上的 ComfyUI 局域网网关。手机端只看到两个固定能力：Qwen 图片编辑和 MiniMax 参考图生视频；工作流 JSON、节点参数和本机绝对路径不会暴露给手机。

## 运行边界

| 服务 | 地址 | 用途 |
| --- | --- | --- |
| ComfyUI | `127.0.0.1:8188` | 仅 Gateway 的本机上游，不开放防火墙 |
| Gateway | `0.0.0.0:3000` | 手机配对、任务、产物和白名单图库 API |
| Windows 管理页 | `127.0.0.1:3001` | 本机浏览器管理目录、配对设备和服务 |

Gateway 默认不会启动 ComfyUI。请先启动 ComfyUI portable，并确认 `http://127.0.0.1:8188/system_stats` 可访问。

## 环境准备

- Windows 10/11
- Python 3.11，且已安装 `server/pyproject.toml` 的运行依赖
- Node.js 20 或更高版本、npm
- 已启动的 ComfyUI portable，默认目录为 `D:\AI\ComfyUI_windows_portable_nvidia\ComfyUI_windows_portable`
- 手机和电脑连接同一个专用网络

安装 Python 依赖：

```powershell
python -m pip install -e ".\server[test]"
```

构建 Windows 管理页：

```powershell
Push-Location .\apps\windows-admin
npm ci
npm run build
Pop-Location
```

## 启动服务

从任意当前目录执行，脚本都会根据自身位置解析项目根目录：

```powershell
& "C:\Users\ALmerb\Desktop\MyProgram\RemoteComfyui\scripts\start-server.ps1"
& "C:\Users\ALmerb\Desktop\MyProgram\RemoteComfyui\scripts\start-admin.ps1"
```

也可以从项目根目录执行：

```powershell
.\scripts\start-server.ps1
.\scripts\start-admin.ps1
```

Python 不在 PATH 时指定完整路径：

```powershell
.\scripts\start-server.ps1 -PythonExe "C:\Python311\python.exe"
```

覆盖数据目录、Gateway 端口或 ComfyUI 地址：

```powershell
.\scripts\start-server.ps1 `
  -DataDir "D:\RemoteComfyUI\data" `
  -ComfyUiUrl "http://127.0.0.1:8188" `
  -PublicPort 3000
```

如果使用自定义 `DataDir`，管理页也必须使用同一个目录：

```powershell
.\scripts\start-admin.ps1 -DataDir "D:\RemoteComfyUI\data"
```

`start-admin.ps1` 始终默认绑定 `127.0.0.1`，不能从手机或其他局域网设备访问。不要把 `ComfyUI` 的启动参数改成 `--listen 0.0.0.0`，也不要为 8188 创建防火墙入站规则。

浏览器打开：

```text
http://127.0.0.1:3001/admin
```

## 管理图片目录和配对

1. 打开管理页的“图片目录”，通过固定磁盘和目录树选择目录，或输入绝对路径后验证。
2. 保存后，Gateway 只读访问白名单目录；删除配置不会删除原始图片。
3. 在“设备/配对”区域生成 6 位、短时有效的一次性配对码。
4. 手机输入电脑局域网地址，例如 `http://192.168.1.20:3000`，再输入配对码。
5. 配对成功后只保存设备令牌；令牌可以从管理页撤销。

手机端支持：

- Qwen 图片编辑：1 到 3 张参考图
- MiniMax 视频：1 到 9 张参考图，以及符合工作流步长的分辨率和帧数
- 手机相册选择、电脑白名单图库选择、任务状态、图片/视频产物预览、保存和分享

## Android 模拟器调试

先确认设备：

```powershell
& "$env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe" devices
```

模拟器访问宿主机 Gateway 的推荐方式是端口反向代理：

```powershell
& "$env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe" reverse tcp:3000 tcp:3000
```

此时在模拟器配对页输入 `http://127.0.0.1:3000`。真实手机不使用 `adb reverse`，请输入电脑的局域网 IPv4 地址。

启动 Metro 和 Android 调试包：

```powershell
Push-Location .\apps\mobile
npm ci
npm test
npm run typecheck
npm run export
npm run android
Pop-Location
```

## 局域网防火墙

只允许 Windows 防火墙在“专用网络”放行 TCP 3000。不要放行 TCP 3001 或 8188。示例（需要管理员 PowerShell）：

```powershell
New-NetFirewallRule `
  -DisplayName "Remote ComfyUI Gateway (Private)" `
  -Direction Inbound -Action Allow -Protocol TCP -LocalPort 3000 `
  -Profile Private
```

如果网络被识别为“公用网络”，不要直接扩大规则范围；先把电脑和手机连接到可信的专用网络，或改用后续的 VPN/Tailscale 方案。

## 登录后自动启动

安装两个当前用户的登录启动任务（Gateway 和本机管理页）：

```powershell
.\scripts\install-autostart.ps1 -ProjectRoot (Get-Location).Path
```

自定义数据目录时，安装任务也传入同一个 `-DataDir`；卸载任务不依赖 Python 仍在 PATH 中。

卸载：

```powershell
.\scripts\install-autostart.ps1 -ProjectRoot (Get-Location).Path -Remove
```

自动启动脚本不会启动 ComfyUI；ComfyUI 必须由 portable 启动方式或已有的 Windows 任务单独管理。登录任务使用当前用户的 Python 和项目路径，迁移项目或 Python 后应先卸载再重新安装。

## 验证命令

```powershell
python -m pytest server/tests -q

Push-Location .\apps\windows-admin
npm test -- --run
npm run build
Pop-Location

Push-Location .\apps\mobile
npm test
npm run typecheck
npm run export
Pop-Location
```

真实 GPU 生成不属于自动化测试。联调时先使用较低的视频参数，确认 `/api/v1/health`、配对、任务状态和产物读取后，再提交正式任务；不要在无人值守脚本中自动提交生图或生视频任务。
