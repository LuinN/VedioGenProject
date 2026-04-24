# 2026-04-25 Client Toolbar And Task Thumbnails

## Scope

- Remove the always-visible right-side panel from startup UI.
- Add a top toolbar to the Wan Chat area.
- Move Configuration, Videos, and Diagnostics into non-modal dialogs.
- Keep `/api/results` as background data only.
- Add first-frame thumbnails to succeeded task cards.

## Client Changes

- Main window now shows only:
  - left `Tasks`
  - center `Wan Chat`
- Wan Chat toolbar now has:
  - `Configuration`
  - `Videos`
  - `Diagnostics`
- Dialog behavior:
  - each toolbar button opens a non-modal `QDialog`
  - dialogs can be closed without losing widget state
- `Results` is no longer shown to the user.
- Succeeded task cards now include a media preview area.
- Double-clicking a task preview opens the local mp4 with the Windows default player.

## Thumbnail Implementation

- Added Qt Multimedia dependency.
- First frame extraction uses:
  - `QMediaPlayer`
  - `QVideoSink`
- Thumbnail cache:

```text
%LOCALAPPDATA%/VideoGenProject/tasks/<task_id>/thumbnail.png
```

- Preview mp4 cache:

```text
%LOCALAPPDATA%/VideoGenProject/tasks/<task_id>/result.mp4
```

- If a matching mp4 already exists in `downloaded_videos.json`, the client uses that file.
- If no local mp4 exists and the task has `download_url`, the client downloads a preview copy into the task cache.
- Preview downloads do not update the user-facing Videos index.

## Verification

Configure:

```powershell
cmake -S code\client\qt_wan_chat -B code\client\qt_wan_chat\build -G Ninja -D CMAKE_BUILD_TYPE=Debug -D CMAKE_PREFIX_PATH=D:\Qt\6.11.0\mingw_64
```

Result:

```text
Configuring done
Generating done
```

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

Thumbnail verification:

```text
C:\Users\37545\AppData\Local\VideoGenProject\tasks\18439c7f-d91b-42a4-a5f3-2e90624587f8\thumbnail.png
```

Result:

```text
614256 bytes
```

## Remaining Manual Check

- Need real desktop visual inspection for toolbar/dialog placement.
- Need manual double-click verification that the task preview opens the Windows default video player.
