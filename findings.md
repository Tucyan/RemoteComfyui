# 调研记录

## 当前环境

- `RemoteComfyui` 当前为空目录。
- ComfyUI portable 根目录存在，包含 `ComfyUI`、`python_embeded`、`update` 等目录。
- 目标工作流未以目标显示名直接作为 JSON 文件名出现。

## 工作流定位与初步结构

- 两个文件均位于 `ComfyUI\user\default\workflows`：
  - `image_qwen_image_edit_2511_int8.json`，5 个顶层节点，其中核心节点是内嵌子图 `cdb2cf24-c432-439b-b5c8-5f69838580c9`。
  - `minimax_h3_ref2va_lightx2v_8step_v1.json`，25 个节点、27 条连线。
- 图像工作流顶层暴露一个 `LoadImage`，输出经核心子图生成后由 `SaveImageAdvanced` 保存；核心模型为 Qwen Image Edit 2511 INT8，并使用 4-step Lightning LoRA。
- 视频工作流使用 `MiniMaxH3ReferenceToVideo`，说明中明确支持最多 9 张参考图、3 个参考视频和 3 个参考音频。本项目只需保留图片入口。
- 当前视频工作流连接了 3 个 `LoadImage`，提示词来自 `PrimitiveStringMultiline`。
- 视频分辨率当前由 `ResolutionSelector` 产生，示例是竖屏 0.4MP；核心节点当前值显示为 1792x768，但实际输入需结合连线确认。
- 帧数由 `ComfyMathExpression` 根据秒数和 24fps 计算，并调整为模型要求的 `17n+5` 帧序列；最终 `CreateVideo` 使用 24fps，`SaveVideo` 输出 MP4。
- 本机 ComfyUI 0.30.0 正常响应 API，GPU 是 8GB RTX 4060 Laptop，启动参数含 `--lowvram`。

## 方案决策

- ComfyUI 保持仅监听 localhost；单独的 Gateway 监听局域网，避免暴露任意工作流执行能力。
- 推荐 Python 3.12 + FastAPI Gateway，RN 采用 Expo + TypeScript。
- UI 工作流 JSON 需另行导出 API Format；服务端只保存并修改固定模板。
- Qwen 使用 1/2/3 张参考图三个模板变体；MiniMax 根据 1–9 张图片动态构造输入。
- 视频由后端直接写入宽、高和合法帧数，无需保留 UI 侧的 ResolutionSelector 和数学节点。
- 指定目录使用白名单别名、数据库 image ID、分页和缩略图缓存，不向手机暴露真实路径。
- 任务必须持久化 ComfyUI prompt_id，以支持断线和服务重启后的状态恢复。
- Windows 管理端改为 FastAPI 提供的纯浏览器页面，不要求桌面外壳或打包。
- 管理 API 独立绑定 `127.0.0.1:3001`，不与局域网手机 API 共用监听入口。
- 文件夹选择由后端受限目录树与手动路径校验实现；目录配置支持原子更新、备份与热加载。
- 管理接口使用 loopback、Host/Origin、SameSite 会话和 CSRF 多层限制。

## 开发环境补充

- Android 模拟器 `emulator-5584` 在线，Android 17，1344×2992、密度 480。
- ADB 位于 `%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe`，未加入 PATH。
- 模拟器未发现 Expo Go 或 Remote ComfyUI 应用；需后续构建/安装调试包。
- 本机 Java 17 可用，Android SDK 包含 android-35、android-36、android-37.0，Gradle 缓存已存在。
- ComfyUI 后端代码中未发现通用的“前端工作流 JSON 转 API prompt”接口；目标模板需要在 ComfyUI 前端导出 API Format，或依据本机 `/object_info` 与连线手工构建并验证。

## MiniMax 运行报错调查

- 当前本机 `MiniMaxH3ReferenceToVideo` 的 `ref_images` 输入类型为 `COMFY_AUTOGROW_V3`，前缀 `ref_image_`，索引 0–8；原工作流节点的连接名形如 `ref_images.ref_image_0`。
- ComfyUI `_io.py` 以点号输入路径构造嵌套的 `ref_images` 字典传给 `execute()`；旧 Gateway 传顶层 `ref_image_1`，导致 `unexpected keyword argument`。
- 对应 ComfyUI 历史的 `status_str=error`、`completed=false`；旧 Gateway 只识别成功而继续将该任务标为 running，新的错误分支读取 `execution_error` 后转为 failed。
# 2026-09-19 功能优化发现

- 现有图库页面点击图片会从受保护的图库 API 下载，再上传为参考图资产，随后回到生成页。代码路径存在；需要增加端到端测试，避免仅凭 UI 推断可用。
- 当前 `app-debug.apk` 需 Metro；已另有内置 JS 的 `app-release.apk`。本轮改动后必须重建 release APK 才会体现在手机。
- 视频服务端限制宽高为 32 的倍数，最大 1920×1088；帧数限定 124～362 且满足 `17n+5`。UI 自定义长宽与滑块生成值都需服从这些约束。
- 产物路径位于数据目录 `artifacts` 下，数据库记录有 `storage_path`；删除必须验证路径仍在该目录内，再删除文件及记录，不可影响白名单图库或 ComfyUI 原始输出。

# 2026-09-25 参考图预览

- `Workspace` 从手机选择图片时保留本地 `asset.uri`，电脑图库导入时没有保存任何 URI，`ReferenceImageStrip` 因此显示占位符。
- 图库图片提供受 Bearer 鉴权保护的 `thumbnail_url` 与 `content_url`。生成页的电脑参考图缩略图与预览须保留 Authorization 头。
- `ZoomableImage` 已提供双指缩放和放大后单指拖动，可直接复用于参考图预览。
- `README.md` 要求源码更新后重建 release APK；`expo export` 只导出 JS bundle，不会更新已安装的 APK。
- 当前 ADB 设备列表为空，无法执行手机手势实测。
