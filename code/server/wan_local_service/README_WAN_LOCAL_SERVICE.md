# README_WAN_LOCAL_SERVICE

## 概要

`wan_local_service` 是运行在 WSL / Linux 上的 FastAPI 本地服务，负责：

- 暴露 `GET /healthz`, `POST /api/tasks`, `GET /api/tasks/{task_id}`, `GET /api/tasks`, `GET /api/results`, `GET /api/results/{task_id}/file`
- 把客户端提交的 `mode=t2v` 任务落盘到 SQLite
- 使用单 worker 串行调用官方 `Wan2.2/generate.py`
- 记录日志、结果文件路径和真实失败原因
- 在生成成功后通过 HTTP 把 `mp4` 结果传回客户端

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

当前脚本的 Python 选择策略是：

- `run_service.sh` / `check_env.sh`
  - 优先使用 `code/server/wan_local_service/.venv/bin/python`
  - 如果你确实需要覆盖服务运行时，可显式设置 `WAN_SERVICE_PYTHON_BIN`
- `WanRunner` 调用 `generate.py`
  - 默认继承当前服务进程自己的解释器
  - 如需单独覆盖推理解释器，可显式设置 `WAN_INFERENCE_PYTHON_BIN`

## 快速环境检查

在重跑安装脚本前，先执行：

```bash
cd code/server/wan_local_service
bash scripts/check_env.sh
```

该脚本不依赖现成 `.venv`，会直接报告当前工作区的真实状态，包括：

- `WAN_PYTHON_BIN` 指向的运行时 Python 是否存在
- `.venv` 是否存在
- `third_party/Wan2.2`
- `third_party/Wan2.2-TI2V-5B`
- `nvidia-smi`
- `nvcc`
- `fastapi` / `uvicorn` / `torch` / `flash_attn` 导入状态

如果只想把服务启动条件当成硬门槛检查，可以执行：

```bash
cd code/server/wan_local_service
bash scripts/check_env.sh --require service
```

如果只想检查完整推理链路是否就绪，可以执行：

```bash
cd code/server/wan_local_service
bash scripts/check_env.sh --require inference
```

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

如果 `run_service.sh` 发现 `.venv` 或 `fastapi` 依赖缺失，会直接给出补环境命令，而不再只报找不到 `.venv/bin/python`。

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
- 在长任务期间打印 `stage` 和采样进度
- 打印 `task_id`
- 打印 `output_path` 或 `error_message`

默认等待窗口当前为 40 分钟，适配 SDPA fallback 下的长任务。

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
- `GET /api/tasks/{task_id}` 额外返回：
  - `output_exists`
  - `status_message`
  - `progress_current`
  - `progress_total`
  - `progress_percent`
  - `download_url`
- 其中：
  - `status_message` 会反映当前阶段，例如 `creating pipeline`、`loading checkpoints`、`sampling`、`saving video`、`finished`
  - `progress_*` 主要用于长时间采样任务的观测
  - `download_url` 在 `status=succeeded` 且结果文件存在时可直接用于客户端下载视频

结果文件下载接口：

- `GET /api/results/<task_id>/file`
  - 成功时返回 `video/mp4`
  - 响应头包含 `Content-Disposition: attachment; filename="<task_id>.mp4"`
  - 适合 Windows 客户端把视频保存到本地目录，而不是依赖 `\\wsl$` 路径访问

下载示例：

```bash
curl --fail --output result.mp4 \
  http://127.0.0.1:8000/api/results/<task_id>/file
```

## 日志目录说明

每个任务使用独立日志文件：

- 文件路径：`logs/<task_id>.log`
- 内容包括：启动时间、任务 ID、执行命令、`generate.py` 标准输出、退出码

服务后台模式的运行日志独立写到：

- `logs/service.log`

## 服务重启恢复语义

服务启动时会扫描遗留 `pending` 和 `running` 任务。

- 如果对应 `outputs/<task_id>/result.mp4` 已经存在：
  - 会优先恢复成 `succeeded`
  - 并自动回填 `output_path`
- 如果输出文件不存在：
  - 才会按中断任务处理为 `failed`

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

- 上游官方 TI2V-5B 主路径原本会进入 `wan/modules/model.py -> flash_attention()`
- 上游原始 `wan/modules/attention.py` 在没有 `flash_attn` 时会触发 `assert FLASH_ATTN_2_AVAILABLE`
- 当前 workspace 已通过本地 patch 给 `flash_attention()` 补上 SDPA fallback

