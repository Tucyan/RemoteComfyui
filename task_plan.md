# Remote ComfyUI 方案规划

## 目标

为本机 ComfyUI 设计一套局域网内可通过 React Native 手机端使用的精简系统，只暴露一个生图工作流和一个生视频工作流，并支持动态多参考图、视频分辨率/帧数、产物预览保存、指定目录图片浏览。

## 阶段

- [x] 确认项目目录与 ComfyUI 安装位置
- [x] 定位并分析两个目标工作流
- [x] 核对 ComfyUI API 与本机节点约束
- [x] 设计系统架构、接口、数据模型与安全边界
- [x] 编写可执行的分阶段实施方案
- [x] 复核方案完整性并交付
- [x] 补充 Windows 本地浏览器管理页方案
- [x] Task 1：仓库与 Gateway 基础
- [x] Task 2：目录配置与 Windows 管理 API
- [x] Task 3：Windows 浏览器管理页
- [x] Task 4：固定工作流与 ComfyUI 客户端
- [x] Task 5：任务、配对、产物与手机 API
- [x] Task 6：Expo React Native 客户端
- [x] Task 7：Windows 启动与端到端验收
- [ ] 最终规格和代码质量审查

## 2026-09-19 功能优化

- [x] 核对现有产物、图库、视频参数能力并确定边界
- [x] 服务端产物物理删除及安全测试
- [x] 手机端产物图片缩放、视频预览、删除操作
- [x] 独立提示词、运行时长与视频尺寸/帧数交互
- [~] 验证图库参考图路径及完整回归，重建测试 APK（模拟器安装画面待验）

## 已知约束

- ComfyUI: `D:\AI\ComfyUI_windows_portable_nvidia\ComfyUI_windows_portable`
- 当前监听: `http://127.0.0.1:8188/`
- 图像工作流: `image_qwen_image_edit_2511_int8`
- 视频工作流: `minimax_h3_ref2va_lightx2v_8step_v1`
- 手机端使用 React Native
- 手机端仅提供提示词、动态多参考图，以及视频分辨率和帧数等必要参数
- 可查看、保存生成产物，并浏览若干白名单目录中的图片
- Windows 本机提供浏览器管理页，用图形界面维护目录、设备和服务

## 错误记录

| 错误 | 尝试 | 处理 |
|---|---:|---|
| 当前目录不是 Git 仓库 | 1 | 仅作为新项目目录使用，不依赖 Git 历史 |
| 按目标名称未找到 JSON | 1 | 扩大到 ComfyUI 用户目录、数据库和 JSON 内容检索 |
| 优化版 APK 安装时 ADB 没有在线设备 | 1 | 尝试启动本机 AVD；模拟器报告实例过多且未进入 ADB，保留 APK，等待用户启动模拟器后复测 |
