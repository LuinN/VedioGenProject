# 2026-04-25 Client Task And Video Deletion

## Scope

Add deletion support to the Windows Qt client with a strict boundary:

- Tasks can be deleted from the client task list together with local task data.
- Downloaded videos are not deleted by task deletion.
- Local video files can only be deleted from the Videos dialog.

The service was not modified, started, stopped, or restarted.

## Client Changes

Tasks:

- Added a `Delete` button to the Tasks header.
- Added keyboard `Delete` shortcut while the task list has focus.
- Deleting a task asks for confirmation.
- Deleting a task removes local client state:
  - task entry from the in-memory task list
  - matching background result entry
  - local task metadata
  - active/in-flight polling state
  - thumbnail queue state
  - local task cache under `%LOCALAPPDATA%/VideoGenProject/tasks/<task_id>/`
- If a downloaded video from the Videos index is stored inside the task cache directory, that mp4 is preserved.
- Deleted task IDs are persisted to:

```text
QStandardPaths::AppDataLocation/deleted_tasks.json
```

- Future `/api/tasks` and `/api/results` responses skip locally deleted task IDs, so deleted tasks do not reappear after refresh or restart.

Videos:

- Added `Delete Selected` to the Videos dialog.
- Deleting a video asks for confirmation.
- Deleting a video removes:
  - the selected local mp4 file
  - the selected entry from `downloaded_videos.json`
- Deleting a video does not delete task history.

## Boundary

The current service contract has no `DELETE /api/tasks/{task_id}` endpoint.

Therefore task deletion is client-local:

- It does not cancel server-side inference.
- It does not remove service task history.
- It does not remove service output files.

This matches the current client-only request and keeps video deletion isolated to the Videos dialog.

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

Static checks:

```powershell
git diff --check
```

Result:

```text
No whitespace errors. Git only reported existing LF-to-CRLF working-copy warnings.
```

## Remaining Manual Check

- In the desktop UI, delete a non-critical history task and confirm it stays hidden after refresh.
- Confirm task deletion does not remove the selected task's Videos entry or local mp4.
- In the Videos dialog, delete a disposable local mp4 and confirm both the file and `downloaded_videos.json` entry are removed.
