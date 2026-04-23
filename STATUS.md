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
- 协议文档、自测报告、集成说明
- Python 单测 `10 passed`
- 真实 HTTP 自测
- 默认模型目录在 README / `.env.example` / `config.py` / 启动脚本之间完成统一
- `Wan2.2-TI2V-5B` 权重已实际下载到默认路径
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
  - 当前真实主阻塞已收敛到 CUDA toolkit / `nvcc` 可用性，而不是 API 层、任务调度层或 `setuptools` 冲突

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
