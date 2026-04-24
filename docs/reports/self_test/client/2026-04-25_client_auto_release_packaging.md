# 2026-04-25 Client Auto Release Packaging

## Scope

Add automatic Windows packaging for the Qt client after each successful build.

The package is a Qt portable directory, not a single-file executable:

```text
code/client/qt_wan_chat/release/
```

## Changes

- Added `code/client/qt_wan_chat/tools/package_windows.ps1`.
- Added a Windows-only CMake `POST_BUILD` command for `qt_wan_chat`.
- The post-build step:
  - clears and recreates `code/client/qt_wan_chat/release/`
  - copies the freshly built `qt_wan_chat.exe`
  - runs `windeployqt --compiler-runtime --force --dir <release> <release\qt_wan_chat.exe>`
  - fails the build if packaging fails
- Added `release/` to `code/client/qt_wan_chat/.gitignore`.

The script validates that it only deletes the fixed client release directory.

## Verification

Build command:

```powershell
$env:PATH='D:\Qt\Tools\Ninja;D:\Qt\Tools\mingw1310_64\bin;D:\Qt\6.11.0\mingw_64\bin;' + $env:PATH
cmake --build code\client\qt_wan_chat\build --parallel
```

Result:

```text
Linking CXX executable qt_wan_chat.exe
Packaged qt_wan_chat release:
  exe: D:\Projects\VideoGenProject\code\client\qt_wan_chat\release\qt_wan_chat.exe
  dir: D:\Projects\VideoGenProject\code\client\qt_wan_chat\release
```

Release checks:

```text
code/client/qt_wan_chat/release/qt_wan_chat.exe                 present
code/client/qt_wan_chat/release/Qt6Core.dll                     present
code/client/qt_wan_chat/release/Qt6Multimedia.dll               present
code/client/qt_wan_chat/release/platforms/qwindows.dll          present
code/client/qt_wan_chat/release/multimedia/ffmpegmediaplugin.dll present
```

Smoke from release:

```powershell
code\client\qt_wan_chat\release\qt_wan_chat.exe --smoke-task-id=18439c7f-d91b-42a4-a5f3-2e90624587f8 --smoke-timeout-ms=10000
```

Result:

```text
Smoke test reached terminal state: succeeded | output_path=/home/liupengkun/VedioGenProject/code/server/wan_local_service/outputs/18439c7f-d91b-42a4-a5f3-2e90624587f8/result.mp4 | download_url=http://127.0.0.1:8000/api/results/18439c7f-d91b-42a4-a5f3-2e90624587f8/file
```

## Notes

- `windeployqt` emitted a non-fatal warning:

```text
Warning: Cannot find any version of the dxcompiler.dll and dxil.dll.
```

- Packaging and release smoke still succeeded.
- No service process was started, stopped, or restarted.
