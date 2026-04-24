# MVP Windows WSL Integration

## Current Service Contract Status

- WSL service path: `code/server/wan_local_service`
- Main API contract: `docs/reports/integration/wan_local_service_api_contract.md`
- Verified WSL endpoints:
  - `GET /healthz`
  - `POST /api/tasks`
  - `GET /api/tasks/{task_id}`
  - `GET /api/tasks`
  - `GET /api/results`

Contract stability for Windows parallel development:

- task status enum remains `pending`, `running`, `succeeded`, `failed`
- `null` semantics for `output_path` and `error_message` are unchanged
- `GET /api/tasks/{task_id}` now also returns optional progress fields:
  - `status_message`
  - `progress_current`
  - `progress_total`
  - `progress_percent`
- restart recovery strings remain:
  - `service restarted before task execution`
  - `service restarted while task was running`

## Latest Windows Client Integration

Date: 2026-04-24

Service ownership note:

- the service was already running before this Windows client pass
- this client pass did not start, stop, or modify the service process

Windows client command that submitted the real task:

```powershell
qt_wan_chat.exe --smoke-prompt="A calm lake at sunrise, slow camera push-in, soft golden light" --smoke-timeout-ms=2700000
```

Observed:

- created task `18439c7f-d91b-42a4-a5f3-2e90624587f8`
- 45 minute smoke window expired while the task was still `running`
- the task later reached terminal success

Final task detail:

- `task_id`: `18439c7f-d91b-42a4-a5f3-2e90624587f8`
- `status`: `succeeded`
- `status_message`: `finished`
- `progress_current`: `50`
- `progress_total`: `50`
- `progress_percent`: `100`
- `output_path`: `/home/liupengkun/VedioGenProject/code/server/wan_local_service/outputs/18439c7f-d91b-42a4-a5f3-2e90624587f8/result.mp4`

Windows client reattach command:

```powershell
qt_wan_chat.exe --smoke-task-id=18439c7f-d91b-42a4-a5f3-2e90624587f8 --smoke-timeout-ms=10000
```

Observed client output:

```text
Smoke test reached terminal state: succeeded | output_path=/home/liupengkun/VedioGenProject/code/server/wan_local_service/outputs/18439c7f-d91b-42a4-a5f3-2e90624587f8/result.mp4
```

Current Windows-side caveat:

- `\\wsl$` access from the current Windows agent session still returns Access denied
- the client now skips `QDir.exists()` pre-check for WSL UNC paths and hands them directly to `explorer.exe`
- actual Explorer open success still needs verification in the real desktop session

## Default Path Status

The default model directory is now aligned across:

- `README_WAN_LOCAL_SERVICE.md`
- `.env.example`
- `app/config.py`
- `scripts/setup_wan22.sh`
- `scripts/run_service.sh`

Unified default model path:

- `code/server/wan_local_service/third_party/Wan2.2-TI2V-5B`

The model weights were actually downloaded to that default path in this session.

## Latest Real WSL Sample

Latest real sample task:

- `task_id`: `18439c7f-d91b-42a4-a5f3-2e90624587f8`
- terminal status: `succeeded`
- `status_message`: `finished`
- `progress_current`: `50`
- `progress_total`: `50`
- `progress_percent`: `100`
- `output_path`: `/home/liupengkun/VedioGenProject/code/server/wan_local_service/outputs/18439c7f-d91b-42a4-a5f3-2e90624587f8/result.mp4`

Earlier real attempts in the same path confirmed the chain progressed through these historical blockers before the SDPA fallback path succeeded:

- `einops` missing
- `decord` missing
- `librosa` missing
- `peft` missing
- TI2V sampling without `flash_attn` originally failed at `wan/modules/attention.py`

Current conclusion:

- Windows can continue against a stable API
- the local service can now produce real `result.mp4`
- generation time in the current SDPA fallback path can exceed 45 minutes for a 50-step 1280x704 task

## Windows Access Recommendation

Windows Qt 客户端默认使用：

- `http://127.0.0.1:8000`

适用前提：

- WSL localhost forwarding 正常工作

如果 Windows 侧访问 `http://127.0.0.1:8000` 失败，fallback 方案如下：

1. 在 WSL 中执行 `hostname -I`
2. 取其中的 WSL IPv4，例如 `172.xx.xx.xx`
3. 将客户端地址改为 `http://<wsl_ip>:8000`

如果 `127.0.0.1` 和 `<wsl_ip>` 都失败：

