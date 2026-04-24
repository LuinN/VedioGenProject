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

- 仅支持 `mode=t2v`
- 仅支持 `size=1280*704` 或 `size=704*1280`
- 服务内部固定调用官方 `Wan2.2/generate.py --task ti2v-5B`

## Status Enum

状态枚举在代码、协议文档、README、自测报告中保持一致：

- `pending`
- `running`
- `succeeded`
- `failed`

客户端轮询建议：

- 创建任务后，每 2 秒轮询一次 `GET /api/tasks/{task_id}`
- 终态为 `succeeded` 或 `failed`

## Null Semantics

- `output_path`
  - `pending` / `running` / `failed`: `null`
  - `succeeded`: 绝对路径字符串
- `error_message`
  - `pending` / `running` / `succeeded`: `null`
  - `failed`: 非空字符串
  - 优先返回前置检查失败原因，或 `generate.py` 日志尾部提炼出的真实错误摘要，并附带退出码
- `log_path`
  - 任务创建成功后立即分配为绝对路径字符串
  - 即使日志文件还没真正写出，也先返回预留路径
- `output_exists`
  - 仅在 `GET /api/tasks/{task_id}` 与 `GET /api/results` 中返回
  - 真实文件存在为 `true`，否则为 `false`
- `status_message`
  - 仅在 `GET /api/tasks/{task_id}` 中返回
  - 可为 `null`
  - 典型值包括 `creating pipeline`、`loading checkpoints`、`sampling`、`saving video`、`finished`
- `progress_current` / `progress_total` / `progress_percent`
  - 仅在 `GET /api/tasks/{task_id}` 中返回
  - 可为 `null`
  - 采样阶段通常返回当前 step、总 step 和百分比
  - 成功完成时可返回 `progress_percent=100`

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
| `unsupported_mode` | `400 Bad Request` | 请求中的 `mode` 不是 `t2v` |
| `invalid_size` | `400 Bad Request` | 请求中的 `size` 不在白名单 |
| `validation_error` | `422 Unprocessable Entity` | 请求体缺字段、字段类型错误、空 prompt |
| `task_not_found` | `404 Not Found` | 查询了不存在的任务 ID |
| `service_not_ready` | `503 Service Unavailable` | 服务上下文未完成初始化 |
| `wan_execution_failed` | `500 Internal Server Error` | API 层意外内部错误 |

语义补充：

- 异步推理失败不会把 `GET /api/tasks/{task_id}` 变成 `500`
- 异步推理失败通过任务对象的 `status=failed` 和 `error_message` 表达

## Restart Recovery Semantics

服务启动时会扫描遗留 `pending` 与 `running` 任务，并统一改成 `failed`。

- 遗留 `pending`
  - `status = "failed"`
  - `error_message = "service restarted before task execution"`
- 遗留 `running`
  - `status = "failed"`
  - `error_message = "service restarted while task was running"`

共同规则：

- `update_time` 刷新为服务启动时刻
- `output_path` 保持 `null`
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

Request body:

```json
{
  "mode": "t2v",
  "prompt": "A cinematic cyberpunk street at night, slow camera push-in, rain reflections on the ground",
  "size": "1280*704"
}
```

Success response:

```json
{
  "task_id": "123e4567-e89b-12d3-a456-426614174000",
  "status": "pending",
  "prompt": "A cinematic cyberpunk street at night, slow camera push-in, rain reflections on the ground",
  "output_path": null,
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
  "status": "running",
  "prompt": "A cinematic cyberpunk street at night, slow camera push-in, rain reflections on the ground",
  "output_path": null,
  "error_message": null,
  "log_path": "/mnt/d/projects/videogenproject/code/server/wan_local_service/logs/123e4567-e89b-12d3-a456-426614174000.log",
  "create_time": "2026-04-23T13:39:00+00:00",
  "update_time": "2026-04-23T13:39:03+00:00",
  "output_exists": false,
  "status_message": "sampling",
  "progress_current": 9,
  "progress_total": 50,
  "progress_percent": 18
}
```

Succeeded example:

```json
{
  "task_id": "123e4567-e89b-12d3-a456-426614174000",
  "status": "succeeded",
  "prompt": "A cinematic cyberpunk street at night, slow camera push-in, rain reflections on the ground",
  "output_path": "/mnt/d/projects/videogenproject/code/server/wan_local_service/outputs/123e4567-e89b-12d3-a456-426614174000/result.mp4",
  "error_message": null,
  "log_path": "/mnt/d/projects/videogenproject/code/server/wan_local_service/logs/123e4567-e89b-12d3-a456-426614174000.log",
  "create_time": "2026-04-23T13:39:00+00:00",
  "update_time": "2026-04-23T13:48:00+00:00",
  "output_exists": true,
  "status_message": "finished",
  "progress_current": 50,
  "progress_total": 50,
  "progress_percent": 100
}
```

Failed example:

```json
{
  "task_id": "123e4567-e89b-12d3-a456-426614174000",
  "status": "failed",
  "prompt": "A cinematic cyberpunk street at night, slow camera push-in, rain reflections on the ground",
  "output_path": null,
  "error_message": "AssertionError (generate.py exit code 1)",
  "log_path": "/mnt/d/projects/videogenproject/code/server/wan_local_service/logs/123e4567-e89b-12d3-a456-426614174000.log",
  "create_time": "2026-04-23T13:39:00+00:00",
  "update_time": "2026-04-23T13:39:00+00:00",
  "output_exists": false,
  "status_message": null,
  "progress_current": null,
  "progress_total": null,
  "progress_percent": null
}
```

### `GET /api/tasks`

Success response:

```json
{
  "items": [
    {
      "task_id": "123e4567-e89b-12d3-a456-426614174000",
      "status": "failed",
      "prompt": "A cinematic cyberpunk street at night, slow camera push-in, rain reflections on the ground",
      "output_path": null,
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
      "output_exists": true
    }
  ],
  "total": 1,
  "limit": 10
}
```

## Error Examples

`unsupported_mode`:

```json
{
  "error": {
    "code": "unsupported_mode",
    "message": "Unsupported mode 'i2v'. Only 't2v' is supported."
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
