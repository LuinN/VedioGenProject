# NEXT_STEP

下一步优先做三件事：1. 由 WSL/服务端侧重启或更新当前正在运行的 FastAPI 进程，使其加载已合入的 `DELETE /api/tasks/{task_id}` 和 multipart `i2v` 协议；2. 在 Windows 客户端中选一个非关键的 `pending` / `succeeded` / `failed` 任务点击 Tasks `Delete`，确认服务端返回 `{deleted: true}`、任务从 `/api/tasks` 和 `/api/results` 消失、客户端清理任务缓存且不删除 Videos 页面 mp4；3. 在真实 Windows 桌面中从 `code/client/qt_wan_chat/release/qt_wan_chat.exe` 启动客户端，目视确认便携包 UI、视频播放、任务缩略图和 i2v 图片选择都正常。
