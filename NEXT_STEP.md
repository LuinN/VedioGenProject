# NEXT_STEP

下一步最小可执行动作是：启动当前 WSL 服务端和 ComfyUI 后端，用已经适配单模型 `i2v` 契约的 Windows Qt 客户端重新做一次真实端到端联调，至少验证：

```text
Qt 选择本地图片 -> POST /api/tasks(mode=i2v, image, prompt, size) -> 轮询任务状态 -> 下载 result.mp4 -> Windows 本地播放
```

联调时必须记录：

- `GET /healthz` 的 `backend_ready` / `model_ready`
- `task_id`
- `backend_prompt_id`
- 服务端 `output_path`
- Windows 本地下载路径

如果继续留在 WSL 服务端侧，下一步最小收敛项是：修正 `run_comfyui.sh` / `run_service.sh` 的后台进程状态追踪，减少重复启动时的 `database lock` 和 `port already in use` 噪音。
