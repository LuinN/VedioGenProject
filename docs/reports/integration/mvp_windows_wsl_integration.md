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
- restart recovery strings remain:
  - `service restarted before task execution`
  - `service restarted while task was running`

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

- `task_id`: `16daa568-fede-4da1-b20b-28f1138d09a1`
- terminal status: `failed`
- API `error_message`: `generate.py exited with code 1`
- log-path blocker: `AssertionError` at `wan/modules/attention.py` because `FLASH_ATTN_2_AVAILABLE` is false

Earlier real attempts in the same path also confirmed the chain progressed through:

- `einops` missing
- `decord` missing
- `librosa` missing
- `peft` missing
- latest failure at real TI2V sampling without `flash_attn`

This means Windows can continue against a stable API while WSL keeps advancing the local runtime dependency chain.

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
- 由于当前真实链路仍未产出视频，客户端需要正确处理：
  - `status=failed`
  - `output_path=null`
  - `output_exists=false`

## Known Issues

- 模型权重已到位，服务端真实任务已进入 TI2V 采样阶段，但当前在无 `flash_attn` 时会失败于：
  - `wan/modules/attention.py`
  - `assert FLASH_ATTN_2_AVAILABLE`
- `setup_wan22.sh` 的 `flash_attn` 安装仍会失败，真实报错为：
  - `CUDA_HOME environment variable is not set`
  - `nvcc was not found`
- 当前 WSL 侧已经确认：对官方 TI2V-5B 主路径，不应让 Windows 客户端尝试任何无 `flash_attn` 特判或协议分支
- Windows Qt 客户端已完成真实编译、启动、创建任务与轮询到 `running`
- 服务端已新增 `run_service.sh start|status|stop` 后台模式，作为掉线问题的直接缓解措施
- 掉线问题仍需在真实 Windows -> WSL 联调中复验：
  - 当前 agent sandbox 无法完成后台服务 `/healthz` ready check 的端口绑定复验
  - 当前 Windows agent 会话对 `\\wsl$` 路径访问被拒绝

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
