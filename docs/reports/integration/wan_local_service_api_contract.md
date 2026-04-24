# Wan Local Service API Contract

## Purpose

本文件是 Windows Qt 客户端并行开发的主协议文档。  
客户端联调请以本文件为准；FastAPI `/docs` 和 `/openapi.json` 仅作为机器可读补充。

## Base URL

- 默认地址：`http://127.0.0.1:8000`
- 编码：`application/json; charset=utf-8`
- 时间格式：UTC ISO8601，例如 `2026-04-23T13:39:00+00:00`
- `task_id` 类型：UUID 字符串

## Supported Capability

- 支持 `mode=t2v` 和 `mode=i2v`
- 仅支持 `size=1280*704` 或 `size=704*1280`
- 服务内部固定调用官方 `Wan2.2/generate.py --task ti2v-5B`
- `mode=i2v` 时会额外带 `--image <input_image_path>`
- 生成成功后支持通过 HTTP 下载 `mp4` 结果文件
- 支持通过 `DELETE /api/tasks/{task_id}` 删除非运行中的任务和本地产物
- 支持通过轻量进度接口查询实时阶段和采样步数

## Status Enum

状态枚举在代码、协议文档、README、自测报告中保持一致：

- `pending`
- `running`
- `succeeded`
- `failed`

客户端轮询建议：

- 创建任务后，可每 1 到 2 秒轮询一次 `GET /api/tasks/{task_id}/progress`
- 需要完整任务详情时，再调用 `GET /api/tasks/{task_id}`
- 终态为 `succeeded` 或 `failed`

## Null Semantics

- `mode`
  - `t2v` / `i2v`
- `size`
  - `1280*704` / `704*1280`
- `output_path`
  - `pending` / `running` / `failed`: `null`
  - `succeeded`: 绝对路径字符串
- `input_image_path`
  - `t2v`: `null`
  - `i2v`: 保存到 `outputs/<task_id>/input_image.<ext>` 的绝对路径
- `input_image_exists`
  - 在 `GET /api/tasks/{task_id}` 中返回
  - `input_image_path` 指向的真实文件存在为 `true`
- `error_message`
  - `pending` / `running` / `succeeded`: `null`
  - `failed`: 非空字符串
  - 优先返回前置检查失败原因，或 `generate.py` 日志尾部提炼出的真实错误摘要，并附带退出码
- `log_path`
  - 任务创建成功后立即分配为绝对路径字符串
  - 即使日志文件还没真正写出，也先返回预留路径
- `output_exists`
  - 在 `GET /api/tasks/{task_id}`、`GET /api/tasks/{task_id}/progress` 与 `GET /api/results` 中返回
  - 真实文件存在为 `true`，否则为 `false`
- `status_message`
  - 在 `GET /api/tasks/{task_id}` 与 `GET /api/tasks/{task_id}/progress` 中返回
  - 可为 `null`
  - 典型值包括 `creating pipeline`、`loading checkpoints`、`sampling`、`saving video`、`finished`
- `progress_current` / `progress_total` / `progress_percent`
  - 在 `GET /api/tasks/{task_id}` 与 `GET /api/tasks/{task_id}/progress` 中返回
  - 可为 `null`
  - 采样阶段通常返回当前 step、总 step 和百分比
  - 成功完成时可返回 `progress_percent=100`
- `update_time`
  - 在实时进度写入时会刷新
  - `GET /api/tasks/{task_id}/progress` 中可用于判断进度是否仍在推进
- `download_url`
  - `GET /api/tasks/{task_id}`、`GET /api/tasks/{task_id}/progress` 与 `GET /api/results` 中返回
  - `pending` / `running` / `failed` / `output_exists=false`: `null`
  - `succeeded` 且结果文件存在：绝对 HTTP URL
  - 客户端应优先使用该 URL 下载视频到本地目录，而不是依赖 `\\wsl$` 路径访问

## Stable Error Format

所有 API 级错误响应统一为：

```json
{
  "error": {
    "code": "<stable_code>",
    "message": "<human_message>"
  }
}
```

稳定错误码与 HTTP 状态码固定映射如下：

