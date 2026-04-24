# 2026-04-24 Client I2V Image Input

## Scope

- Add one-image attachment support to the Qt chat input.
- Submit `mode=i2v` tasks with `multipart/form-data`.
- Keep existing no-image `mode=t2v` JSON flow unchanged.
- Cache selected images under `%LOCALAPPDATA%/VideoGenProject/tasks`.
- Persist per-task `metadata.json` after the service returns `task_id`.
- Replace the task table with card-style task rows that can show an input reference image.

## Client Changes

- Input area now has a `+` image button and a preview block with thumbnail, filename, size, and remove button.
- Supported local image formats: `png`, `jpg`, `jpeg`, `webp`.
- Local validation checks:
  - file exists
  - file is readable
  - extension is supported
  - `QImageReader` can read the image
  - file size is at most `20 MiB`
- `ApiClient` now supports:
  - JSON `createTask(prompt, size)` for `t2v`
  - multipart `createImageTask(prompt, size, localImagePath, clientRequestId)` for `i2v`
- `TaskSummary` / `TaskDetail` now parse:
  - `mode`
  - `size`
  - `input_image_path`
  - `input_image_exists`
- `--smoke-image <path>` was added for smoke creation of an `i2v` task.

## Build Verification

Configure:

```powershell
cmake -S code\client\qt_wan_chat -B code\client\qt_wan_chat\build -G Ninja -D CMAKE_BUILD_TYPE=Debug -D CMAKE_PREFIX_PATH=D:\Qt\6.11.0\mingw_64
```

Result:

```text
Configuring done
Generating done
Build files have been written to: D:/Projects/VideoGenProject/code/client/qt_wan_chat/build
```

Build:

```powershell
cmake --build code\client\qt_wan_chat\build --parallel
```

Result:

```text
Linking CXX executable qt_wan_chat.exe
```

## Smoke Verification

Temporary input image:

```text
D:\Projects\VideoGenProject\code\client\qt_wan_chat\build\smoke_assets\i2v_smoke.png
```

Size:

```text
434 bytes
```

Command:

```powershell
qt_wan_chat.exe --smoke-prompt="i2v client smoke test" --smoke-image=D:\Projects\VideoGenProject\code\client\qt_wan_chat\build\smoke_assets\i2v_smoke.png --smoke-timeout-ms=10000
```

Observed result:

```text
body: Input should be a valid dictionary or object to extract fields from [HTTP 422] [code=validation_error]
```

Interpretation:

- The Windows client reached `POST /api/tasks`.
- The client error display preserved the service stable error code.
- The checked-in service contract supports multipart `i2v`, but the service process that was already running during this pass still behaved like the earlier JSON-only implementation.
- This pass did not restart, stop, or modify the service process.
- The fixed client no longer leaves new `pending_*` image cache directories after this create-task failure.

Existing T2V monitor smoke:

```powershell
qt_wan_chat.exe --smoke-task-id=18439c7f-d91b-42a4-a5f3-2e90624587f8 --smoke-timeout-ms=10000
```

Result:

```text
Smoke test reached terminal state: succeeded | output_path=/home/liupengkun/VedioGenProject/code/server/wan_local_service/outputs/18439c7f-d91b-42a4-a5f3-2e90624587f8/result.mp4 | download_url=http://127.0.0.1:8000/api/results/18439c7f-d91b-42a4-a5f3-2e90624587f8/file
```

## Remaining Issues

- Need a service-side restart/update of the already-running FastAPI process before the Windows client can verify successful multipart `i2v` task creation.
- Need a real GPU `i2v` task after that to verify `input_image_path`, `--image`, progress polling, and final `result.mp4`.
- Need manual GUI verification for the new card list and image preview interactions.
