# 2026-04-25 Client Server Delete Task API

## Scope

Switch the Windows Qt client Tasks deletion flow from local-only deletion to the service-backed protocol:

```text
DELETE /api/tasks/{task_id}
```

Videos deletion remains local-only and stays isolated to the Videos dialog.

The service was not modified, started, stopped, or restarted in this Windows client pass.

## Client Changes

Protocol:

- Added `TaskModels::TaskDeleteResponse`.
- Added `RequestKind::DeleteTask`.
- Added `ApiClient::deleteTask(taskId)`.
- Added response parsing for:

```json
{
  "task_id": "...",
  "deleted": true
}
```

Tasks UI:

- `Delete` now sends `DELETE /api/tasks/{task_id}` first.
- Local task cleanup happens only after the service returns a successful delete response.
- Service errors reuse the existing stable error handling path, including:
  - `task_not_deletable`
  - `task_not_found`
  - `task_delete_failed`
  - network errors
  - HTTP errors

Local cleanup after successful service deletion:

- Remove task state from the client task list.
- Remove matching background result mapping.
- Remove local task metadata.
- Remove local input image cache, thumbnail, thumbnail version file, and preview cache.
- Keep downloaded videos and `downloaded_videos.json`.
- Persist the task ID to `deleted_tasks.json` so stale list responses cannot re-show it.

Videos:

- The Videos dialog still owns local mp4 deletion.
- Deleting a task does not remove local mp4 files.

## Verification

Build:

```powershell
cmake --build code\client\qt_wan_chat\build --parallel
```

Result:

```text
Linking CXX executable qt_wan_chat.exe
```

Existing task smoke:

```powershell
qt_wan_chat.exe --smoke-task-id=18439c7f-d91b-42a4-a5f3-2e90624587f8 --smoke-timeout-ms=10000
```

Result:

```text
Smoke test reached terminal state: succeeded | output_path=/home/liupengkun/VedioGenProject/code/server/wan_local_service/outputs/18439c7f-d91b-42a4-a5f3-2e90624587f8/result.mp4 | download_url=http://127.0.0.1:8000/api/results/18439c7f-d91b-42a4-a5f3-2e90624587f8/file
```

Safe DELETE probe against the currently running service:

```powershell
curl.exe -s -i -X DELETE http://127.0.0.1:8000/api/tasks/codex-missing-delete-probe
```

Actual result:

```text
HTTP/1.1 405 Method Not Allowed
allow: GET
{"detail":"Method Not Allowed"}
```

Interpretation:

- The repository protocol and server code now include `DELETE /api/tasks/{task_id}`.
- The currently running FastAPI process has not loaded the new route yet.
- Real UI delete success must be re-tested after the service process is restarted or updated by the server-side owner.

Static checks:

```powershell
git diff --check
```

Result:

```text
No whitespace errors. Git only reported LF-to-CRLF working-copy warnings.
```

## Remaining Manual Check

- Restart or update the running service process.
- Delete a disposable `pending` / `succeeded` / `failed` task from the Windows client.
- Confirm the task disappears from the service task list and result list.
- Confirm downloaded local mp4 files remain visible in Videos until deleted from the Videos dialog.
