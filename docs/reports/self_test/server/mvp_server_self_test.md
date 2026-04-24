# MVP Server Self Test

## 1. Environment Check

- Date: `2026-04-23` to `2026-04-24`
- Workspace: `/mnt/d/projects/videogenproject`
- Service root: `/mnt/d/projects/videogenproject/code/server/wan_local_service`
- OS: `Ubuntu 24.04.3 LTS`
- Python: `Python 3.12.3`
- Unit tests: `10 passed in 2.90s`
- Wan official repo: `code/server/wan_local_service/third_party/Wan2.2`
- Default model dir: `code/server/wan_local_service/third_party/Wan2.2-TI2V-5B`

Observed GPU facts in this session:

- escalated `nvidia-smi`: success
- GPU: `NVIDIA GeForce RTX 3090`
- Driver: `591.86`
- CUDA: `13.1`

Observed CUDA toolkit facts in the same session:

- `CUDA_HOME` is empty
- `nvcc` is not available on PATH
- `apt-cache policy nvidia-cuda-toolkit` shows Ubuntu package candidate `12.0.140~12.0.1-4build4`
- current chosen repair direction remains NVIDIA CUDA `13.x`, not the Ubuntu `12.0` package

## 1A. Current Workspace Recheck

- Date: `2026-04-24`
- Workspace: `/home/liupengkun/VedioGenProject`
- Service root: `/home/liupengkun/VedioGenProject/code/server/wan_local_service`

Command-level recheck in the current workspace:

```bash
cd code/server/wan_local_service
bash scripts/check_env.sh
```

Observed results:

- `configured_python_resolved=<missing>`
- `.venv` missing
- `third_party/Wan2.2` missing
- `third_party/Wan2.2-TI2V-5B` missing
- `nvcc` missing
- latest repeated `nvidia-smi` probe returned:

```text
Failed to initialize NVML: GPU access blocked by the operating system
Failed to properly shut down NVML: GPU access blocked by the operating system
```

- system `python3` lacks:
  - `fastapi`
  - `httpx`
  - `pytest`

Additional startup preflight check:

```bash
cd code/server/wan_local_service
bash scripts/run_service.sh foreground
```

Observed result:

```text
[error] Service Python not found: /home/liupengkun/VedioGenProject/code/server/wan_local_service/.venv/bin/python
[hint] Run: cd /home/liupengkun/VedioGenProject/code/server/wan_local_service && bash scripts/setup_wan22.sh
[hint] Check details with: cd /home/liupengkun/VedioGenProject/code/server/wan_local_service && bash scripts/check_env.sh
```

Conclusion for the current workspace snapshot:

- service runtime is not bootstrapped
- inference runtime is not bootstrapped
- GPU access is not currently reliable enough to mark as ready
- the earlier `/mnt/d/projects/videogenproject` validation should be treated as historical evidence, not as the current workspace state

## 2. `GET /healthz`

Request:

```bash
curl --noproxy '*' --fail --silent --show-error http://127.0.0.1:8000/healthz
```

Response:

```json
{"ok":true,"service":"wan-local-service"}
```

Result: passed

## 3. `POST /api/tasks`

Latest real request body:

```json
{
  "mode": "t2v",
  "prompt": "A cinematic cyberpunk street at night, slow camera push-in, rain reflections on the ground",
  "size": "1280*704"
}
```

Latest real response:

```json
{
  "task_id": "16daa568-fede-4da1-b20b-28f1138d09a1",
  "status": "pending",
  "prompt": "A cinematic cyberpunk street at night, slow camera push-in, rain reflections on the ground",
  "output_path": null,
  "error_message": null,
  "log_path": "/mnt/d/projects/videogenproject/code/server/wan_local_service/logs/16daa568-fede-4da1-b20b-28f1138d09a1.log",
  "create_time": "2026-04-23T14:49:25+00:00",
  "update_time": "2026-04-23T14:49:25+00:00"
}
```

Result: passed

## 4. `GET /api/tasks/{task_id}`

Request:

```bash
curl --noproxy '*' --fail --silent --show-error \
  http://127.0.0.1:8000/api/tasks/16daa568-fede-4da1-b20b-28f1138d09a1
```

Terminal response:

