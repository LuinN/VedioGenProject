# NEXT_STEP

先在真实 WSL 会话中用 `bash code/server/wan_local_service/scripts/run_service.sh start` 托管后台服务，再从 Windows Qt 客户端发起一次真实任务，验证客户端能拿到 `task_id`、长任务轮询结果、终态 `status=succeeded` 和最终 `output_path`。如果后续要恢复高性能路径，再执行 `cd code/server/wan_local_service && WAN_FLASH_ATTN_CUDA_ARCHS=80 WAN_FLASH_ATTN_MAX_JOBS=1 bash scripts/build_flash_attn_resumable.sh resume`。
