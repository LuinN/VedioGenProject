# 2026-04-24 Client Result Download And Video List

## Scope

This Windows-side pass only changed the Qt client.

Implemented:

- parse `download_url` from task detail and result list responses
- download `GET /api/results/{task_id}/file` into a Windows local `<task_id>.mp4`
- use `QSaveFile` for atomic local writes
- persist downloaded video metadata in `downloaded_videos.json`
- show a local `Videos` table in the client
- open selected local videos with the Windows default player
- add `--smoke-download-dir` for command-line download verification

The server was not modified or restarted by this client pass.

## Build Verification

Workspace:

- `D:\Projects\VideoGenProject`

Configure command:

```powershell
$env:PATH='D:\Qt\Tools\Ninja;D:\Qt\Tools\mingw1310_64\bin;D:\Qt\6.11.0\mingw_64\bin;' + $env:PATH
& 'D:\Qt\Tools\CMake_64\bin\cmake.exe' `
  -S 'code\client\qt_wan_chat' `
  -B 'code\client\qt_wan_chat\build' `
  -G Ninja `
  -D CMAKE_BUILD_TYPE=Debug `
  -D CMAKE_PREFIX_PATH='D:\Qt\6.11.0\mingw_64'
```

Result: passed

Build command:

```powershell
$env:PATH='D:\Qt\Tools\Ninja;D:\Qt\Tools\mingw1310_64\bin;D:\Qt\6.11.0\mingw_64\bin;' + $env:PATH
& 'D:\Qt\Tools\CMake_64\bin\cmake.exe' --build 'code\client\qt_wan_chat\build' --parallel
```

Result: passed

## Real Download Verification

Source task:

- `task_id`: `18439c7f-d91b-42a4-a5f3-2e90624587f8`
- status: `succeeded`
- `download_url`: `http://127.0.0.1:8000/api/results/18439c7f-d91b-42a4-a5f3-2e90624587f8/file`

Smoke command:

```powershell
$env:PATH='D:\Qt\Tools\Ninja;D:\Qt\Tools\mingw1310_64\bin;D:\Qt\6.11.0\mingw_64\bin;' + $env:PATH
& 'code\client\qt_wan_chat\build\qt_wan_chat.exe' `
  --smoke-task-id=18439c7f-d91b-42a4-a5f3-2e90624587f8 `
  --smoke-download-dir='D:\Projects\VideoGenProject\code\client\qt_wan_chat\build\smoke_downloads' `
  --smoke-timeout-ms=10000
```

Observed output:

```text
Smoke test downloaded result: D:/Projects/VideoGenProject/code/client/qt_wan_chat/build/smoke_downloads/18439c7f-d91b-42a4-a5f3-2e90624587f8.mp4 | bytes=8060815 | index=C:/Users/37545/AppData/Roaming/VideoGenProject/qt_wan_chat/downloaded_videos.json
```

Downloaded file:

- `D:\Projects\VideoGenProject\code\client\qt_wan_chat\build\smoke_downloads\18439c7f-d91b-42a4-a5f3-2e90624587f8.mp4`
- size: `8060815` bytes

Persistent index:

- `C:\Users\37545\AppData\Roaming\VideoGenProject\qt_wan_chat\downloaded_videos.json`
- contains `task_id`, `prompt`, `local_path`, `download_url`, `source_output_path`, `create_time`, `downloaded_at`, and `file_size`

Note:

- The first non-elevated smoke run could download into the workspace but could not write the AppData index due to the agent sandbox.
- The elevated rerun verified the real Windows AppData persistence path.

## Remaining Verification

Not verified in this agent session:

- opening the local mp4 through the Windows default player from the GUI

Reason:

- player launch is a desktop GUI action and should be checked in the real Windows desktop session.

Next manual step:

- open `code\client\qt_wan_chat\build\qt_wan_chat.exe`
- confirm the `Videos` table loads the persisted mp4 entry
- double-click the row or click `Play Selected`
- confirm the Windows default player opens and plays the local mp4