| code | HTTP status | meaning |
| --- | --- | --- |
| `unsupported_mode` | `400 Bad Request` | 请求中的 `mode` 不是 `t2v` / `i2v` |
| `invalid_size` | `400 Bad Request` | 请求中的 `size` 不在白名单 |
| `image_required` | `400 Bad Request` | `mode=i2v` 但未上传 `image` |
| `image_not_supported` | `400 Bad Request` | 上传图片扩展名或 MIME type 不在白名单 |
| `image_too_large` | `413 Payload Too Large` | 上传图片超过大小限制 |
| `image_save_failed` | `500 Internal Server Error` | 服务端保存上传图片失败 |
| `validation_error` | `422 Unprocessable Entity` | 请求体缺字段、字段类型错误、空 prompt |
| `task_not_found` | `404 Not Found` | 查询了不存在的任务 ID |
| `task_not_deletable` | `409 Conflict` | 当前任务状态不允许删除，现阶段主要是 `running` |
| `task_delete_failed` | `500 Internal Server Error` | 删除任务本地文件或数据库记录时发生内部错误 |
| `result_not_ready` | `409 Conflict` | 任务尚未成功完成，当前没有可下载结果 |
| `result_file_missing` | `404 Not Found` | 任务已成功，但服务端结果文件不存在 |
| `service_not_ready` | `503 Service Unavailable` | 服务上下文未完成初始化 |
| `wan_execution_failed` | `500 Internal Server Error` | API 层意外内部错误 |

语义补充：

- 异步推理失败不会把 `GET /api/tasks/{task_id}` 变成 `500`
- 异步推理失败通过任务对象的 `status=failed` 和 `error_message` 表达

## Restart Recovery Semantics

服务启动时会扫描遗留 `pending` 与 `running` 任务。

- 遗留 `pending`
  - 若期望输出文件已存在：
    - `status = "succeeded"`
    - `output_path = <outputs/<task_id>/result.mp4>`
  - 否则：
    - `status = "failed"`
    - `error_message = "service restarted before task execution"`
- 遗留 `running`
  - 若期望输出文件已存在：
    - `status = "succeeded"`
    - `output_path = <outputs/<task_id>/result.mp4>`
  - 否则：
    - `status = "failed"`
    - `error_message = "service restarted while task was running"`

共同规则：

- `update_time` 刷新为服务启动时刻
- 若恢复为 `failed`，`output_path` 保持 `null`
- `log_path` 保留原值

## Endpoints

### `GET /healthz`

Success response:

```json
{
  "ok": true,
  "service": "wan-local-service"
}
```

### `POST /api/tasks`

支持两种请求方式：

- `application/json`
  - 仅兼容 `mode=t2v`
- `multipart/form-data`
  - 支持 `mode=t2v` 和 `mode=i2v`
  - `mode=i2v` 时必须包含 `image`

图片上传规则：

- 支持扩展名：`png` / `jpg` / `jpeg` / `webp`
- 会检查文件扩展名
- 会检查 MIME type，常见有效值包括 `image/png` / `image/jpeg` / `image/webp`
- 默认大小限制：`20971520` bytes，也就是 `20 MiB`
- `mode=t2v` 传 `image` 会返回 `validation_error`

JSON `t2v` request body:

```json
{
  "mode": "t2v",
  "prompt": "A cinematic cyberpunk street at night, slow camera push-in, rain reflections on the ground",
  "size": "1280*704"
}
```

Multipart `i2v` fields:

- `mode=i2v`
- `prompt=<text>`
- `size=1280*704`
- `image=@./frame.png`

Success response:

```json
{
  "task_id": "123e4567-e89b-12d3-a456-426614174000",
  "mode": "t2v",
  "status": "pending",
  "prompt": "A cinematic cyberpunk street at night, slow camera push-in, rain reflections on the ground",
  "size": "1280*704",
  "output_path": null,
  "input_image_path": null,
  "error_message": null,
  "log_path": "/mnt/d/projects/videogenproject/code/server/wan_local_service/logs/123e4567-e89b-12d3-a456-426614174000.log",
  "create_time": "2026-04-23T13:39:00+00:00",
  "update_time": "2026-04-23T13:39:00+00:00"
}
```

### `GET /api/tasks/{task_id}`

Running example:

