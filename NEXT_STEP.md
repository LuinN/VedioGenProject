# NEXT_STEP

下一步最小可执行动作是：由 Windows 侧客户端同步当前服务端的单模型 `i2v` 契约，停止依赖 `/api/capabilities` 和 `t2v`，然后在 Windows 原生 Qt 工具链里重新做一次客户端到 WSL 服务端的真实联调，至少验证：

```text
Qt -> POST /api/tasks(mode=i2v, image, prompt, size) -> 轮询任务状态 -> 下载 result.mp4
```

如果继续留在 WSL 服务端侧，下一步最小收敛项是：修正 `run_comfyui.sh` / `run_service.sh` 的后台进程状态追踪，减少重复启动时的 `database lock` 和 `port already in use` 噪音。
