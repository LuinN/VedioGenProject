# README_WAN_LOCAL_SERVICE

## 概要

`wan_local_service` 是运行在 WSL / Linux 上的 FastAPI 本地服务，负责：

- 暴露 `GET /healthz`, `POST /api/tasks`, `GET /api/tasks/{task_id}`, `GET /api/tasks`, `GET /api/results`
- 把客户端提交的 `mode=t2v` 任务落盘到 SQLite
- 使用单 worker 串行调用官方 `Wan2.2/generate.py`
- 记录日志、结果文件路径和真实失败原因

当前 MVP 固定范围：

- 仅支持 API `mode=t2v`
- 内部固定调用 `Wan2.2-TI2V-5B`
- 单机串行执行
- 不支持多模型切换、Redis、Celery、Docker、鉴权

## 环境要求

- Ubuntu / WSL2
- Python 3.10+，当前脚本默认使用 `python3`
- NVIDIA GPU 环境，用于真实推理
- `git`
- `ffmpeg`
- `curl`

如果官方 Wan2.2 依赖在当前 `python3` 上安装失败，可以在 `.env` 中显式设置 `WAN_PYTHON_BIN` 指向兼容版本。

## Python 版本

检查方式：

```bash
python3 --version
```

如果你需要改成其它解释器，可在 `.env` 中设置：

```bash
WAN_PYTHON_BIN=/usr/bin/python3.11
```

## CUDA / 驱动检查

检查方式：

```bash
nvidia-smi
```

如果输出 `GPU access blocked by the operating system`，说明当前 WSL 尚未获得 GPU 访问权限，真实推理会失败。该错误需要记录到 `BLOCKERS.md` 和自测报告。

## 模型下载方式

服务脚本会 clone / update 官方 `Wan2.2` 仓库，但默认不会自动下载 `Wan2.2-TI2V-5B` 权重。

默认模型目录固定为：

- `code/server/wan_local_service/third_party/Wan2.2-TI2V-5B`

如果你在 `.env` 中覆盖 `WAN_MODEL_DIR`，相对路径也会按 `code/server/wan_local_service` 解析，而不是按你执行命令时的当前目录解析。

官方手动下载命令：

```bash
huggingface-cli download Wan-AI/Wan2.2-TI2V-5B --local-dir ./third_party/Wan2.2-TI2V-5B
```

或：

```bash
modelscope download Wan-AI/Wan2.2-TI2V-5B --local_dir ./third_party/Wan2.2-TI2V-5B
```

如果要让 `setup_wan22.sh` 自动下载，可以在 `.env` 中设置：

```bash
WAN_AUTO_DOWNLOAD_MODEL=1
WAN_MODEL_DOWNLOAD_PROVIDER=huggingface
```

## 启动服务

1. 首次准备环境：

```bash
cd code/server/wan_local_service
bash scripts/setup_wan22.sh
```

2. 启动服务：

```bash
cd code/server/wan_local_service
bash scripts/run_service.sh
```

如果要让服务脱离当前终端、便于 Windows 客户端长时间轮询，优先使用后台模式：

```bash
cd code/server/wan_local_service
bash scripts/run_service.sh start
bash scripts/run_service.sh status
```

停止后台服务：

```bash
cd code/server/wan_local_service
bash scripts/run_service.sh stop
```

后台模式会额外写出：

- 进程 PID：`storage/service.pid`
- 服务运行日志：`logs/service.log`

如果当前环境和本 agent 一样限制本地监听端口复验，可临时跳过 `/healthz` 就绪检查：

```bash
WAN_SERVICE_SKIP_HEALTHCHECK=1 bash scripts/run_service.sh start
```

真实 WSL 本机联调默认不要设置这个变量。

默认地址：

- 服务地址：`http://127.0.0.1:8000`
- OpenAPI：`http://127.0.0.1:8000/docs`

## 创建样例任务

样例脚本会：

- 检查 `/healthz`
- 创建一个真实任务
- 轮询到 `succeeded` 或 `failed`
- 打印 `task_id`
- 打印 `output_path` 或 `error_message`

执行方式：

```bash
cd code/server/wan_local_service
bash scripts/run_sample_t2v.sh
```

## 输出目录说明

- SQLite 数据库：`storage/tasks.db`
- 日志文件：`logs/<task_id>.log`
- 结果文件：`outputs/<task_id>/result.mp4`

返回语义固定如下：

- `output_path`
  - `pending` / `running` / `failed`: `null`
  - `succeeded`: 绝对路径字符串
- `error_message`
  - `pending` / `running` / `succeeded`: `null`
  - `failed`: 非空字符串，优先返回前置检查失败原因或日志尾部的真实错误摘要，并附带 `generate.py exit code`
- `log_path`
  - 任务创建成功后立即分配为绝对路径字符串

## 日志目录说明

每个任务使用独立日志文件：

- 文件路径：`logs/<task_id>.log`
- 内容包括：启动时间、任务 ID、执行命令、`generate.py` 标准输出、退出码

