# NEXT_STEP

下一步优先做三件事：1. 由 WSL/服务端侧重启或更新当前正在运行的 FastAPI 进程，使其加载已合入的 `DELETE /api/tasks/{task_id}` 和 multipart `i2v` 协议；2. 在 Windows 客户端中选一个非关键的 `pending` / `succeeded` / `failed` 任务点击 Tasks `Delete`，确认服务端返回 `{deleted: true}`、任务从 `/api/tasks` 和 `/api/results` 消失、客户端清理任务缓存且不删除 Videos 页面 mp4；3. 重新运行 Windows 客户端 `qt_wan_chat.exe --smoke-prompt=... --smoke-image=... --smoke-timeout-ms=10000`，确认 `mode=i2v` 能成功创建任务、写入本地 `metadata.json`，随后再补一条真实 GPU `i2v` 长任务闭环。
