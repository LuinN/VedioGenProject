# NEXT_STEP

服务端下载协议已就绪；下一步只做 Windows 客户端对接：在 `code\client\qt_wan_chat\build\qt_wan_chat.exe` 中消费 `download_url`，对 `GET /api/results/{task_id}/file` 发起下载，并把返回的 `mp4` 保存到用户选择的 Windows 本地目录。
