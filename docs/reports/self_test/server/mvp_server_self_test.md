# MVP Server Self Test

## Scope

日期：`2026-05-04`

本轮目标：

- 启动 `ComfyUI + Wan2.2 I2V-A14B`
- 通过 `FastAPI -> /api/tasks -> run_sample_i2v.sh` 完成一条真实 `832*480` 出片验收

本报告只记录这轮在当前工作区里真实完成的验证。

## Workspace Snapshot

- Workspace：`/home/liupengkun/VedioGenProject`
- Service root：`/home/liupengkun/VedioGenProject/code/server/wan_local_service`
- GPU：`NVIDIA GeForce RTX 3090`
- 测试输入图：
  - `code/server/wan_local_service/outputs/b46f4189-c915-4d2d-a3d1-8f7bd584bbc6/input_image.jpeg`

当前 `third_party` / runtime 真实状态：

- `third_party/ComfyUI` 存在
- `.comfyui-venv` 存在
- 4 个 14B 必需模型文件存在：
  - `wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors`
  - `wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors`
  - `umt5_xxl_fp8_e4m3fn_scaled.safetensors`
  - `wan_2.1_vae.safetensors`

## Code-Level Fixes Completed In This Turn

### 1. 修复环境检查误指向系统 Python

- `app.config` 原先会把 `.venv/bin/python` / `.comfyui-venv/bin/python` 跟着符号链接 `resolve()` 到 `/usr/bin/python3.12`
- 结果是 `check_env.sh` 和 `app.env_report` 在检查系统 Python，而不是项目 venv
- 现已修正为保留项目 venv 的绝对路径

### 2. 修复 ComfyUI 工作流到 API prompt 的 `KSamplerAdvanced` 参数映射

首次真实任务曾失败于：

- `failure_code=backend_validation_error`
- `/prompt HTTP 400`
- 原因是旧模板里的 `widgets_values` 排列与当前 ComfyUI `KSamplerAdvanced` 的 `object_info` 顺序不再一致

现已改为：

- 对 `KSamplerAdvanced` 使用显式语义映射
- 不再依赖当前版本 `input_order` 与旧模板前端导出顺序刚好一致

### 3. 修复 `run_sample_i2v.sh` 的进度字段解析

- 原先脚本在空字段场景下会把 `status_message` / `backend_prompt_id` / 进度数字串位
- 现已改为按行读取字段，避免 `tab` 分隔在空值场景下错位

## Automated Verification

### Pytest

命令：

```bash
cd code/server/wan_local_service
./.venv/bin/python -m pytest -q tests
```

结果：

```text
20 passed in 0.92s
```

### Targeted Workflow Regression

命令：

```bash
cd code/server/wan_local_service
./.venv/bin/python -m pytest -q tests/test_comfyui_workflow.py tests/test_comfyui_integration.py tests/test_api.py
```

结果：

```text
12 passed in 0.62s
```

### Shell / Diff Checks

命令：

```bash
bash -n code/server/wan_local_service/scripts/run_sample_i2v.sh
git diff --check
```

结果：

```text
ok
```

## Environment Report

命令：

```bash
cd code/server/wan_local_service
bash scripts/check_env.sh
```

在真实可运行的非沙箱 WSL 环境中，结果为：

- `service_ready=yes`
- `backend_ready=yes`
- `model_ready=yes`

关键细节：

- `service_python -> .../.venv/bin/python`
- `comfyui_python -> .../.comfyui-venv/bin/python`
- 4 个 14B 文件 -> 全部 `ok`
- `torch_cuda -> cuda_available=True`
- `comfyui_object_info -> ok`

## Real Runtime Acceptance

### Health Check

真实返回：

```json
{
  "ok": true,
  "service": "wan-local-service",
  "backend": "comfyui_native",
  "backend_ready": true,
  "model_ready": true,
  "backend_reason": null
}
```

### Sample Command

真实执行命令：

```bash
cd /home/liupengkun/VedioGenProject
bash code/server/wan_local_service/scripts/run_comfyui.sh start
bash code/server/wan_local_service/scripts/run_service.sh start
WAN_SAMPLE_IMAGE=/home/liupengkun/VedioGenProject/code/server/wan_local_service/outputs/b46f4189-c915-4d2d-a3d1-8f7bd584bbc6/input_image.jpeg \
WAN_SAMPLE_SIZE='832*480' \
bash code/server/wan_local_service/scripts/run_sample_i2v.sh
```

### Successful Task

- `task_id`：`d69cc58c-df85-4fcd-86f3-849072c0e8ec`
- `backend_prompt_id`：`14d77c4b-f272-4ca2-8eff-9715b48d9a0a`
- `mode`：`i2v`
- `size`：`832*480`
- `prompt`：`A determined fantasy warrior stands still while the camera slowly moves closer, cinematic lighting, smooth motion`
- `input_image_path`：
  - `/home/liupengkun/VedioGenProject/code/server/wan_local_service/outputs/d69cc58c-df85-4fcd-86f3-849072c0e8ec/input_image.jpeg`
- `output_path`：
  - `/home/liupengkun/VedioGenProject/code/server/wan_local_service/outputs/d69cc58c-df85-4fcd-86f3-849072c0e8ec/result.mp4`
- `download_url`：
  - `http://127.0.0.1:8000/api/results/d69cc58c-df85-4fcd-86f3-849072c0e8ec/file`
- `create_time`：`2026-05-04T10:54:53+00:00`
- `update_time`：`2026-05-04T11:05:01+00:00`
- 任务墙钟时长约：`10m08s`
- ComfyUI 日志记录总执行时长：
  - `Prompt executed in 00:10:48`

### Output File Facts

```text
result.mp4 size = 474557 bytes
```

`ffprobe` 结果：

```json
{
  "streams": [
    {
      "width": 832,
      "height": 480,
      "r_frame_rate": "16/1",
      "duration": "3.062500",
      "nb_frames": "49"
    }
  ]
}
```

### Task Progress Evidence

任务日志关键片段：

```text
uploading image
prompt queued prompt_id=14d77c4b-f272-4ca2-8eff-9715b48d9a0a
sampling 1/10 (10%)
...
sampling 10/10 (100%)
sampling 1/10 (10%)
...
sampling 10/10 (100%)
saving video
copied result to .../outputs/d69cc58c-df85-4fcd-86f3-849072c0e8ec/result.mp4
```

ComfyUI 日志关键片段：

```text
Device: cuda:0 NVIDIA GeForce RTX 3090 : cudaMallocAsync
loaded completely; 19085.49 MB usable, 13631.42 MB loaded, full load: True
Prompt executed in 00:10:48
```

## Real Conclusion

本轮真实结论是：

- `Wan2.2 I2V-A14B` 已经在这台 `RTX 3090 24GB` 机器上跑出第一条真实视频
- 服务端从 `FastAPI -> ComfyUI -> result.mp4` 的 14B 主链路已经闭环
- 当前剩余问题已经不是“能不能跑”，而是：
  - Windows 客户端契约同步
  - ComfyUI 后台进程状态收敛
