# STATUS

## 当前状态

当前仓库已有两条主线：

- WSL 服务端 MVP 第一阶段已完成，范围保持在 `code/server/wan_local_service/**`
- Windows Qt6 客户端 MVP 已完成首轮落地，范围保持在 `code/client/qt_wan_chat/**`

已完成：

### WSL 服务端

- FastAPI 服务入口与 5 个接口
- SQLite 任务持久化
- 单 worker 串行任务执行器
- Wan2.2 官方 `generate.py` 调用封装
- 稳定错误码与 HTTP 状态码映射
- `null` 语义与重启恢复语义固定
- `setup_wan22.sh` / `run_service.sh` / `run_sample_t2v.sh`
- `check_env.sh` / `app.env_report`
- 协议文档、自测报告、集成说明
- 默认模型目录在 README / `.env.example` / `config.py` / 启动脚本之间完成统一
- `setup_wan22.sh` 已补齐当前真实验证过的缺失运行时依赖：
  - `einops`
  - `decord`
  - `librosa`
  - `peft`
- `run_service.sh` 已支持：
  - `foreground`
  - `start`
  - `status`
  - `stop`
- 后台模式会写出：
  - `storage/service.pid`
  - `logs/service.log`
- `WanRunner` 失败结果已改为优先回传日志尾部的真实错误摘要，而不再只返回笼统的 `generate.py exited with code N`

当前工作区重新核对后的真实环境状态：

- `code/server/wan_local_service/.venv` 已存在
- `code/server/wan_local_service/third_party/Wan2.2` 已存在
- `code/server/wan_local_service/third_party/Wan2.2-TI2V-5B` 已存在
- `nvidia-smi` 当前可用，GPU 为 `RTX 3090`
- `nvcc` 当前仍不在 PATH
- 当前工作区已经可以启动服务并跑通一次真实 `t2v` 生成
- 当前未完成项主要剩在：
  - Windows 客户端长任务轮询闭环
  - Windows 客户端最终联调闭环

### Windows Qt 客户端

- Qt6 + CMake + Widgets 客户端工程已创建
- `ApiClient` 已基于 `QNetworkAccessManager` 实现：
  - `GET /healthz`
  - `POST /api/tasks`
  - `GET /api/tasks/{task_id}`
  - `GET /api/tasks`
  - `GET /api/results`
- 三栏主窗口已完成：
  - 任务列表
  - 聊天区 / 输入框 / 发送按钮
  - 配置区 / 结果列表 / 输出目录 / 诊断日志
- 启动自动拉取 `/healthz`、`/api/tasks`、`/api/results`
- 任务创建后自动轮询并同步刷新任务列表与结果列表
- 稳定错误体、HTTP 错误、JSON 解析错误、服务不可达错误已实现非阻塞提示
- `\\wsl$\<distro>\...` 路径转换逻辑已实现
- Windows 原生编译已通过
- Windows 原生启动已通过
- Windows smoke test 已真实打到本地 FastAPI 服务

## 最近一次重要进展

2026-04-24：

- 服务端可观测性和恢复语义已补强：
  - `GET /api/tasks/{task_id}` 现已增加：
    - `status_message`
    - `progress_current`
    - `progress_total`
    - `progress_percent`
  - 上述字段来自任务日志实时解析，可直接反映 `creating pipeline / loading checkpoints / sampling / saving video / finished`
  - 任务详情读取时，如果发现 `outputs/<task_id>/result.mp4` 已存在，但数据库状态仍停在 `pending/running`，会自动回填成 `succeeded`
  - 服务启动恢复时也不再一刀切把遗留 `pending/running` 任务全部改成失败；若输出文件已落盘，会优先恢复为 `succeeded`
- 服务端脚本已继续收敛：
  - `run_sample_t2v.sh` 默认等待窗口已从 6 分钟提升到 40 分钟
  - `run_sample_t2v.sh` 轮询时会打印 `stage` 和采样进度
  - `run_service.sh start` 现优先走 `setsid` 脱离当前会话
  - `run_service.sh stop` 在超时后会补一次强制停止，避免遗留僵尸 PID
  - `setup_wan22.sh` 现已默认 `WAN_ENABLE_FLASH_ATTN_BUILD=0`
  - 默认安装链不再尝试安装 CUDA toolkit，也不再尝试本地编译 `flash_attn`
  - 当前服务端的默认可交付路径已经固定为 SDPA fallback，而不是高性能编译链