因此对于当前仓库的默认运行路径：

- `flash_attn` 不再是必装依赖
- `setup_wan22.sh` 默认不会再尝试本地编译 `flash_attn`
- 默认交付路径就是当前已验证通过的 SDPA fallback

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

7. 默认安装链现在为什么不再追 `nvcc` / `flash_attn`

- 说明：当前仓库已经验证过 SDPA fallback 能真实出片，因此默认路径不再需要本地编译 `flash_attn`
- 当前 `setup_wan22.sh` 的默认行为：
  - `WAN_ENABLE_FLASH_ATTN_BUILD=0`
  - 不自动安装 CUDA toolkit
  - 不自动安装 `flash_attn`
- 正常情况下只需要：

```bash
bash scripts/setup_wan22.sh
```

- 只有你明确想恢复那条可选高性能编译链时，才需要自己显式开启：

```bash
WAN_ENABLE_FLASH_ATTN_BUILD=1 bash scripts/setup_wan22.sh
```

9. 当前 workspace 已补上 `flash_attention()` 的 SDPA fallback

- 说明：官方 `wan/modules/attention.py` 原本只有 `attention()` 有 `scaled_dot_product_attention` 回退，但 `wan/modules/model.py` 等主路径直接调用了 `flash_attention()`
- 当前已把同一份官方 fallback 逻辑补到 `flash_attention()` 上
- 当前父仓库也已把这份修改固化为：
  - `patches/wan2.2_attention_sdpa_fallback.patch`
  - `setup_wan22.sh` 在 clone / pull Wan2.2 后会自动重放这份 patch
- 结果：
  - `flash_attn` 缺失时，当前 workspace 不再直接断在 `assert FLASH_ATTN_2_AVAILABLE`
  - 真实 WSL 环境中的 `check_env.sh` 已达到 `inference_ready=yes`
  - 真实任务已经能进入 GPU 生成阶段，并已成功生成：
    - `outputs/57783f7a-5915-49f2-b105-8cd15dd26fbe/result.mp4`
- 代价：
  - 运行速度会明显慢于装好 `flash_attn` 的路径
  - 当前虽然已把 `run_sample_t2v.sh` 默认等待窗口拉长到 40 分钟，但 Windows 客户端的长任务轮询仍需要按真实联调再验证一次
  - 当前 1280x704 样例完整耗时约 31 分钟

10. 如果你更偏向效率，不想在实际生成阶段默认启用低内存防护

- 当前默认行为已经改成：
  - 不自动降低 `frame_num`
  - 不自动降低 `sample_steps`
  - 不默认开启生成前内存硬门槛
- 如果后续你需要切回保守运行模式，可以显式设置：

```bash
export WAN_LOW_MEMORY_PROFILE=1
export WAN_ENFORCE_RUNTIME_MEMORY_GUARD=1
```

11. 当前 `run_service.sh start` 已增强后台脱离，但最终仍以真实 WSL 联调为准

- 当前脚本已优先通过 `setsid` 脱离当前会话
- 本轮在当前 agent 里已真实通过：
  - `bash scripts/run_service.sh start`
  - `bash scripts/run_service.sh status`
  - `curl --noproxy '*' http://127.0.0.1:8000/healthz`
  - `bash scripts/run_service.sh stop`
- 如果你的具体终端环境仍会回收后台进程，联调时再临时切回 `bash scripts/run_service.sh foreground`

12. Windows 客户端轮询期间服务随终端退出

- 说明：如果服务以前台模式跑在临时 shell 里，关闭该终端或收到中断后，客户端轮询会得到 `Connection refused`
- 处理：
  - 在真实 WSL 本机终端里优先用 `bash scripts/run_service.sh start`
  - 如果你的具体终端环境里后台模式仍不保活，就改用 `bash scripts/run_service.sh foreground`

13. 历史保留：如果你后续仍坚持要把 `flash_attn` 编好

- `WAN_FLASH_ATTN_MAX_JOBS=1`
- `WAN_FLASH_ATTN_CUDA_ARCHS=80`
- 说明：
  - 当前目标 GPU 是 RTX 3090
  - 不再默认编译 `sm_90/sm_100/sm_120`
  - 能减少本地编译时间和 OOM 风险
  - 但这条链路已不再是当前仓库的默认维护目标
