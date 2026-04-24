# 2026-04-24 Client UI Simplification

## Scope

- Simplify the Windows Qt client visual style.
- Keep the existing client behavior unchanged.
- Do not modify, start, stop, or restart the service.

## UI Changes

- Added a light neutral app stylesheet for a ChatGPT-like desktop feel.
- Reduced default Qt chrome around the main chat experience.
- Changed the input area into a single composer container:
  - image `+` button on the left
  - prompt input in the middle
  - `Send` action on the right
- Updated chat messages to render as simple left/right message bubbles.
- Styled task cards with white background, subtle border, compact spacing, and pill labels.
- Unified table, form input, button, progress bar, and status bar styling.

## Verification

Build:

```powershell
cmake --build code\client\qt_wan_chat\build --parallel
```

Result:

```text
Linking CXX executable qt_wan_chat.exe
```

Whitespace check:

```powershell
git diff --check
```

Result:

```text
passed, with CRLF warnings only
```

Existing task monitor smoke:

```powershell
qt_wan_chat.exe --smoke-task-id=18439c7f-d91b-42a4-a5f3-2e90624587f8 --smoke-timeout-ms=10000
```

Result:

```text
Smoke test reached terminal state: succeeded | output_path=/home/liupengkun/VedioGenProject/code/server/wan_local_service/outputs/18439c7f-d91b-42a4-a5f3-2e90624587f8/result.mp4 | download_url=http://127.0.0.1:8000/api/results/18439c7f-d91b-42a4-a5f3-2e90624587f8/file
```

## Remaining Manual Check

- Need real desktop visual inspection for the simplified three-column layout, task cards, image preview, and composer spacing.
