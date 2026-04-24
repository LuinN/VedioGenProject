# NEXT_STEP

下一步优先做三件事：1. 在真实 Windows 桌面中从 `code/client/qt_wan_chat/release/qt_wan_chat.exe` 启动客户端，创建一个新任务，目视确认 Wan Chat 中同一个任务进度卡片持续更新、不会每次进度变化追加 System 对话，并确认 ETA 文案随进度变化；2. 由 WSL/服务端侧重启或更新当前正在运行的 FastAPI 进程，使其加载已合入的 `DELETE /api/tasks/{task_id}` 和 multipart `i2v` 协议；3. 在 Windows 客户端中选一个非关键的 `pending` / `succeeded` / `failed` 任务点击 Tasks `Delete`，确认服务端返回 `{deleted: true}`、任务从 `/api/tasks` 和 `/api/results` 消失、客户端清理任务缓存且不删除 Videos 页面 mp4。
