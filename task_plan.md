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
- [~] Task 1：仓库与 Gateway 基础
- [ ] Task 2：目录配置与 Windows 管理 API
- [ ] Task 3：Windows 浏览器管理页
- [ ] Task 4：固定工作流与 ComfyUI 客户端
- [ ] Task 5：任务、配对、产物与手机 API
- [ ] Task 6：Expo React Native 客户端
- [ ] Task 7：Windows 启动与端到端验收
- [ ] 最终规格和代码质量审查

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
