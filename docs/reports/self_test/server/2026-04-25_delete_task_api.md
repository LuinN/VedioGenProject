# 2026-04-25 Delete Task API

## Scope

- Add `DELETE /api/tasks/{task_id}`
- Delete non-running task records and local artifacts
- Keep running-task deletion rejected with a stable error

## Behavior

- Allowed:
  - `pending`
  - `succeeded`
  - `failed`
- Rejected:
  - `running`
- Successful deletion removes:
  - SQLite row in `tasks`
  - `logs/<task_id>.log`
  - `outputs/<task_id>/`

## Files

- `code/server/wan_local_service/app/main.py`
- `code/server/wan_local_service/app/repository.py`
- `code/server/wan_local_service/app/errors.py`
- `code/server/wan_local_service/app/schemas.py`
- `code/server/wan_local_service/tests/test_api.py`
- `code/server/wan_local_service/tests/test_repository.py`
- `code/server/wan_local_service/tests/test_task_runner.py`
- `docs/reports/integration/wan_local_service_api_contract.md`
- `code/server/wan_local_service/README_WAN_LOCAL_SERVICE.md`

## Verification

Command:

```bash
cd code/server/wan_local_service
PYTHONPATH=. .venv/bin/python -m pytest -q tests
```

Result:

```text
37 passed in 1.73s
```

Covered cases:

- delete `succeeded` task removes DB row, `logs/<task_id>.log`, and `outputs/<task_id>/`
- deleted succeeded task disappears from `GET /api/results`
- delete `pending` task succeeds even if no artifact files exist yet
- delete `running` task returns `task_not_deletable`
- delete missing task returns `task_not_found`
- worker safely skips stale queued task IDs after a task row has been deleted

Python syntax check:

```bash
python3 -m py_compile code/server/wan_local_service/app/*.py
```

Result:

```text
ok
```

## Notes

- 本轮删除功能没有补“取消正在运行的推理子进程”。
- 因此 `running` 任务删除当前固定返回 `409 task_not_deletable`。
- 这轮验收以 ASGI/pytest 自测为主，没有另外做独立后台服务的手工 HTTP 复验。
