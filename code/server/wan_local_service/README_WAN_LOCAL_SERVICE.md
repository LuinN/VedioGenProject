# README_WAN_LOCAL_SERVICE

## 概要

`wan_local_service` 是运行在 WSL / Linux 上的本地 FastAPI 服务。当前主线已经切到：

- 单模型服务：`Wan2.2 I2V-A14B`
- 低显存实现：`ComfyUI` 原生工作流
- 当前只支持：`mode=i2v`
- 当前固定分辨率：`832*480`、`480*832`
- 当前固定长度：`49` 帧

服务端不再以官方 `generate.py` 的 `TI2V-5B` 作为主路径，也不再提供 `/api/capabilities` 的多 profile 协议。

## 当前接口

- `GET /healthz`
- `POST /api/tasks`
- `GET /api/tasks/{task_id}`
- `GET /api/tasks/{task_id}/progress`
- `GET /api/tasks`
- `GET /api/results`
- `GET /api/results/{task_id}/file`
- `DELETE /api/tasks/{task_id}`

状态枚举固定为：

- `pending`
- `running`
- `succeeded`
- `failed`

## 请求语义

`POST /api/tasks` 现在正式收口为 `multipart/form-data` 的 `i2v` 创建接口。

必填字段：

- `mode=i2v`
- `prompt`
- `size`
- `image`

当前只允许：

- `size=832*480`
- `size=480*832`

如果请求是 `application/json`，服务会返回 `validation_error`。
如果 `mode=t2v`，服务会返回 `unsupported_mode`。

上传图片规则：

- 支持扩展名：`png`、`jpg`、`jpeg`、`webp`
- 默认大小上限：`20 MiB`
- 服务会把图片保存到 `outputs/<task_id>/input_image.<ext>`

## `GET /healthz`

`ok=true` 只表示 FastAPI 进程存活。
能否真实提交 14B 任务，要看：

- `backend="comfyui_native"`
- `backend_ready`
- `model_ready`
- `backend_reason`

示例：

```json
{
  "ok": true,
  "service": "wan-local-service",
  "backend": "comfyui_native",
  "backend_ready": false,
  "model_ready": false,
  "backend_reason": "missing model file: /abs/path/to/file"
}
```

## 目录与运行时

默认目录：

- 服务根目录：`code/server/wan_local_service`
- FastAPI venv：`.venv`
- ComfyUI venv：`.comfyui-venv`
- ComfyUI 源码：`third_party/ComfyUI`
- 工作流模板：`workflows/wan22_i2v_a14b_lowvram_template.json`
- SQLite：`storage/tasks.db`
- 服务日志：`logs/service.log`
- ComfyUI 日志：`logs/comfyui.log`
- 服务 PID：`storage/service.pid`
- ComfyUI PID：`storage/comfyui.pid`
- 任务结果：`outputs/<task_id>/result.mp4`

## 14B 模型文件

服务要求 ComfyUI 目录下至少存在这些文件：

- `models/diffusion_models/wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors`
- `models/diffusion_models/wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors`
- `models/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors`
- `models/vae/wan_2.1_vae.safetensors`

这些文件不纳入 Git 版本控制。

## 环境准备

先检查当前工作区是否已经具备 14B 运行前提：

```bash
cd code/server/wan_local_service
bash scripts/check_env.sh
```

当前报告会明确输出：

- `service_ready`
- `backend_ready`
- `model_ready`

首次准备环境：

```bash
cd code/server/wan_local_service
bash scripts/setup_wan22.sh
```

这个入口会做两件事：

- 准备 FastAPI 服务自己的 `.venv`
- 准备 ComfyUI 的 `.comfyui-venv`、源码和 14B 模型文件

模型下载默认启用，默认下载源是 `Hugging Face`。
如需切到 `ModelScope`，可设置：

```bash
WAN_COMFYUI_MODEL_PROVIDER=modelscope
```

如需临时关闭自动下载：

```bash
WAN_COMFYUI_AUTO_DOWNLOAD_MODELS=0
```

## 启动服务

后台启动：

```bash
cd code/server/wan_local_service
bash scripts/run_service.sh start
bash scripts/run_service.sh status
```

前台启动：

```bash
cd code/server/wan_local_service
bash scripts/run_service.sh foreground
```

停止服务：

```bash
cd code/server/wan_local_service
bash scripts/run_service.sh stop
```

`run_service.sh` 会先确保 ComfyUI 存活，再启动 FastAPI。
ComfyUI 也可以单独管理：

```bash
cd code/server/wan_local_service
bash scripts/run_comfyui.sh start
bash scripts/run_comfyui.sh status
bash scripts/run_comfyui.sh stop
```

## 样例任务

准备一张输入图后，可以直接跑服务端闭环脚本：

```bash
cd code/server/wan_local_service
WAN_SAMPLE_IMAGE=/abs/path/frame.png bash scripts/run_sample_i2v.sh
```

脚本会：

- 请求 `/healthz`
- 提交一条 `i2v` 任务
- 轮询任务详情直到 `succeeded` 或 `failed`
- 打印 `task_id`
- 打印 `backend_prompt_id`
- 打印 `status_message`
- 打印最终 `output_path` 或 `error_message`

## 输出语义

任务响应新增并固定这些字段：

- `backend`
- `backend_prompt_id`
- `failure_code`

`failure_code` 当前只收口为：

- `backend_unavailable`
- `backend_upload_failed`
- `backend_validation_error`
- `backend_timeout`
- `backend_oom`
- `backend_execution_error`
- `backend_output_missing`

## 说明

当前仓库里的 `AGENTS.md` 仍然保留了早期 `TI2V-5B` MVP 约束。
本目录下的实现、README、协议文档和状态文档已经按新的服务端产品目标切到 `ComfyUI + Wan2.2 I2V-A14B` 主线。是否同步清理客户端与协作文档，需要下一轮联调一起收口。