- 当前会话已真实补过一轮后台服务复验：
  - `bash code/server/wan_local_service/scripts/run_service.sh start`
  - `bash code/server/wan_local_service/scripts/run_service.sh status`
  - `curl --noproxy '*' http://127.0.0.1:8000/healthz`
  - `bash code/server/wan_local_service/scripts/run_service.sh stop`
  - 本轮在当前 agent 里均已成功
- 当前服务端测试已提升到：
  - `PYTHONPATH=$PWD .venv/bin/python -m pytest tests -q`
  - `17 passed`
- 新增服务端自测报告：
  - `docs/reports/self_test/server/2026-04-24_server_recovery_and_observability.md`

- 官方 Wan2.2 attention 路径已补上运行态 SDPA fallback：
  - `code/server/wan_local_service/third_party/Wan2.2/wan/modules/attention.py`
  - 现在 `flash_attention()` 在 `flash_attn` / `flash_attn_interface` 都缺失时，不再直接断在 `assert FLASH_ATTN_2_AVAILABLE`
  - 会复用同文件里已有的 `scaled_dot_product_attention` 回退逻辑
- 服务端当前也已接受这条 fallback 路径：
  - `WanRunner` 不再把缺少 `flash_attn` 视为默认硬阻塞
  - `check_env.sh` / `env_report.py` 在真实 WSL 环境里现已显示 `inference_ready=yes`
  - `flash_attn` 本地编译链默认已关闭，不再作为当前主路径前置
- 真实服务链已推进到 GPU 满载生成阶段：
  - 以 `bash code/server/wan_local_service/scripts/run_service.sh foreground` 托管服务
  - 以 `bash code/server/wan_local_service/scripts/run_sample_t2v.sh` 创建了真实任务 `57783f7a-5915-49f2-b105-8cd15dd26fbe`
  - 任务已真实从 `pending` 进入 `running`，最终完成并生成视频文件
  - `nvidia-smi` 已看到 `/python3.12` 占用约 `23.5 GiB / 24 GiB` 显存，`GPU-Util=100%`
  - 真实输出文件：
    - `code/server/wan_local_service/outputs/57783f7a-5915-49f2-b105-8cd15dd26fbe/result.mp4`
  - `ffprobe` 已确认：
    - 编码：`h264`
    - 分辨率：`1280x704`
    - 时长：`5.041667s`
    - 帧数：`121`
    - 文件大小：`11051605` bytes
  - 任务日志尾部已确认：
    - `Saving generated video to .../result.mp4`
    - `Finished.`
    - `generate.py exit code: 0`
- `run_sample_t2v.sh` 现已按当前 SDPA fallback 模式做长任务适配：
  - 默认等待窗口已拉长
  - 当前脚本能直接打印阶段和采样进度
  - 这次 1280x704 样例完整耗时约 31 分钟，其中采样阶段约 16 分 36 秒
- `flash_attn` 编译链现已降级为历史保留能力：
  - `build_flash_attn_resumable.sh` 仍保留在仓库中
  - 但默认服务端安装与运行路径不再依赖它

- `flash_attn` 本地编译链已改成仓库内可续编模式：
  - 当前这次真实编译已从 `pip` 的临时目录转存到 `code/server/wan_local_service/third_party/flash-attn-2.8.3-src`
  - 已在 `2026-04-24 02:46:53 +0800` 主动中断当前 `pip install flash-attn==2.8.3` 进程，避免继续占住夜间会话
  - 当前持久快照保留了 `22 / 73` 个 `.o` 目标
  - 最新已编译目标是 `flash_bwd_hdim96_bf16_causal_sm80.o`，时间为 `2026-04-24 02:41:33 +0800`
  - 新增 `code/server/wan_local_service/scripts/build_flash_attn_resumable.sh`
  - `code/server/wan_local_service/scripts/setup_wan22.sh` 现在也会改走同一份持久源码树，不再回到 `pip` 的 `/tmp/pip-install-*` 临时目录
