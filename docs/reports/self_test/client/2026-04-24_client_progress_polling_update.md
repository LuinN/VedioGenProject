# 2026-04-24 Client Progress Polling Update

## Scope

This Windows-side update only changed the Qt client:

- parsed task detail progress fields returned by `GET /api/tasks/{task_id}`
- rendered task `Stage` and `Progress` in the task table
- included progress summaries in polling diagnostics and status bar notices
- changed command-line smoke test default timeout from 60 seconds to 60 minutes
- added `--smoke-timeout-ms` for explicit long-task test windows
- added `--smoke-task-id` to poll an existing task without creating a new one
- skipped the `QDir.exists()` pre-check for `\\wsl$` and `\\wsl.localhost` output directories so Explorer gets the open request directly

The service implementation was not modified in this Windows client pass.

## Build Verification

Workspace:

- `D:\Projects\VideoGenProject`

Real Windows configure command:

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

Real Windows build command:

```powershell
$env:PATH='D:\Qt\Tools\Ninja;D:\Qt\Tools\mingw1310_64\bin;D:\Qt\6.11.0\mingw_64\bin;' + $env:PATH
& 'D:\Qt\Tools\CMake_64\bin\cmake.exe' --build 'code\client\qt_wan_chat\build' --parallel
```

Result: passed

Observed build tail:

```text
[2/3] Building CXX object CMakeFiles/qt_wan_chat.dir/src/MainWindow.cpp.obj
[3/3] Linking CXX executable qt_wan_chat.exe
```

## Real Client Smoke Verification

The service was already running and was not started or stopped by this client pass.

Real client submit command:

```powershell
$env:PATH='D:\Qt\Tools\Ninja;D:\Qt\Tools\mingw1310_64\bin;D:\Qt\6.11.0\mingw_64\bin;' + $env:PATH
& 'code\client\qt_wan_chat\build\qt_wan_chat.exe' `
  --smoke-prompt='A calm lake at sunrise, slow camera push-in, soft golden light' `
  --smoke-timeout-ms=2700000
```

Observed result:

- client created task `18439c7f-d91b-42a4-a5f3-2e90624587f8`
- the 45 minute smoke window expired while the task was still `running`
- the task later completed successfully
- this showed the 45 minute default was too short for the current SDPA fallback path, so the client default was raised to 60 minutes

Real task detail after completion:

```text
status=succeeded
status_message=finished
progress_current=50
progress_total=50
progress_percent=100
output_path=/home/liupengkun/VedioGenProject/code/server/wan_local_service/outputs/18439c7f-d91b-42a4-a5f3-2e90624587f8/result.mp4
```

Real client reattach command:

```powershell
$env:PATH='D:\Qt\Tools\Ninja;D:\Qt\Tools\mingw1310_64\bin;D:\Qt\6.11.0\mingw_64\bin;' + $env:PATH
& 'code\client\qt_wan_chat\build\qt_wan_chat.exe' `
  --smoke-task-id=18439c7f-d91b-42a4-a5f3-2e90624587f8 `
  --smoke-timeout-ms=10000
```

Observed output:

```text
Smoke test reached terminal state: succeeded | output_path=/home/liupengkun/VedioGenProject/code/server/wan_local_service/outputs/18439c7f-d91b-42a4-a5f3-2e90624587f8/result.mp4
```

Result: passed for client task creation, reattach polling, terminal `succeeded` handling, progress-field parsing, and output path reporting.

## Remaining Verification

The current Windows agent session still cannot access the `\\wsl$` path:

```text
Access to the path '\\wsl$\Ubuntu-24.04\home\liupengkun\VedioGenProject\code\server\wan_local_service\outputs\18439c7f-d91b-42a4-a5f3-2e90624587f8' is denied.
```

The client now sends WSL UNC paths directly to `explorer.exe` without blocking on `QDir.exists()`, but the Explorer success path still needs verification in the real desktop session.