```json
{
  "task_id": "123e4567-e89b-12d3-a456-426614174000",
  "mode": "i2v",
  "status": "running",
  "prompt": "A cinematic cyberpunk street at night, slow camera push-in, rain reflections on the ground",
  "size": "1280*704",
  "output_path": null,
  "input_image_path": "/mnt/d/projects/videogenproject/code/server/wan_local_service/outputs/123e4567-e89b-12d3-a456-426614174000/input_image.png",
  "error_message": null,
  "log_path": "/mnt/d/projects/videogenproject/code/server/wan_local_service/logs/123e4567-e89b-12d3-a456-426614174000.log",
  "create_time": "2026-04-23T13:39:00+00:00",
  "update_time": "2026-04-23T13:39:03+00:00",
  "output_exists": false,
  "input_image_exists": true,
  "status_message": "sampling",
  "progress_current": 9,
  "progress_total": 50,
  "progress_percent": 18,
  "download_url": null
}
```

### `GET /api/tasks/{task_id}/progress`

用途：

- 用更轻的响应体轮询实时进度
- 适合 Windows 客户端在任务运行期间高频刷新 UI

Running example:

```json
{
  "task_id": "123e4567-e89b-12d3-a456-426614174000",
  "status": "running",
  "update_time": "2026-04-23T13:39:21+00:00",
  "output_exists": false,
  "error_message": null,
  "status_message": "sampling",
  "progress_current": 21,
  "progress_total": 50,
  "progress_percent": 42,
  "download_url": null
}
```

### `DELETE /api/tasks/{task_id}`

用途：

- 删除指定任务
- 同时清理该任务的本地产物

当前删除规则：

- 允许删除：
  - `pending`
  - `succeeded`
  - `failed`
- 当前拒绝删除：
  - `running`

删除副作用：

- 删除 SQLite 中的任务记录
- 删除 `logs/<task_id>.log`
- 删除 `outputs/<task_id>/`
- 删除后：
  - `GET /api/tasks/{task_id}` 返回 `task_not_found`
  - 若该任务原本在 `GET /api/results` 中出现，会从结果列表中消失

Success response:

```json
{
  "task_id": "123e4567-e89b-12d3-a456-426614174000",
  "deleted": true
}
```

Succeeded example for `GET /api/tasks/{task_id}`:

```json
{
  "task_id": "123e4567-e89b-12d3-a456-426614174000",
  "status": "succeeded",
  "update_time": "2026-04-23T13:48:00+00:00",
  "output_exists": true,
  "error_message": null,
  "status_message": "finished",
  "progress_current": 50,
  "progress_total": 50,
  "progress_percent": 100,
  "download_url": "http://127.0.0.1:8000/api/results/123e4567-e89b-12d3-a456-426614174000/file"
}
```

Succeeded example:

```json
{
  "task_id": "123e4567-e89b-12d3-a456-426614174000",
  "mode": "i2v",
  "status": "succeeded",
  "prompt": "A cinematic cyberpunk street at night, slow camera push-in, rain reflections on the ground",
  "size": "1280*704",
  "output_path": "/mnt/d/projects/videogenproject/code/server/wan_local_service/outputs/123e4567-e89b-12d3-a456-426614174000/result.mp4",
  "input_image_path": "/mnt/d/projects/videogenproject/code/server/wan_local_service/outputs/123e4567-e89b-12d3-a456-426614174000/input_image.png",
  "error_message": null,
  "log_path": "/mnt/d/projects/videogenproject/code/server/wan_local_service/logs/123e4567-e89b-12d3-a456-426614174000.log",
  "create_time": "2026-04-23T13:39:00+00:00",
  "update_time": "2026-04-23T13:48:00+00:00",
  "output_exists": true,
  "input_image_exists": true,
  "status_message": "finished",
  "progress_current": 50,
  "progress_total": 50,
  "progress_percent": 100,
  "download_url": "http://127.0.0.1:8000/api/results/123e4567-e89b-12d3-a456-426614174000/file"
}
```

Failed example:

```json
{
  "task_id": "123e4567-e89b-12d3-a456-426614174000",
  "mode": "i2v",
  "status": "failed",
  "prompt": "A cinematic cyberpunk street at night, slow camera push-in, rain reflections on the ground",
  "size": "1280*704",
  "output_path": null,
  "input_image_path": "/mnt/d/projects/videogenproject/code/server/wan_local_service/outputs/123e4567-e89b-12d3-a456-426614174000/input_image.png",
  "error_message": "AssertionError (generate.py exit code 1)",
  "log_path": "/mnt/d/projects/videogenproject/code/server/wan_local_service/logs/123e4567-e89b-12d3-a456-426614174000.log",
  "create_time": "2026-04-23T13:39:00+00:00",
  "update_time": "2026-04-23T13:39:00+00:00",
  "output_exists": false,
  "input_image_exists": true,
  "status_message": null,
  "progress_current": null,
  "progress_total": null,
  "progress_percent": null,
  "download_url": null
}
```

### `GET /api/tasks`

Success response:

```json
{
  "items": [
    {
      "task_id": "123e4567-e89b-12d3-a456-426614174000",
      "mode": "i2v",
      "status": "failed",
      "prompt": "A cinematic cyberpunk street at night, slow camera push-in, rain reflections on the ground",
      "size": "1280*704",
      "output_path": null,
      "input_image_path": "/mnt/d/projects/videogenproject/code/server/wan_local_service/outputs/123e4567-e89b-12d3-a456-426614174000/input_image.png",
      "error_message": "model directory not found: /mnt/d/projects/videogenproject/code/server/wan_local_service/third_party/Wan2.2-TI2V-5B",
      "log_path": "/mnt/d/projects/videogenproject/code/server/wan_local_service/logs/123e4567-e89b-12d3-a456-426614174000.log",
      "create_time": "2026-04-23T13:39:00+00:00",
      "update_time": "2026-04-23T13:39:00+00:00"
    }
  ],
  "total": 1,
  "limit": 10
}
```

### `GET /api/results`

Success response:

```json
{
  "items": [
    {
      "task_id": "123e4567-e89b-12d3-a456-426614174000",
      "output_path": "/mnt/d/projects/videogenproject/code/server/wan_local_service/outputs/123e4567-e89b-12d3-a456-426614174000/result.mp4",
      "create_time": "2026-04-23T13:39:00+00:00",
      "output_exists": true,
      "download_url": "http://127.0.0.1:8000/api/results/123e4567-e89b-12d3-a456-426614174000/file"
    }
  ],
  "total": 1,
  "limit": 10
}
```

### `GET /api/results/{task_id}/file`

用途：

- 下载指定任务的结果视频文件
- 供 Windows 客户端保存到本地目录

成功响应：

- `200 OK`
- `Content-Type: video/mp4`
- `Content-Disposition: attachment; filename="<task_id>.mp4"`
- 响应体为完整 `mp4` 二进制内容

客户端建议：

- 在 `status=succeeded` 且 `download_url != null` 时启用“保存到本地”按钮
- 使用 `download_url` 发起 `GET`
- 将响应体写入用户选择的 Windows 本地目录
- 不要依赖 `output_path` 指向的 WSL 路径做跨系统复制

## Error Examples

`unsupported_mode`:

```json
{
  "error": {
    "code": "unsupported_mode",
    "message": "Unsupported mode 'bad-mode'. Supported modes: t2v, i2v."
  }
}
```

`invalid_size`:

```json
{
  "error": {
    "code": "invalid_size",
    "message": "Invalid size '999*999'. Supported sizes: 1280*704, 704*1280."
  }
}
```

`validation_error`:

```json
{
  "error": {
    "code": "validation_error",
    "message": "body.prompt: Value error, prompt must not be empty"
  }
}
```

`task_not_found`:

```json
{
  "error": {
    "code": "task_not_found",
    "message": "Task 'not-found-task' was not found."
  }
}
```

`task_not_deletable`:

```json
{
  "error": {
    "code": "task_not_deletable",
    "message": "Task '123e4567-e89b-12d3-a456-426614174000' is currently running and cannot be deleted."
  }
}
```

`service_not_ready`:

```json
{
  "error": {
    "code": "service_not_ready",
    "message": "The service is not ready to accept tasks."
  }
}
```

`wan_execution_failed`:

```json
{
  "error": {
    "code": "wan_execution_failed",
    "message": "The service encountered an unexpected internal error."
  }
}
```