- 当前 `flash_attn` 持久快照已补充到服务端自测报告：
  - `docs/reports/self_test/server/2026-04-24_flash_attn_resume_snapshot.md`
- 新增对 `flash_attn` 编译崩溃的系统级复盘：
  - 已核对 `/var/log/apt/history.log`
  - 已核对 `/var/log/kern.log`
  - 已核对 `/var/log/syslog`
  - 已核对 `/mnt/c/Users/37545/.wslconfig`
- 已确认：
  - `cuda-toolkit-13-0` 曾在真实 WSL 中于 `2026-04-23 23:24` 安装完成
  - 后续 `flash_attn` 不是停在“找不到 `nvcc`”，而是已经真正进入本地 CUDA/C++ 编译
  - 从 `2026-04-23 23:28` 到 `2026-04-24 01:46` 之间，多次发生全局 OOM
  - OOM 现场的主进程是 `cicc` / `cc1plus` / `nvcc`
  - `2026-04-24 01:46:34` 还出现了用户会话 `systemd` 被 OOM 杀死
  - 这可以直接解释“Codex 自动退出”和“WSL 看起来崩了”的现象
- `code/server/wan_local_service/scripts/setup_wan22.sh` 已做保守化修正：
  - 默认 `WAN_FLASH_ATTN_MAX_JOBS` 从 `4` 下调到 `1`
  - 在 WSL 中若显式把 `MAX_JOBS` 提高，会输出 OOM 风险提示
  - 在真正开始 `flash_attn` 编译前，会先检查 `MemAvailable` / `SwapFree`
  - 会额外提示 `dockerd` / `containerd` / `postgres` 等常驻进程占用
- 运行时 Python 选择已收敛为更稳定的双路径：
  - `run_service.sh` / `check_env.sh` 默认优先使用 `code/server/wan_local_service/.venv/bin/python`
  - `WanRunner` 默认使用当前服务进程自己的解释器，而不是外部 shell 中遗留的 `WAN_PYTHON_BIN`
- 运行阶段的低内存保守模式已改为显式 opt-in：
  - 默认不再自动压低 `frame_num` / `sample_steps`
  - 默认不再启用生成前内存硬门槛
  - 如确实需要，可显式设置：
    - `WAN_LOW_MEMORY_PROFILE=1`
    - `WAN_ENFORCE_RUNTIME_MEMORY_GUARD=1`

- 新增 `code/server/wan_local_service/scripts/check_env.sh`
- 新增 `code/server/wan_local_service/app/env_report.py`
- `scripts/run_service.sh` 已增加服务启动前检查：
  - 运行时 Python 缺失时给出明确修复提示
  - `fastapi` / `uvicorn` 缺失时给出明确修复提示
- 当前 workspace 再次复核到的真实环境：
  - `.venv` 已存在
  - `third_party/Wan2.2` 已存在
  - `third_party/Wan2.2-TI2V-5B` 已存在
  - 最新重复探测里 `nvidia-smi` 已恢复可用
  - `nvcc` 缺失
  - 系统 `python3` 仍缺少 `fastapi` / `httpx` / `pytest`，但服务实际运行走的是 `.venv`
- 因此当前真实状态是：
  - 服务端单测已通过
  - FastAPI 实例已真实启动
  - 真实 `t2v` 样例已生成出视频文件
  - 当前剩余问题不在“能否出片”，而在性能和保活

- `code/server/wan_local_service/scripts/setup_wan22.sh` 已改为可直接处理完整 `flash_attn` 安装链：
  - `nvcc` 缺失时自动尝试安装 `cuda-toolkit-13-0`
  - 自动创建并激活 `.venv`
  - 不再盲目升级 `setuptools`
  - 显式固定 `setuptools<82`，避免 `torch 2.11.0` 依赖冲突
  - 预装 `packaging`、`psutil`、`ninja`
  - 固定安装 `flash-attn==2.8.3 --no-build-isolation`
