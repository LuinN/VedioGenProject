# 2026-04-25 Client Thumbnail Stale Frame Fix

## Scope

Fix the Windows Qt client issue where completed task cards could show the same generated video frame across different videos.

Only the client was changed. The service was not modified, started, stopped, or restarted.

## Problem

Observed UI issue:

```text
All videos used the same generated frame image.
```

Client-side cause found:

- The thumbnail extractor reused one shared `QMediaPlayer` and one shared `QVideoSink`.
- When the player source changed between videos, the next `videoFrameChanged` callback could still carry a stale frame from the previous media.
- Existing `thumbnail.png` files were treated as valid forever, so bad cached thumbnails were not rebuilt.
- A first fix that waited only for `LoadedMedia` / `BufferedMedia` timed out on this Qt Multimedia backend, even though FFmpeg could open the mp4.

## Fix

- Removed the shared thumbnail `QMediaPlayer` / `QVideoSink` members.
- Each queued task now creates its own local `QMediaPlayer` and `QVideoSink`.
- Added thumbnail cache versioning:

```text
%LOCALAPPDATA%/VideoGenProject/tasks/<task_id>/thumbnail.version
```

- Current version:

```text
2
```

- If `thumbnail.png` exists but `thumbnail.version` is missing or stale, the client removes the old png and regenerates it.
- Before saving a new thumbnail, the client removes the old `thumbnail.png`.
- The extractor seeks into the task's own local mp4 before accepting frames.
- A timer fallback enables frame capture even if Qt Multimedia does not emit the expected loaded/buffered media status.

## Verification

Build:

```powershell
cmake --build code\client\qt_wan_chat\build --parallel
```

Result:

```text
Linking CXX executable qt_wan_chat.exe
```

GUI thumbnail regeneration:

- Started the client for 30 seconds.
- The client loaded 3 result items and 3 task items.
- The client generated fresh thumbnails and version files for all 3 local mp4 files from the Videos index.

Generated files:

```text
C:\Users\37545\AppData\Local\VideoGenProject\tasks\0dfbe405-19cb-4256-a86b-13c49569a5b5\thumbnail.png
C:\Users\37545\AppData\Local\VideoGenProject\tasks\0dfbe405-19cb-4256-a86b-13c49569a5b5\thumbnail.version
C:\Users\37545\AppData\Local\VideoGenProject\tasks\18439c7f-d91b-42a4-a5f3-2e90624587f8\thumbnail.png
C:\Users\37545\AppData\Local\VideoGenProject\tasks\18439c7f-d91b-42a4-a5f3-2e90624587f8\thumbnail.version
C:\Users\37545\AppData\Local\VideoGenProject\tasks\57783f7a-5915-49f2-b105-8cd15dd26fbe\thumbnail.png
C:\Users\37545\AppData\Local\VideoGenProject\tasks\57783f7a-5915-49f2-b105-8cd15dd26fbe\thumbnail.version
```

Thumbnail sizes:

```text
0dfbe405-19cb-4256-a86b-13c49569a5b5      619094 bytes
18439c7f-d91b-42a4-a5f3-2e90624587f8      364520 bytes
57783f7a-5915-49f2-b105-8cd15dd26fbe      415876 bytes
```

Thumbnail SHA256:

```text
0dfbe405-19cb-4256-a86b-13c49569a5b5      F578E7306F5B467296E87276883997C85461632F0BAE64BD395AA46C7BFD1D27
18439c7f-d91b-42a4-a5f3-2e90624587f8      5720DC16BDB1D1C45024DC71DA00709A6C62BD5EC4C1434DF74FA44FA3EC3C7B
57783f7a-5915-49f2-b105-8cd15dd26fbe      0FBB94A6A0302F0759A52F04C124447C6A2E0753CF948941E456EF5F7168B065
```

Existing task smoke:

```powershell
qt_wan_chat.exe --smoke-task-id=18439c7f-d91b-42a4-a5f3-2e90624587f8 --smoke-timeout-ms=10000
```

Result:

```text
Smoke test reached terminal state: succeeded | output_path=/home/liupengkun/VedioGenProject/code/server/wan_local_service/outputs/18439c7f-d91b-42a4-a5f3-2e90624587f8/result.mp4 | download_url=http://127.0.0.1:8000/api/results/18439c7f-d91b-42a4-a5f3-2e90624587f8/file
```

## Remaining Manual Check

- Need visual confirmation in the desktop UI that each task card thumbnail corresponds to its own video content.
- Need manual double-click verification that the task preview opens the Windows default video player.
