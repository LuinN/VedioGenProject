# Wan Local Service API Contract

## Purpose

本文件是当前 WSL 服务端主线的协议文档。
截至 `2026-05-03`，服务端已经切到单模型主线：

- `Wan2.2 I2V-A14B`
- `ComfyUI` 原生低显存工作流
- 单模型、单能力、单分辨率集合

这意味着客户端不应再把服务端当成：

- `t2v` 服务
- `TI2V-5B` 多模式服务
- 依赖 `/api/capabilities` 的多 profile 服务

## Base URL

- 默认地址：`http://127.0.0.1:8000`
- 时间格式：UTC ISO8601
- `task_id`：UUID 字符串

## Supported Capability

当前只支持：

- `mode=i2v`
- `size=832*480`
- `size=480*832`

当前不支持：

- `mode=t2v`
- `/api/capabilities`
- 多模型切换
- 720p

服务内部固定后端：

- `backend="comfyui_native"`

## Status Enum

- `pending`
- `running`
- `succeeded`
- `failed`

## Health Check

`GET /healthz` 现在包含后端 readiness。

语义：

- `ok=true`
  - 只表示 FastAPI 存活
- `backend_ready=true`
  - 才表示 ComfyUI 后端可接受真实任务
- `model_ready=true`
  - 才表示 14B 模型文件齐全

示例：

```json
{
  "ok": true,
  "service": "wan-local-service",
  "backend": "comfyui_native",
  "backend_ready": true,
  "model_ready": true,
  "backend_reason": null
}
```

## Create Task

### `POST /api/tasks`

当前只接受 `multipart/form-data`。

必填字段：

- `mode=i2v`
- `prompt=<text>`
- `size=832*480` 或 `480*832`
- `image=@./frame.png`

示例：

```bash
curl --fail http://127.0.0.1:8000/api/tasks \
  -F mode=i2v \
  -F prompt='A fox looking at the camera, cinematic motion, smooth movement' \
  -F size='832*480' \
  -F image=@./frame.png
```

成功响应示例：

```json
{
  "task_id": "123e4567-e89b-12d3-a456-426614174000",
  "mode": "i2v",
  "status": "pending",
  "prompt": "A fox looking at the camera, cinematic motion, smooth movement",
  "size": "832*480",
  "output_path": null,
  "input_image_path": "/abs/path/outputs/123e4567-e89b-12d3-a456-426614174000/input_image.png",
  "error_message": null,
  "backend": "comfyui_native",
  "backend_prompt_id": null,
  "failure_code": null,
  "log_path": "/abs/path/logs/123e4567-e89b-12d3-a456-426614174000.log",
  "create_time": "2026-05-03T12:00:00+00:00",
  "update_time": "2026-05-03T12:00:00+00:00"
}
```

## Task Detail

### `GET /api/tasks/{task_id}`

运行中示例：

```json
{
  "task_id": "123e4567-e89b-12d3-a456-426614174000",
  "mode": "i2v",
  "status": "running",
  "prompt": "A fox looking at the camera, cinematic motion, smooth movement",
  "size": "832*480",
  "output_path": null,
  "input_image_path": "/abs/path/outputs/123e4567-e89b-12d3-a456-426614174000/input_image.png",
  "error_message": null,
  "backend": "comfyui_native",
  "backend_prompt_id": "prompt-1",
  "failure_code": null,
  "log_path": "/abs/path/logs/123e4567-e89b-12d3-a456-426614174000.log",
  "create_time": "2026-05-03T12:00:00+00:00",
  "update_time": "2026-05-03T12:00:12+00:00",
  "output_exists": false,
  "input_image_exists": true,
  "status_message": "sampling",
  "progress_current": 3,
  "progress_total": 20,
  "progress_percent": 15,
  "download_url": null
}
```

## Progress Endpoint

### `GET /api/tasks/{task_id}/progress`

示例：

```json
{
  "task_id": "123e4567-e89b-12d3-a456-426614174000",
  "status": "running",
  "update_time": "2026-05-03T12:00:15+00:00",
  "output_exists": false,
  "error_message": null,
  "backend": "comfyui_native",
  "backend_prompt_id": "prompt-1",
  "failure_code": null,
  "status_message": "sampling",
  "progress_current": 3,
  "progress_total": 20,
  "progress_percent": 15,
  "download_url": null
}
```

服务端当前阶段文案固定为：

- `uploading image`
- `queued`
- `sampling`
- `saving video`
- `finished`

## Result List

### `GET /api/tasks`

返回任务列表，字段与任务详情公共部分保持一致。

### `GET /api/results`

只列出 `succeeded` 任务，仍保留：

- `task_id`
- `output_path`
- `create_time`
- `output_exists`
- `download_url`

### `GET /api/results/{task_id}/file`

成功时返回 `video/mp4`。

## Delete Task

### `DELETE /api/tasks/{task_id}`

当前允许删除：

- `pending`
- `succeeded`
- `failed`

当前拒绝删除：

- `running`

## Stable Error Format

所有 API 错误统一返回：

```json
{
  "error": {
    "code": "<stable_code>",
    "message": "<human_message>"
  }
}
```

当前主要稳定错误码：

- `unsupported_mode`
- `invalid_size`
- `image_required`
- `image_not_supported`
- `image_too_large`
- `image_save_failed`
- `validation_error`
- `task_not_found`
- `task_not_deletable`
- `task_delete_failed`
- `result_not_ready`
- `result_file_missing`
- `service_not_ready`

任务异步失败不会把任务详情接口变成 `500`。
异步失败通过这些字段表达：

- `status="failed"`
- `error_message`
- `failure_code`

## Failure Code

任务级 `failure_code` 当前固定为：

- `backend_unavailable`
- `backend_upload_failed`
- `backend_validation_error`
- `backend_timeout`
- `backend_oom`
- `backend_execution_error`
- `backend_output_missing`

## Restart Recovery

服务启动时仍会扫描遗留 `pending` / `running` 任务并做恢复：

- `pending`
  - 若 `outputs/<task_id>/result.mp4` 已存在，则恢复为 `succeeded`
  - 否则恢复为 `failed`，`error_message="service restarted before task execution"`
- `running`
  - 若 `outputs/<task_id>/result.mp4` 已存在，则恢复为 `succeeded`
  - 否则恢复为 `failed`，`error_message="service restarted while task was running"`

## Integration Note

截至这轮服务端收口，Windows 客户端如果仍然：

- 请求 `/api/capabilities`
- 提交 `mode=t2v`
- 把服务端当成多 profile 服务

都会与当前服务端契约不一致。
这属于下一轮 Win/WSL 联调清理项，不影响本轮服务端单模型收口实现。