```json
{
  "task_id": "16daa568-fede-4da1-b20b-28f1138d09a1",
  "status": "failed",
  "prompt": "A cinematic cyberpunk street at night, slow camera push-in, rain reflections on the ground",
  "output_path": null,
  "error_message": "generate.py exited with code 1",
  "log_path": "/mnt/d/projects/videogenproject/code/server/wan_local_service/logs/16daa568-fede-4da1-b20b-28f1138d09a1.log",
  "create_time": "2026-04-23T14:49:25+00:00",
  "update_time": "2026-04-23T14:52:58+00:00",
  "output_exists": false
}
```

Result: passed

## 5. `GET /api/tasks`

Request:

```bash
curl --noproxy '*' --fail --silent --show-error \
  'http://127.0.0.1:8000/api/tasks?limit=5'
```

Response summary:

```json
{
  "items": [
    {
      "task_id": "16daa568-fede-4da1-b20b-28f1138d09a1",
      "status": "failed",
      "error_message": "generate.py exited with code 1"
    },
    {
      "task_id": "ab5bba2b-4b9a-4832-bd0c-bbfc7a6a5bc8",
      "status": "failed",
      "error_message": "generate.py exited with code 1"
    }
  ],
  "limit": 5
}
```

Result: passed

## 6. `GET /api/results`

Request:

```bash
curl --noproxy '*' --fail --silent --show-error \
  'http://127.0.0.1:8000/api/results?limit=10'
```

Response:

```json
{"items":[],"total":0,"limit":10}
```

Result: passed

## 7. Error Mapping And Null Semantics

Real HTTP checks:

- `unsupported_mode` -> `400`
- `validation_error` -> `422`
- `task_not_found` -> `404`

Unit tests cover:

- `invalid_size` -> `400`
- `service_not_ready` -> `503`
- `wan_execution_failed` -> `500`

Null semantics verified by real responses:

- `output_path`
  - `pending`: `null`
  - `failed`: `null`
- `error_message`
  - `pending`: `null`
  - `failed`: non-empty string
- `log_path`
  - allocated immediately on task creation
- `output_exists`
  - `false` while no `result.mp4` exists

## 8. Restart Recovery Semantics

Repository and API tests verified the exact restart recovery behavior:

- stale `pending` -> `failed` with `service restarted before task execution`
- stale `running` -> `failed` with `service restarted while task was running`

These exact strings are shared by code, README, protocol doc, and integration doc.

## 9. Real Inference Attempts

Model weights are present at the default path:

- `code/server/wan_local_service/third_party/Wan2.2-TI2V-5B`

Real sample progression in this session:

- `16a8b7fb-d24b-4731-8f3d-f489d02a3381`
  - first rerun after model download
  - log blocker: `ModuleNotFoundError: No module named 'einops'`
- `020ef017-f54e-4f41-8b30-4c3273906fa1`
  - rerun after installing `einops`
  - log blocker: `ModuleNotFoundError: No module named 'decord'`
- `b6bed8f5-4ce0-45ed-b906-2011a99205f9`
  - rerun after installing `decord`
  - log blocker: `ModuleNotFoundError: No module named 'librosa'`
- `ab5bba2b-4b9a-4832-bd0c-bbfc7a6a5bc8`
  - rerun after installing `librosa`
  - log blocker: `ModuleNotFoundError: No module named 'peft'`
- `16daa568-fede-4da1-b20b-28f1138d09a1`
  - rerun after installing `peft`
  - official TI2V path loaded T5, VAE, and all 3 model shards
  - generation reached the first sampling step
  - runtime blocker became `AssertionError` at `wan/modules/attention.py`
- `2026-04-24 direct generate.py validation`
  - bypassed Windows client and bypassed HTTP polling
  - reran the official `generate.py` entrypoint directly with the same `ti2v-5B` / `1280*704` / prompt combination
  - unprivileged sandbox first produced a false CUDA initialization blocker:
    - `RuntimeError: Found no NVIDIA driver on your system`
  - rerunning the same direct command outside the sandbox restored the real path
  - the direct run again loaded T5, VAE, and all 3 model shards
  - the direct run again reached `Generating video ...`
  - the direct run again failed on `wan/modules/attention.py` with `assert FLASH_ATTN_2_AVAILABLE`

Latest real log excerpt:

```text
[2026-04-23 22:52:47,031] INFO: Generating video ...
  0%|          | 0/50 [00:00<?, ?it/s]
  0%|          | 0/50 [00:01<?, ?it/s]
Traceback (most recent call last):
  File "/mnt/d/projects/videogenproject/code/server/wan_local_service/third_party/Wan2.2/wan/modules/attention.py", line 112, in flash_attention
    assert FLASH_ATTN_2_AVAILABLE
AssertionError
generate.py exit code: 1
```

