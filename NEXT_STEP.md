# NEXT_STEP

下一步优先做三件事：1. 在真实 Windows 桌面会话中目视检查新版两栏 UI，确认顶部工具栏、Configuration/Videos/Diagnostics 弹窗、任务结果截图卡片、Tasks 删除按钮、Videos 删除按钮和输入 composer 没有遮挡或错位；2. Windows 客户端把当前 Tasks 的本地隐藏式删除切到服务端 `DELETE /api/tasks/{task_id}`，先覆盖 `pending/succeeded/failed` 任务，并继续保持 Videos 页面单独删除本地 mp4 的边界；3. 由 WSL/服务端侧重启或更新当前正在运行的 FastAPI 进程，使其加载已合入的 multipart `i2v` 协议，然后重新运行 Windows 客户端 `qt_wan_chat.exe --smoke-prompt=... --smoke-image=... --smoke-timeout-ms=10000`，确认 `mode=i2v` 能成功创建任务、写入本地 `metadata.json`，随后再补一条真实 GPU `i2v` 长任务闭环。
