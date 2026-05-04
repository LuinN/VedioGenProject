# STATUS

## 当前状态

截至 `2026-05-05`，项目两侧的真实状态是：

- WSL 服务端已经在 `RTX 3090 24GB` 上完成一次真实 `Wan2.2 I2V-A14B` 出片闭环
- Windows Qt 客户端已切到当前单模型 `i2v` 契约，并在 Windows 原生 Qt/MinGW 工具链下完成构建与 release 打包
- 当前整条最终用户链路的剩余重点，不再是“服务端能不能跑”或“客户端契约是否同步”，而是“用当前客户端重新完成一次真实 Win/WSL 端到端联调”

服务端当前对外语义：

- `POST /api/tasks`
  - 只接受 `multipart/form-data`
  - 只支持 `mode=i2v`
  - 只允许 `832*480` / `480*832`
- `GET /healthz`
  - 返回 `backend`
  - 返回 `backend_ready`
  - 返回 `model_ready`
  - 返回 `backend_reason`
- 任务对象
  - 包含 `backend`
  - 包含 `backend_prompt_id`
  - 包含 `failure_code`
- 不再实现 `/api/capabilities`

## 已完成

### WSL 服务端

- `WanRunner` 主路径已被 `ComfyUiNativeBackend` 替代
- `TaskRunner` 已切成单一 ComfyUI backend 执行路径
- ComfyUI 工作流模板已入库：
  - `code/server/wan_local_service/workflows/wan22_i2v_a14b_lowvram_template.json`
- ComfyUI 环境脚本已补齐：
  - `scripts/setup_comfyui.sh`
  - `scripts/run_comfyui.sh`
  - `scripts/setup_wan22.sh`
  - `scripts/run_service.sh`
  - `scripts/run_sample_i2v.sh`
- `check_env.sh` / `app.env_report` 已修正为读取真实项目 venv 解释器路径
- 修复了 ComfyUI 工作流到 API prompt 的 `KSamplerAdvanced` 参数映射
- 修复了 `run_sample_i2v.sh` 的进度字段解析
- 4 个 14B 必需模型文件已下载完成
- 成功真实出片任务：
  - `task_id=d69cc58c-df85-4fcd-86f3-849072c0e8ec`
  - `backend_prompt_id=14d77c4b-f272-4ca2-8eff-9715b48d9a0a`
  - 输出文件：
    - `code/server/wan_local_service/outputs/d69cc58c-df85-4fcd-86f3-849072c0e8ec/result.mp4`
- 服务端自动化测试当前为：
  - `20 passed`

### Windows Qt 客户端

- Qt6 + CMake + Widgets 客户端工程已创建并可在 Windows 原生环境构建
- `ApiClient` 已实现：
  - `GET /healthz`
  - `POST /api/tasks`
  - `GET /api/tasks/{task_id}`
  - `GET /api/tasks`
  - `DELETE /api/tasks/{task_id}`
  - `GET /api/results`
  - `GET /api/results/{task_id}/file`
- 主窗口已具备：
  - 左侧任务列表
  - 中间 Wan Chat 区
  - 输入框 / 发送按钮
  - Configuration / Videos / Diagnostics 非模态弹窗
- 已支持：
  - 本地输入图片附件
  - 任务轮询与阶段/进度展示
  - Wan Chat 中按 `task_id` 复用的进度卡片
  - 下载结果视频到 Windows 本地目录
  - Videos 列表、本地索引、默认播放器打开
  - 结果缩略图生成与缓存
  - 任务删除与本地缓存清理
- 已按服务端最终契约收敛：
  - 不再请求 `/api/capabilities`
  - 不再提交 `mode=t2v`
  - 创建任务只走 `multipart/form-data` 的 `mode=i2v`
  - 发送前强制要求本地输入图片
  - 尺寸固定为 `832*480` / `480*832`
  - `GET /healthz` 解析 `backend_ready` / `model_ready` / `backend_reason`
  - 任务对象解析 `backend` / `backend_prompt_id` / `failure_code`
- 客户端原生构建、release 打包已跑通过

### 文档

- 服务 README 已切到 14B 主线
- 服务端 API 契约已切到单模型 `i2v`
- 服务端自测报告已记录本轮真实成功出片
- Win/WSL 集成文档已更新为“服务端真实跑通，客户端仍需同步最终契约”

## 当前真实环境快照

服务端成功验收时的真实事实：

- `GET /healthz`：
  - `ok=true`
  - `backend="comfyui_native"`
  - `backend_ready=true`
  - `model_ready=true`
- 非沙箱 WSL 环境下 `bash scripts/check_env.sh` 为：
  - `service_ready=yes`
  - `backend_ready=yes`
  - `model_ready=yes`
- `nvidia-smi` 可见：
  - `RTX 3090`
  - 运行时显存占用约 `16079 MiB / 24576 MiB`
- 真实视频参数：
  - `832x480`
  - `49` 帧
  - `16fps`
  - 时长约 `3.0625s`
- ComfyUI 真实执行耗时：
  - `Prompt executed in 00:10:48`

## 当前未完成

- Windows 客户端已完成单模型 `i2v` 契约适配，但还没有用当前服务端重新完成一次真实端到端联调
- `AGENTS.md` 仍保留早期 `TI2V-5B / t2v` 的 MVP 文字，与当前服务端主线不一致
- 重复启动时仍可能看到 ComfyUI `database lock` / `port already in use` 警告，需要后续收敛后台进程管理

## 最近一次重要进展

`2026-05-05`

- Windows Qt 客户端已合入服务端最新生成业务适配：
  - 移除 `/api/capabilities` 客户端调用链
  - 移除 JSON `t2v` 创建任务路径
  - 固定 UI 为 `Wan2.2 I2V-A14B / ComfyUI`
  - smoke 创建任务现在必须提供 `--smoke-image`
  - 失败诊断补充 `failure_code` 和 `backend_prompt_id`
- Windows 原生构建验证通过：
  - Ninja 编译对象文件通过
  - `qt_wan_chat.exe` 链接通过
  - `windeployqt` release 打包通过

`2026-05-04`

- Windows Qt 客户端已合入：
  - Wan Chat 进度卡片与 ETA 展示
  - 任务删除协议
  - 构建后自动 release 打包
  - 缩略图生成链路修复
- WSL 服务端已合入并真实验证：
  - `ComfyUI + Wan2.2 I2V-A14B`
  - 第一条真实 `result.mp4`
  - `KSamplerAdvanced` 工作流映射修复
  - 样例脚本进度解析修复
