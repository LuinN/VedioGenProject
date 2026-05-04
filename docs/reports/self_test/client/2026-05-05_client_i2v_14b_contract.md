# Windows Qt Client Self Test - I2V 14B Contract

Date: 2026-05-05

## Scope

This Windows-side pass updated only the Qt client and project status docs.

The client now follows the current WSL service contract:

- no `/api/capabilities` request
- no JSON task creation path
- no `mode=t2v` submission path
- task creation uses multipart `mode=i2v`, `prompt`, `size`, and `image`
- supported sizes are `832*480` and `480*832`
- health parsing includes `backend_ready`, `model_ready`, and `backend_reason`
- task parsing includes `backend`, `backend_prompt_id`, and `failure_code`

## Static Checks

Old contract search:

```powershell
rg -n 'profile|Capability|fetchCapabilities|capabilitiesFetched|selectedProfileId|refreshProfileOptions|allowedSizesForProfile|supportedModesForProfile|isProfileAvailable|createTask\(|m_profileCombo|kLegacy|t2v|/api/capabilities' code\client\qt_wan_chat\src
```

Result: no matches.

New contract search:

```powershell
rg -n 'createImageTask\(|sendMultipartCreateTask\(|backend_ready|model_ready|backend_reason|backend_prompt_id|failure_code|QStringLiteral\("i2v"\)' code\client\qt_wan_chat\src
```

Result: expected matches in `ApiClient`, `MainWindow`, and `TaskModels`.

Whitespace check:

```powershell
git diff --check
```

Result: passed. Git reported only existing line-ending normalization warnings.

## Build Verification

The sandboxed build process repeatedly timed out while creating `.ninja_lock`. Running the same build with local Windows toolchain access completed successfully.

Object compile:

```powershell
$env:PATH='D:\Qt\Tools\Ninja;D:\Qt\Tools\mingw1310_64\bin;D:\Qt\6.11.0\mingw_64\bin;' + $env:PATH
& 'D:\Qt\Tools\Ninja\ninja.exe' -C 'code\client\qt_wan_chat\build' -v CMakeFiles/qt_wan_chat.dir/src/main.cpp.obj
& 'D:\Qt\Tools\Ninja\ninja.exe' -C 'code\client\qt_wan_chat\build' -v CMakeFiles/qt_wan_chat.dir/src/ApiClient.cpp.obj CMakeFiles/qt_wan_chat.dir/src/MainWindow.cpp.obj
```

Result: passed.

Full target:

```powershell
$env:PATH='D:\Qt\Tools\Ninja;D:\Qt\Tools\mingw1310_64\bin;D:\Qt\6.11.0\mingw_64\bin;' + $env:PATH
& 'D:\Qt\Tools\Ninja\ninja.exe' -C 'code\client\qt_wan_chat\build' -v qt_wan_chat
```

Result:

- `qt_wan_chat.exe` linked successfully
- `windeployqt` completed
- release package refreshed at `code/client/qt_wan_chat/release/`

Observed non-blocking warning:

- `windeployqt`: `Cannot find any version of the dxcompiler.dll and dxil.dll.`

## Not Verified

This pass did not run a real WSL service task from the Windows client. The next verification still needs a running WSL FastAPI service and ComfyUI backend, then a real image-to-video task from the Qt client.
