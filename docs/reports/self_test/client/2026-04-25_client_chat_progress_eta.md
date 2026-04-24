# Windows Qt Client Self Test - Chat Progress Cards and ETA

Date: 2026-04-25

## Scope

Implemented Wan Chat progress rendering as an updatable Qt Widgets message flow.

- Replaced the chat display path from `QTextBrowser` HTML append to `QScrollArea + QVBoxLayout`.
- Kept user and important system messages as lightweight bubbles.
- Added one reusable task progress card per `task_id`.
- Progress polling now updates the card in place instead of appending a System message on every progress sample.
- Diagnostics still records every real progress update.
- Added elapsed time, estimated remaining time, and estimated completion time based on locally observed progress.

## Build

The plain shell PATH did not include CMake/Qt/MinGW. The successful build used the project Qt toolchain paths:

```powershell
$env:PATH='D:\Qt\Tools\Ninja;D:\Qt\Tools\mingw1310_64\bin;D:\Qt\6.11.0\mingw_64\bin;' + $env:PATH
& 'D:\Qt\Tools\CMake_64\bin\cmake.exe' --build code\client\qt_wan_chat\build --parallel 1
```

Result:

```text
[1/4] Building CXX object CMakeFiles/qt_wan_chat.dir/qt_wan_chat_autogen/mocs_compilation.cpp.obj
[2/4] Building CXX object CMakeFiles/qt_wan_chat.dir/src/main.cpp.obj
[3/4] Building CXX object CMakeFiles/qt_wan_chat.dir/src/MainWindow.cpp.obj
[4/4] Linking CXX executable qt_wan_chat.exe
Packaged qt_wan_chat release:
  exe: D:\Projects\VideoGenProject\code\client\qt_wan_chat\release\qt_wan_chat.exe
  dir: D:\Projects\VideoGenProject\code\client\qt_wan_chat\release
```

Post-build `windeployqt` refreshed the local release package.

Follow-up no-op build:

```powershell
$env:PATH='D:\Qt\Tools\Ninja;D:\Qt\Tools\mingw1310_64\bin;D:\Qt\6.11.0\mingw_64\bin;' + $env:PATH
& 'D:\Qt\Tools\CMake_64\bin\cmake.exe' --build code\client\qt_wan_chat\build --parallel
```

Result:

```text
ninja: no work to do.
```

## Smoke Test

Command:

```powershell
code\client\qt_wan_chat\release\qt_wan_chat.exe --smoke-task-id=18439c7f-d91b-42a4-a5f3-2e90624587f8 --smoke-timeout-ms=10000
```

Result:

```text
Smoke test reached terminal state: succeeded | output_path=/home/liupengkun/VedioGenProject/code/server/wan_local_service/outputs/18439c7f-d91b-42a4-a5f3-2e90624587f8/result.mp4 | download_url=http://127.0.0.1:8000/api/results/18439c7f-d91b-42a4-a5f3-2e90624587f8/file
[mov,mp4,m4a,3gp,3g2,mj2 @ ...] moov atom not found
```

Smoke exit code: 0.

The `moov atom not found` line came from the Qt Multimedia/FFmpeg preview path and did not block task terminal-state verification.

## Manual UI Items Still Needed

- Start `code/client/qt_wan_chat/release/qt_wan_chat.exe` in a real Windows desktop session.
- Create a new task and confirm the Chat area keeps one progress card for that `task_id`.
- Confirm progress samples update status, stage, progress bar, percent/steps, elapsed time, estimated remaining time, and estimated completion time in place.
- Confirm completion or failure updates the same progress card to terminal state.
- Confirm Diagnostics still contains detailed progress transitions.