- 记录为联调 blocker
- 不在服务端引入 Windows 专属网络修复逻辑

联调期间，WSL 服务端建议优先以前台模式之外的后台方式启动：

```bash
cd code/server/wan_local_service
bash scripts/run_service.sh start
```

这样可以避免服务绑定在临时终端会话上，减少客户端轮询中途遇到 `Connection refused` 的概率。

## Path Semantics

服务端返回的 `output_path` 和 `log_path` 都是 WSL 绝对路径。

例如：

- `log_path=/mnt/d/projects/videogenproject/code/server/wan_local_service/logs/16daa568-fede-4da1-b20b-28f1138d09a1.log`
- `output_path` 在成功前固定为 `null`

Windows 侧若要打开目录，应由 Windows Codex 转换为：

- `\\wsl$\<distro>\...`

服务端职责仅限：

- 返回稳定字段
- 保持 `null` 语义稳定
- 返回可追踪的 WSL 路径

服务端不负责：

- `\\wsl$` 路径转换
- `explorer.exe` 打开目录

## API Notes For Client

- 客户端建议每 2 秒轮询一次 `GET /api/tasks/{task_id}`
- `failed` 任务请直接展示 `error_message`
- 最新服务端实现会优先把日志尾部的真实错误摘要折叠进 `error_message`，例如：
  - `AssertionError (generate.py exit code 1)`
  - `ModuleNotFoundError: No module named 'einops' (generate.py exit code 1)`
- 若需要更深错误，请允许用户打开 `log_path`
- 客户端需要继续正确处理失败和未完成状态：
  - `status=failed`
  - `output_path=null`
  - `output_exists=false`
- 客户端也需要展示成功状态的新增观测字段：
  - `status_message`
  - `progress_current`
  - `progress_total`
  - `progress_percent`

## Known Issues

- `flash_attn` 本地编译链仍是历史高风险路径，曾触发 WSL OOM；当前默认交付路径是 SDPA fallback
- SDPA fallback 可真实出片，但生成时间偏长；本轮 Windows 客户端任务约 46 分 45 秒后完成
- Windows Qt 客户端已完成真实编译、启动、创建任务、轮询终态和 `output_path` 获取
- 当前 Windows agent 会话对 `\\wsl$` 路径访问被拒绝，因此 Explorer 打开输出目录的成功路径仍需真实桌面复验

## Windows Qt Client Verification

Windows 侧客户端工程：

- `code/client/qt_wan_chat`

Real Windows build result:

- Qt6 Widgets client configured and built successfully with:
  - `D:\Qt\6.11.0\mingw_64`
  - `D:\Qt\Tools\CMake_64\bin\cmake.exe`
  - `D:\Qt\Tools\Ninja\ninja.exe`
  - `D:\Qt\Tools\mingw1310_64\bin\g++.exe`

Real Windows startup result:

- `qt_wan_chat.exe` launched successfully
- initial requests succeeded:
  - `GET /healthz`
  - `GET /api/tasks?limit=20`
  - `GET /api/results?limit=20`

Observed client diagnostics:

```text
[2026-04-23T22:20:35] Connected to service 'wan-local-service' at http://127.0.0.1:8000/
[2026-04-23T22:20:35] Loaded 7 task item(s).
[2026-04-23T22:20:35] Loaded 0 result item(s).
```

Real Windows smoke tasks:

- `2eea7312-9b99-41f9-8ec1-43d33474e824`
  - client observed `pending -> running`
  - later service query showed terminal `failed`
  - `error_message`: `generate.py exited with code 1`
- `141f1a6d-ba50-44ec-9dec-4662ec43ab7c`
  - client observed `pending -> running`
  - later polling hit `network_error`
  - error details: `Connection refused`

Observed client diagnostics for the second task:

```text
[2026-04-23T22:20:36] Task created: 141f1a6d-ba50-44ec-9dec-4662ec43ab7c status=pending
[2026-04-23T22:20:38] Task update: Task 141f1a6d-ba50-44ec-9dec-4662ec43ab7c -> running
[2026-04-23T22:21:14] Could not reach the local service. Check the URL and make sure FastAPI is running. [code=network_error]
```

Service-side evidence for the same task:

- log file:
  - `code/server/wan_local_service/logs/141f1a6d-ba50-44ec-9dec-4662ec43ab7c.log`
- observed tail:

```text
KeyboardInterrupt
generate.py exit code: -2
```