Latest full task metadata:

- `task_id`: `16daa568-fede-4da1-b20b-28f1138d09a1`
- `log_path`: `/mnt/d/projects/videogenproject/code/server/wan_local_service/logs/16daa568-fede-4da1-b20b-28f1138d09a1.log`
- API `error_message`: `generate.py exited with code 1`

Real output status:

- `result.mp4` was not generated
- `/api/results` is still empty
- the 2026-04-24 direct `generate.py` rerun also did not produce a video file

## 10. Historical `flash_attn` Hard-Dependency Conclusion

Current code and runtime evidence now agree that `flash_attn` is a hard dependency for the official TI2V-5B path:

- `wan/modules/model.py` directly imports and calls `flash_attention(...)`
- `wan/modules/attention.py` uses `assert FLASH_ATTN_2_AVAILABLE` inside `flash_attention()` when FA3 is absent
- the TI2V path reached real sampling and failed exactly on that assertion
- the fallback implementation using `scaled_dot_product_attention` lives in `attention()`, but the TI2V main model path does not use that function

Conclusion:

- no `flash_attn` bypass should be attempted inside the official source tree for this MVP
- the correct next move is system-level CUDA toolkit repair

Status note on `2026-04-24`:

- this section is now historical context
- the current workspace later patched `flash_attention()` with an SDPA fallback and proved real video generation without compiling `flash_attn`
- therefore this report should not be treated as the latest default service path

## 11. Background Service Script Verification

This round added background service management to `scripts/run_service.sh`:

- `bash scripts/run_service.sh start`
- `bash scripts/run_service.sh status`
- `bash scripts/run_service.sh stop`

Observed process-level verification in the current session:

```bash
WAN_SERVICE_SKIP_HEALTHCHECK=1 bash scripts/run_service.sh start
WAN_SERVICE_SKIP_HEALTHCHECK=1 bash scripts/run_service.sh status
ps -fp $(cat storage/service.pid)
WAN_SERVICE_SKIP_HEALTHCHECK=1 bash scripts/run_service.sh stop
```

Observed result:

- background PID file was created at `storage/service.pid`
- runtime log path was reported as `logs/service.log`
- `status` returned `Service is running pid=...`
- `ps` confirmed the live `uvicorn app.main:app` process
- `stop` removed the background process successfully

Current session limitation:

- this agent sandbox does not allow a simple local listener self-check
- real control check:

```text
PermissionError: [Errno 1] Operation not permitted
```

- reproduction in the same session:

```bash
python3 -m http.server 8765
```

Conclusion:

- `run_service.sh` background lifecycle is implemented and process-level verified
- `/healthz` readiness under background mode still needs one more real WSL terminal verification outside the current restricted agent sandbox

## 12. Setup Script Findings

`bash scripts/setup_wan22.sh` now reflects the real service-side dependency chain:

- resolves default repo/model paths relative to `code/server/wan_local_service`
- installs non-`flash_attn` Wan requirements
- additionally installs runtime dependencies missing from the upstream main requirements:
  - `einops`
  - `decord`
  - `librosa`
  - `peft`

Earlier real `flash_attn` setup blocker was:

```text
OSError: CUDA_HOME environment variable is not set. Please set it to your CUDA install root.
```

Context from the same failure:

```text
flash_attn was requested, but nvcc was not found
```

After `cuda-toolkit-13-0` was installed in the real WSL environment, the blocker moved forward again. The latest root cause is no longer "missing nvcc", but WSL-wide OOM during local `flash_attn` compilation:

```text
2026-04-24T00:37:45 ... Out of memory: Killed process 3017 (cicc)
2026-04-24T01:46:34 ... Out of memory: Killed process 1119 (systemd)
2026-04-24T01:46:37 ... Out of memory: Killed process 6120 (cicc)
```

This explains the observed symptom that Codex exited and the WSL session looked crashed: once user-session `systemd` was OOM-killed, the interactive session was torn down as collateral damage.

## 12. Historical Blockers At That Stage

- official TI2V-5B sampling now confirms `flash_attn` is required at runtime
- local `flash_attn` compilation can now start in real WSL, but it still fails because the compile stage triggers global OOM
- the next real repair direction is to stop unnecessary resident services and retry with `WAN_FLASH_ATTN_MAX_JOBS=1`
