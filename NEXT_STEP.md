# NEXT_STEP

下一步优先做三件事：1. 在真实 Windows 桌面会话中目视检查新版两栏 UI，确认顶部工具栏、Configuration/Videos/Diagnostics 弹窗、任务结果截图卡片、Tasks 删除按钮、Videos 删除按钮和输入 composer 没有遮挡或错位；2. 人工点选一个非关键历史任务验证 Tasks 删除只隐藏任务并清本地任务缓存、不删除 Videos 页面 mp4，再在 Videos 页面单独验证删除视频文件和索引；3. 由 WSL/服务端侧重启或更新当前正在运行的 FastAPI 进程，使其加载已合入的 multipart `i2v` 协议，然后重新运行 Windows 客户端 `qt_wan_chat.exe --smoke-prompt=... --smoke-image=... --smoke-timeout-ms=10000`，确认 `mode=i2v` 能成功创建任务、写入本地 `metadata.json`，随后再补一条真实 GPU `i2v` 长任务闭环。