服务后台模式的运行日志独立写到：

- `logs/service.log`

## 服务重启恢复语义

服务启动时会扫描遗留 `pending` 和 `running` 任务，并统一改成 `failed`。

- 遗留 `pending`：
  - `status = failed`
  - `error_message = "service restarted before task execution"`
- 遗留 `running`：
  - `status = failed`
  - `error_message = "service restarted while task was running"`

以上两条英文文案在代码、协议文档、README、自测报告和集成文档中保持完全一致。

## 协议文档

客户端并行开发请以这份文档为准：

- `docs/reports/integration/wan_local_service_api_contract.md`

FastAPI 自动文档只作为机器可读补充，不替代主协议文档。

## 官方依赖链说明

当前官方 `wan/__init__.py` 会无条件导入：

- `WanS2V`
- `WanAnimate`

这意味着即使当前服务只跑 `mode=t2v`，也会在模块导入阶段触发额外依赖链。当前真实验证过的缺口包括：

- `einops`
- `decord`
- `librosa`
- `peft`

因此当前 `setup_wan22.sh` 会在安装官方主 `requirements.txt` 之后，再补装上述运行时依赖。

当前还已通过真实任务确认：

- 官方 TI2V-5B 主路径会进入 `wan/modules/model.py -> flash_attention()`
- 在没有 `flash_attn` 时，`wan/modules/attention.py` 会触发 `assert FLASH_ATTN_2_AVAILABLE`

因此对于当前官方 TI2V-5B 路径，`flash_attn` 应视为硬依赖。

## 常见问题排查

1. `nvidia-smi` 失败

- 真实错误示例：`GPU access blocked by the operating system`
- 影响：无法完成真实推理
- 处理：先修复 WSL GPU 访问，再重跑 `run_sample_t2v.sh`

2. `generate.py not found`

- 说明：官方仓库尚未 clone 完成
- 处理：重跑 `bash scripts/setup_wan22.sh`

3. `model directory not found`

- 说明：权重尚未下载到 `third_party/Wan2.2-TI2V-5B`
- 处理：按上方官方命令下载模型

4. `output file was not generated`

- 说明：`generate.py` 执行后没有生成 `result.mp4`
- 处理：查看任务 `log_path`，确认官方脚本真实报错

5. 官方依赖安装失败

- 说明：常见于 Torch / flash-attn / Python 版本不匹配
- 处理：记录真实报错，改用兼容 Python，并重新执行 `setup_wan22.sh`

6. `ModuleNotFoundError: No module named 'einops'`、`decord`、`librosa` 或 `peft`

- 说明：当前上游主 `requirements.txt` 未覆盖全部运行时依赖，但官方入口模块链路会导入它们
- 处理：重跑 `bash scripts/setup_wan22.sh`；当前脚本会额外安装 `einops`、`decord`、`librosa` 和 `peft`

7. `flash_attn` 安装失败，提示 `CUDA_HOME environment variable is not set` 或 `nvcc was not found`

- 说明：当前环境缺少 CUDA toolkit 编译链，无法在本机编译 `flash_attn`
- 处理：优先安装和当前 `torch 2.11.0+cu130` 更贴近的 `cuda-toolkit-13-0`，然后设置 `CUDA_HOME` 后重跑 `bash scripts/setup_wan22.sh`
- 当前脚本已内置：
  - `nvcc` 缺失时自动尝试 `sudo apt-get install -y cuda-toolkit-13-0`
  - `.venv` 自动创建和激活
  - `setuptools<82` 固定，用于避免 `torch 2.11.0 requires setuptools<82` 冲突
  - `packaging`、`psutil`、`ninja` 预装
  - `flash-attn==2.8.3 --no-build-isolation` 固定安装
- 因此正常情况下不需要手动逐条输入 `python -m pip install ...`
- 推荐命令：

```bash
sudo apt-get update
sudo apt-get install -y cuda-toolkit-13-0
export CUDA_HOME=/usr/local/cuda-13.0
export PATH="${CUDA_HOME}/bin:${PATH}"
bash scripts/setup_wan22.sh
```

8. 真实任务日志出现 `AssertionError`，栈位于 `wan/modules/attention.py` 的 `assert FLASH_ATTN_2_AVAILABLE`

- 说明：当前官方 TI2V-5B 主路径已经进入真实采样阶段，但由于 `flash_attn` 缺失而中断
- 处理：不要绕过官方模型逻辑；先修复 `flash_attn` 安装链，再重跑 `bash scripts/run_sample_t2v.sh`

9. Windows 客户端轮询期间服务随终端退出

- 说明：如果服务以前台模式跑在临时 shell 里，关闭该终端或收到中断后，客户端轮询会得到 `Connection refused`
- 处理：联调期间改用 `bash scripts/run_service.sh start`，并用 `bash scripts/run_service.sh status` / `stop` 管理后台进程