- 当前服务端安装目标已收敛为“直接运行 `bash code/server/wan_local_service/scripts/setup_wan22.sh`”，而不是手工逐条输入 pip 命令
- 按“只走服务端、不走客户端”的方式，直接在 `code/server/wan_local_service/third_party/Wan2.2` 真实重跑了官方 `generate.py`
- 非提权 sandbox 直跑时，`torch.cuda.current_device()` 先报出：
  - `RuntimeError: Found no NVIDIA driver on your system`
- 同一条直跑命令在提权后恢复到真实 WSL / GPU 路径，并继续完成：
  - T5 checkpoint 加载
  - VAE checkpoint 加载
  - 3 个模型 shard 加载
  - 进入 `Generating video ...` 首个采样 step
- 2026-04-24 这轮“直接服务端生成链路验证”最终再次失败在：
  - `wan/modules/attention.py` 的 `assert FLASH_ATTN_2_AVAILABLE`
- 这次验证说明：
  - 当前服务端主链路不依赖 Windows Qt 客户端即可直接复现真实生成阻塞
  - 当前真实主阻塞已收敛到 `flash_attn` 本地编译 OOM，而不是 API 层、任务调度层或 `setuptools` 冲突

2026-04-23：

- Windows Qt 客户端 `code/client/qt_wan_chat` 已真实编译通过并成功启动
- Windows 客户端已真实完成：
  - `/healthz`
  - `/api/tasks`
  - `/api/results`
  - `POST /api/tasks`
  - `pending -> running` 轮询状态更新
- 最新 Windows smoke task：
  - `141f1a6d-ba50-44ec-9dec-4662ec43ab7c`
- 最新 Windows 侧真实阻塞：
  - 轮询期间服务掉线，客户端收到 `network_error / Connection refused`
  - `\\wsl$` 路径访问被拒绝，打开目录成功路径未验证
- 客户端自测报告已新增：
  - `docs/reports/self_test/client/mvp_client_self_test.md`

- 真实运行了 `bash code/server/wan_local_service/scripts/setup_wan22.sh`
- WSL 中 `nvidia-smi` 已恢复可用，确认 GPU 为 `RTX 3090`
- 真实运行了多次 `bash code/server/wan_local_service/scripts/run_sample_t2v.sh`
- 最新真实任务 `16daa568-fede-4da1-b20b-28f1138d09a1` 已通过服务端执行到官方 `generate.py` 的真实采样阶段
- 运行时阻塞点已继续推进：
  - 安装 `librosa` 后，最新前沿到达 `peft`
  - 安装 `peft` 后，最新任务 `16daa568-fede-4da1-b20b-28f1138d09a1` 已加载 T5、VAE、模型分片，并进入真实采样阶段
  - 最新真实失败点已确认是 `wan/modules/attention.py` 中的 `assert FLASH_ATTN_2_AVAILABLE`
- 这轮真实运行已确认：对官方 TI2V-5B 主路径，`flash_attn` 是硬依赖
- NVIDIA CUDA apt keyring 已在 WSL 中完成安装，当前目标 toolkit 已明确为 `cuda-toolkit-13-0`
- `setup_wan22.sh` 当前仍在 `flash_attn` 安装阶段遇到真实环境阻塞：
  - `CUDA_HOME environment variable is not set`
  - `nvcc was not found`
  - 当前 agent 会话还缺少可直接完成 `sudo apt-get update/install` 的 sudo 能力
- 新增服务端改进：
  - `run_service.sh` 已补齐后台常驻与 PID 管理，用于避免服务绑定在临时终端上
  - `WanRunner` 新增失败摘要提炼，典型返回现为 `AssertionError (generate.py exit code 1)`
- 本轮本地验证结果：
  - `PYTHONPATH=$PWD pytest tests -q` -> `10 passed`
  - `WAN_SERVICE_SKIP_HEALTHCHECK=1 bash scripts/run_service.sh start/status/stop` 已完成进程级验证
  - 当前 agent sandbox 对本地监听端口存在限制，后台模式 `/healthz` ready check 仍需在真实 WSL 终端补一次验证
