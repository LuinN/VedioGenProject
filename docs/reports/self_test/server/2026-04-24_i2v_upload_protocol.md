# 2026-04-24 i2v Upload Protocol

## Scope

- Extend `POST /api/tasks` to support:
  - `application/json` `t2v`
  - `multipart/form-data` `t2v`
  - `multipart/form-data` `i2v`
- Save uploaded input images to `outputs/<task_id>/input_image.<ext>`
- Persist `input_image_path`
- Expose `input_image_exists`
- Pass `--image <input_image_path>` to official Wan `generate.py` for `i2v`

## Files

- `code/server/wan_local_service/app/main.py`
- `code/server/wan_local_service/app/wan_runner.py`
- `code/server/wan_local_service/app/repository.py`
- `code/server/wan_local_service/app/db.py`
- `code/server/wan_local_service/app/schemas.py`
- `code/server/wan_local_service/app/errors.py`
- `code/server/wan_local_service/app/config.py`
- `code/server/wan_local_service/app/env_report.py`
- `code/server/wan_local_service/requirements-service.txt`
- `code/server/wan_local_service/tests/test_api.py`
- `code/server/wan_local_service/tests/test_repository.py`
- `code/server/wan_local_service/tests/test_wan_runner.py`

## Verification

### Service Tests

Command:

```bash
cd code/server/wan_local_service
PYTHONPATH=. .venv/bin/python -m pytest -q tests
```

Result:

```text
31 passed in 1.43s
```

Covered cases:

- JSON `t2v` task creation still works
- multipart `t2v` task creation works
- multipart `i2v` task creation works
- `i2v` missing image returns `image_required`
- unsupported image type returns `image_not_supported`
- oversized image returns `image_too_large`
- `input_image_path` persists to SQLite and lands in `outputs/<task_id>/input_image.<ext>`
- `GET /api/tasks/{task_id}` returns `input_image_path` and `input_image_exists`
- result list contract remains unchanged
- `WanRunner` adds `--image` for `i2v`
- `WanRunner` fails early with a real message when an `i2v` task is missing `input_image_path`

### Python Syntax

Command:

```bash
python3 -m py_compile code/server/wan_local_service/app/*.py
```

Result:

```text
ok
```

### Environment Report

Command:

```bash
cd code/server/wan_local_service
bash scripts/check_env.sh --require service
```

Result:

```text
service_ready=yes
python_import:multipart -> ok
```

## Notes

- 本轮没有重跑真实 GPU `i2v` 长任务。
- 尝试在当前 agent 内用独立命令会话对临时前台端口做 HTTP 复验时，端口连通性表现不稳定，因此这轮把 ASGI + pytest 作为主验证手段。
- 当前可以确认：
  - 协议已支持 `i2v`
  - 图片上传会被校验并落盘
  - `generate.py` 命令会带 `--image`
  - 服务端契约和错误码已更新
