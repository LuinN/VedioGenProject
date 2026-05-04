# MVP Windows WSL Integration

## Current Cross-Side Status

日期：`2026-05-04`

当前 WSL 服务端已经真实跑通：

- `ComfyUI` 原生后端
- `Wan2.2 I2V-A14B`
- 单模型、单能力服务

当前服务契约文件：

- [wan_local_service_api_contract.md](/home/liupengkun/VedioGenProject/docs/reports/integration/wan_local_service_api_contract.md:1)

## What Is Now Proven On The WSL Side

这轮 WSL 侧已经完成真实验证：

- `ComfyUI` 源码已落地
- `.comfyui-venv` 已落地
- 4 个 14B 模型文件已下载完成
- `check_env.sh` 在真实可运行的非沙箱 WSL 环境中为：
  - `service_ready=yes`
  - `backend_ready=yes`
  - `model_ready=yes`
- 成功跑出一条真实视频：
  - `task_id=d69cc58c-df85-4fcd-86f3-849072c0e8ec`
  - `backend_prompt_id=14d77c4b-f272-4ca2-8eff-9715b48d9a0a`
  - `result.mp4` 已落到：
    - `code/server/wan_local_service/outputs/d69cc58c-df85-4fcd-86f3-849072c0e8ec/result.mp4`

这意味着 WSL 服务端不再停留在“代码主线已切换”，而是已经具备真实 14B 出片能力。

## Current Service Contract

服务端当前已经不再对外承诺：

- `mode=t2v`
- `/api/capabilities`
- 多 profile
- `TI2V-5B` 主线兼容

当前固定为：

- `POST /api/tasks`
  - `multipart/form-data`
  - `mode=i2v`
  - `size=832*480` 或 `480*832`
- `GET /healthz`
  - 返回 `backend/backend_ready/model_ready/backend_reason`
- 任务对象
  - 返回 `backend`
  - 返回 `backend_prompt_id`
  - 返回 `failure_code`

## Remaining Client/Server Drift

当前最可能的接口漂移点：

- 客户端仍请求 `/api/capabilities`
- 客户端仍允许 `t2v`
- 客户端仍把服务端当成多模型或多 profile 服务

因此当前联调结论是：

- WSL 服务端已经真实跑通 14B
- Windows 客户端尚未同步到新契约
- Win/WSL 最后一段阻塞已经从“服务端能不能跑”收敛为“客户端协议要不要跟上”

## Next Integration Gap

下一次 Win/WSL 联调最小目标应当是：

1. Windows 客户端只提交 `i2v`
2. 不再请求 `/api/capabilities`
3. 使用真实图片完成：

```text
Qt -> POST /api/tasks -> 轮询状态 -> 下载 result.mp4
```

在这一步完成前，仍不能把“Windows 客户端到 WSL 服务端”的整条最终用户链路标记为已完全恢复。
