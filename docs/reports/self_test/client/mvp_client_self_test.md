# MVP Client Self Test

## 1. Environment And Toolchain

- Date: 2026-04-23
- Workspace: `D:\Projects\VideoGenProject`
- Client root: `code/client/qt_wan_chat`
- Qt: `D:\Qt\6.11.0\mingw_64`
- CMake: `D:\Qt\Tools\CMake_64\bin\cmake.exe`
- Ninja: `D:\Qt\Tools\Ninja\ninja.exe`
- MinGW: `D:\Qt\Tools\mingw1310_64\bin\g++.exe`

Real Windows build command:

```powershell
$env:PATH='D:\Qt\Tools\Ninja;D:\Qt\Tools\mingw1310_64\bin;D:\Qt\6.11.0\mingw_64\bin;' + $env:PATH
& 'D:\Qt\Tools\CMake_64\bin\cmake.exe' `
  -S 'code\client\qt_wan_chat' `
  -B 'code\client\qt_wan_chat\build' `
  -G Ninja `
  -D CMAKE_BUILD_TYPE=Debug `
  -D CMAKE_PREFIX_PATH='D:\Qt\6.11.0\mingw_64'
& 'D:\Qt\Tools\CMake_64\bin\cmake.exe' --build 'code\client\qt_wan_chat\build' --parallel
```

Result: passed

## 2. Main Window Startup

Verified executable:

- `code/client/qt_wan_chat/build/qt_wan_chat.exe`

Real startup verification:

- client executable launched successfully on Windows
- main window handle existed and responded
- initial client requests succeeded:
  - `GET /healthz`
  - `GET /api/tasks?limit=20`
  - `GET /api/results?limit=20`

Observed diagnostics:

```text
[2026-04-23T22:14:56] Connected to service 'wan-local-service' at http://127.0.0.1:8000/
[2026-04-23T22:14:56] Loaded 5 task item(s).
[2026-04-23T22:14:56] Loaded 0 result item(s).
```

Result: passed

## 3. Chat Send Flow Verification

Client added a reproducible smoke-test path:

```powershell
qt_wan_chat.exe --smoke-prompt=smoke_client_prompt
```

Real smoke-test evidence:

- task `2eea7312-9b99-41f9-8ec1-43d33474e824`
  - client observed `pending -> running`
  - service later marked it `failed`
  - API `error_message`: `generate.py exited with code 1`
- task `141f1a6d-ba50-44ec-9dec-4662ec43ab7c`
  - client observed `pending -> running`
  - later polling hit `network_error / Connection refused`

Observed diagnostics from the second smoke run:

```text
[2026-04-23T22:20:36] Submitting task with size=1280*704 to http://127.0.0.1:8000/
[2026-04-23T22:20:36] Task created: 141f1a6d-ba50-44ec-9dec-4662ec43ab7c status=pending
[2026-04-23T22:20:38] Task update: Task 141f1a6d-ba50-44ec-9dec-4662ec43ab7c -> running
```

Result:

- passed for local prompt insertion, `POST /api/tasks`, and polling startup

## 4. Status Polling Verification

Verified in real client diagnostics:

- `pending -> running` transition was received and rendered
- polling used the live task id returned by the service
- when the service later became unavailable, client surfaced:

```text
Could not reach the local service. Check the URL and make sure FastAPI is running. [code=network_error]
```

The same second smoke run ended with:

```text
details=Connection refused
```

Result:

- passed for polling mechanics and non-blocking error handling
- not fully passed for stable terminal-state observation because the local FastAPI service dropped during the second smoke run

## 5. Success / Failure Display Logic

Verified in the live client:

- health success messaging
- startup tasks/results loading
- task creation success messaging
- task status transition messaging
- network failure messaging

Verified via live API contract and task history already loaded by the client:

- `failed` task objects include non-null `error_message`
- client parser accepts current `failed` task payloads returned by `/api/tasks`

Not fully verified in a completed Qt polling session:

- terminal `failed` rendering after the same live task finishes
- terminal `succeeded` rendering

Reason:

- the second smoke run lost service connectivity before the terminal poll completed

## 6. Open Output Directory Verification

Implemented in client:

- Linux `output_path` -> `\\wsl$\<distro>\...`
- use output file parent directory
- `explorer.exe` open
- clear non-blocking error when path is empty, invalid, or inaccessible

Real verification status:

- `/api/results` returned `0` items in this session
- no successful `output_path` was available for a true success-path open test
- direct Windows access check for a known WSL path returned:

```text
Access to the path '\\wsl$\Ubuntu-24.04\mnt\d\Projects\VideoGenProject\code\server\wan_local_service\logs' is denied.
```

Result:

- failure-path handling is implemented
- success-path open-directory flow is not verified in this session

## 7. Current Problems

### 1. WSL service dropped during client polling

Real symptom:

```text
Connection refused (127.0.0.1:8000)
```

Impact:

- the Qt client correctly surfaced the outage
- end-to-end terminal-state verification remains unstable

### 2. Latest real service log ended inside official `generate.py`

Real log:

- `code/server/wan_local_service/logs/141f1a6d-ba50-44ec-9dec-4662ec43ab7c.log`

Observed tail:

```text
KeyboardInterrupt
generate.py exit code: -2
```

Impact:

- no real `result.mp4` was produced
- results-list success flow and open-output success flow remain blocked

### 3. `\\wsl$` access is denied in the current Windows agent session

Real symptom:

```text
Access to the path '\\wsl$\Ubuntu-24.04\mnt\d\Projects\VideoGenProject\code\server\wan_local_service\logs' is denied.
```

Impact:

- client conversion logic exists
- real success-path directory opening remains unverified

