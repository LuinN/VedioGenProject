# 2026-04-24 SDPA fallback 真实出片记录

## 目标

- 在 `flash_attn` 仍未安装完成的前提下，验证当前 workspace 的 Wan2.2 运行态 fallback 能否把真实任务完整跑到视频文件落盘

## 本轮关键改动

- `code/server/wan_local_service/third_party/Wan2.2/wan/modules/attention.py`
  - 给 `flash_attention()` 补上 `scaled_dot_product_attention` fallback
- `code/server/wan_local_service/app/wan_runner.py`
  - 默认允许 `WAN_ALLOW_SDPA_FALLBACK=1` 路径，不再把缺少 `flash_attn` 作为运行前硬阻塞
- `code/server/wan_local_service/app/env_report.py`
  - 在 fallback 模式下把 `flash_attn` 缺失降为 `info`

## 环境验证

真实 WSL 环境执行：

```bash
bash code/server/wan_local_service/scripts/check_env.sh
```

结果：

- `service_ready=yes`
- `inference_ready=yes`
- `flash_attn_build_ready=no`
- `python_import:flash_attn` 仍缺失，但当前只记为 `info`
- `torch_cuda` 为 `cuda_available=True`

## 真实任务

- 服务托管方式：`bash code/server/wan_local_service/scripts/run_service.sh foreground`
- smoke 命令：`bash code/server/wan_local_service/scripts/run_sample_t2v.sh`
- task_id：`57783f7a-5915-49f2-b105-8cd15dd26fbe`
- log_path：`/home/liupengkun/VedioGenProject/code/server/wan_local_service/logs/57783f7a-5915-49f2-b105-8cd15dd26fbe.log`

## 真实进展

- `/healthz` 成功
- `POST /api/tasks` 成功
- 任务状态真实从 `pending` 进入 `running`
- `run_sample_t2v.sh` 的默认 6 分钟轮询窗口结束时，任务仍在 `running`
- 继续观察任务日志后，确认本次任务最终完成并生成输出文件

## GPU 证据

真实 `nvidia-smi` 观测到：

- 进程：`/python3.12`
- 显存占用：约 `23.5 GiB / 24 GiB`
- `GPU-Util=100%`

说明：

- 当前链路已经真实进入 Wan2.2 的 GPU 生成阶段
- 当前没有再停在 `flash_attn` 导入断言

## 输出结果

- `output_path`：
  - `/home/liupengkun/VedioGenProject/code/server/wan_local_service/outputs/57783f7a-5915-49f2-b105-8cd15dd26fbe/result.mp4`
- 日志尾部：

```text
[2026-04-24 11:54:45,831] INFO: Saving generated video to .../result.mp4
[2026-04-24 11:54:48,035] INFO: Finished.
generate.py exit code: 0
```

- `ffprobe` 结果：
  - codec: `h264`
  - resolution: `1280x704`
  - duration: `5.041667s`
  - frames: `121`
  - size: `11051605` bytes

## 当前结论

- SDPA fallback 已经把“缺少 `flash_attn` 就完全不能跑”的阻塞解除
- 当前 workspace 已经在真实 WSL 环境里跑出了视频文件
- 默认 `run_sample_t2v.sh` 的 6 分钟等待窗口不足以覆盖当前 1280x704 样例的真实生成时长
- 这次完整样例总耗时约 31 分钟，其中采样阶段约 16 分 36 秒
- 后续若要提升速度，应继续完成 `flash_attn` 的高性能编译链
