# NEXT_STEP

在具备 sudo 的真实 WSL 会话中直接运行 `bash code/server/wan_local_service/scripts/setup_wan22.sh`；该脚本现已自动尝试安装 `cuda-toolkit-13-0`，并处理 `.venv`、`setuptools<82`、`packaging/psutil/ninja` 和 `flash-attn==2.8.3` 安装。安装完成后再补一次直接 `generate.py` 验证，确认 `flash_attn` 已安装且不再阻塞首个采样 step。
