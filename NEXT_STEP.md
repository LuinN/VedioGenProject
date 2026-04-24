# NEXT_STEP

下一步优先做两件事：1. Windows 客户端接入 `multipart/form-data` 的 `i2v` 提交，支持选择本地图片并上传到 `POST /api/tasks`；2. 在真实 WSL GPU 环境里补跑一条完整 `mode=i2v` 任务，确认 `input_image_path`、`--image`、进度轮询和最终 `result.mp4` 全部闭环。
