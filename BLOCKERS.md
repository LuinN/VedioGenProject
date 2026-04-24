# BLOCKERS

## 当前真实阻塞

### 新增：当前 workspace 已具备真实出片所需的最小服务端环境

当前会话真实检查结果：

```text
code/server/wan_local_service/.venv                  present
code/server/wan_local_service/third_party/Wan2.2    present
code/server/wan_local_service/third_party/Wan2.2-TI2V-5B present
nvidia-smi                                           RTX 3090 visible
nvcc                                                 missing
```

当前结论：

- 服务端最小运行链路已经打通，并已真实生成 `result.mp4`
- 当前剩余阻塞不在“能不能跑”，而在：
  - Windows 客户端长任务轮询闭环
  - Windows 客户端最终联调
  - `flash_attn` 高性能路径

### 1. WSL FastAPI 服务在 Windows 客户端轮询期间掉线，后台模式已补上但仍待真实联调复验

Windows 客户端真实报错：

```text
Could not reach the local service. Check the URL and make sure FastAPI is running. [code=network_error]
details=Connection refused
```

触发上下文：

- Windows smoke task：
  - `141f1a6d-ba50-44ec-9dec-4662ec43ab7c`
- 客户端已成功观察到：
  - `pending`
  - `running`
- 随后 `http://127.0.0.1:8000` 拒绝连接

影响：

- Windows 客户端的创建任务和轮询逻辑已被真实证明可用
- 但终态失败展示与成功结果展示无法稳定复验
- 服务端现已新增并复验 `bash scripts/run_service.sh start|status|stop` 后台模式
- 当前 WSL 侧阻塞已经从“后台服务自己起不来”收敛成“Windows 客户端长任务轮询尚未补一次真实闭环复验”

### 2. 当前已经能真实出片，但 SDPA fallback 性能明显偏慢

最新服务端真实任务：

- `task_id`: `57783f7a-5915-49f2-b105-8cd15dd26fbe`
- `log_path`: `/home/liupengkun/VedioGenProject/code/server/wan_local_service/logs/57783f7a-5915-49f2-b105-8cd15dd26fbe.log`
- `output_path`: `/home/liupengkun/VedioGenProject/code/server/wan_local_service/outputs/57783f7a-5915-49f2-b105-8cd15dd26fbe/result.mp4`

真实运行进展：

- 已加载 T5 checkpoint
- 已加载 VAE checkpoint
- 已加载 3 个模型 shard
- 已完成 50 步采样并保存视频文件

真实尾部：

```text
[2026-04-24 11:54:45,831] INFO: Saving generated video to .../result.mp4
[2026-04-24 11:54:48,035] INFO: Finished.
generate.py exit code: 0
```

当前缓解状态：

- `code/server/wan_local_service/third_party/Wan2.2/wan/modules/attention.py` 已补丁为：
  - `flash_attention()` 在 `flash_attn` / `flash_attn_interface` 都缺失时，不再直接 `assert`
  - 改为复用同文件已有的 `scaled_dot_product_attention` fallback
- `WanRunner` 与 `check_env.sh` 也已同步接受这条 fallback 路径
- 在真实 WSL 环境里，当前已确认：
  - `service_ready=yes`
  - `inference_ready=yes`
  - `flash_attn` 缺失不再拦住真实推理启动
  - 真实任务 `57783f7a-5915-49f2-b105-8cd15dd26fbe` 已成功出片
  - RTX 3090 显存已打到约 `23.5 GiB / 24 GiB`，`GPU-Util=100%`

当前新问题：

- 当前主阻塞已从“依赖断言”切换成“SDPA fallback 模式下真实生成更慢”
- 这次 1280x704 样例总耗时约 31 分钟，其中采样阶段约 16 分 36 秒
- 服务端 `run_sample_t2v.sh` 已把默认等待窗口拉长到 40 分钟，并会输出 `stage/progress`
- 当前剩余问题主要落在 Windows 客户端轮询策略尚未按长任务重新做一次真实复验

### 3. `flash_attn` 本地编译会触发 WSL 全局 OOM，并进一步打断 Codex / 用户会话

最新真实证据来自本机系统日志，而不是推测：

- `/var/log/apt/history.log` 记录 `cuda-toolkit-13-0` 已在 `2026-04-23 23:24` 安装完成
- `/var/log/kern.log` 在 `2026-04-23 23:28`、`2026-04-24 00:12`、`00:25`、`00:37`、`01:02`、`01:14`、`01:46` 多次记录到 `flash_attn` 编译期间的 OOM
- 同期进程表里出现多路并发的 `cicc` / `cc1plus` / `nvcc`
- 其中 `cicc` 多次被直接打死，例如：

```text
2026-04-24T00:37:45 ... Out of memory: Killed process 3017 (cicc)
2026-04-24T01:46:37 ... Out of memory: Killed process 6120 (cicc)
```

- 更严重的一次在 `2026-04-24 01:46:34` 已经开始杀用户会话里的 `systemd`：

```text
Out of memory: Killed process 1119 (systemd)
```

- `journalctl` 同时记录：

```text
system.journal corrupted or uncleanly shut down, renaming and replacing
```

当前结论：

- 这已经不是“还没装好 `nvcc` / `CUDA_HOME`”的旧问题
- 真实根因是 `flash_attn` 本地编译进入 CUDA/C++ 阶段后并发过高，触发 WSL 全局 OOM
- 一旦用户会话里的 `systemd` 被杀，当前 shell、Codex 进程和相关终端都会被一起打断，所以主观感受会像“Codex 自动退出、WSL 崩了”

已知放大因素：

- `setup_wan22.sh` 之前默认 `WAN_FLASH_ATTN_MAX_JOBS=4`
- 同期日志里还能看到 `dockerd` / `containerd` / `postgres` 等常驻进程占用额外内存
- Windows `.wslconfig` 当前虽然已设置：
  - `memory=24GB`
  - `swap=12GB`
  - `processors=12`
  但多路 `cicc` 仍可把 RAM 和 swap 全部耗尽

最小修复路径：

- 先停掉 Docker 和其他不必要的 WSL 常驻服务
- 使用串行编译重跑：
  - `cd code/server/wan_local_service`
  - `WAN_FLASH_ATTN_MAX_JOBS=1 bash scripts/setup_wan22.sh`
- 如果仍然 OOM，再临时提高 `.wslconfig` 的 `memory` / `swap`，或在更干净的 WSL 发行版中完成一次编译

### 4. 更早一轮的 `nvcc` / `CUDA_HOME` 缺失错误已经不是最新主阻塞

历史错误仍真实存在过：

```text
OSError: CUDA_HOME environment variable is not set. Please set it to your CUDA install root.
flash_attn was requested, but nvcc was not found
```

但根据 `apt` 历史记录，这个阶段已经在真实 WSL 上被推进到“可以真正启动本地编译”。

当前应优先处理的不是继续追 `nvcc`，而是解决本地编译 OOM。

当前缓解状态：

- 编译脚本已经默认降到单并发
- 编译前会先检查 `MemAvailable` / `SwapFree`
- 当前这次真实编译也已转存到仓库内持久源码树 `code/server/wan_local_service/third_party/flash-attn-2.8.3-src`
- 已记录下 `22 / 73` 个 `.o` 目标的当前快照，可以直接续编
- 这可以减少再次把 WSL 打挂的概率，也避免每次都从 `pip` 的临时目录重新开始
- 但在当前 workspace 里，`nvcc` 仍不在 PATH，`flash_attn` 也仍未装好，所以高性能路径还没有真正闭环

当前续编入口：

- `cd code/server/wan_local_service`
- `bash scripts/build_flash_attn_resumable.sh status`
- `WAN_FLASH_ATTN_MAX_JOBS=1 bash scripts/build_flash_attn_resumable.sh resume`
- 或者继续走总安装链：`WAN_FLASH_ATTN_MAX_JOBS=1 bash scripts/setup_wan22.sh`

### 5. 官方主 requirements 之外还需要额外运行时依赖

这轮真实推进过程中确认过的导入链缺口：

- `einops`
- `decord`
- `librosa`
- `peft`

原因：

- `wan/__init__.py` 会无条件导入 `speech2video`
- `wan/__init__.py` 也会无条件导入 `animate`
- 上游主 `requirements.txt` 未覆盖全部被导入的运行时依赖

影响：

- 只按上游主 `requirements.txt` 安装时，真实任务会在导入阶段持续前移失败
- 当前已通过手动安装和真实重跑把前沿推进到 `flash_attn` 运行时断言
- `setup_wan22.sh` 需要显式补装这些额外依赖，才能避免回退到旧的导入错误

最小修复路径：

- 在 `setup_wan22.sh` 中显式补装当前已验证缺失的运行时依赖
- fresh environment 上优先执行 `bash code/server/wan_local_service/scripts/setup_wan22.sh`

### 6. 当前 Windows agent 会话对 `\\wsl$` 路径访问被拒绝

真实错误：

```text
Access to the path '\\wsl$\Ubuntu-24.04\mnt\d\Projects\VideoGenProject\code\server\wan_local_service\logs' is denied.
```

影响：

- 客户端已实现 `\\wsl$` 路径转换和错误提示
- 但“打开输出目录”的成功路径仍未在本会话真实验证

### 7. 当前 agent sandbox 不允许本地监听端口复验后台服务 `/healthz`

当前会话真实对照：

```text
PermissionError: [Errno 1] Operation not permitted
```

最小复现：

```bash
python3 -m http.server 8765
```

影响：

- 当前 agent sandbox 里不能把本地监听端口的验证结果当成真实 WSL 主机结果
- 后台服务 `/healthz` 的最终复验仍应放到真实 WSL 本机终端里完成

### 8. `run_service.sh start` 已增强脱离当前会话，但 Windows 侧长轮询还需补一次真实复验

最新真实现象：

- 脚本当前已优先用 `setsid` 启动后台服务
- 本轮在当前 agent 里已真实通过：
  - `run_service.sh start`
  - `run_service.sh status`
  - `curl /healthz`
  - `run_service.sh stop`
- 因此当前 WSL 侧的“后台服务起不来”已不再是主阻塞

当前剩余问题：

- 还没有从 Windows Qt 客户端重新补一次“后台服务 + 长任务轮询 + 最终 output_path 展示”的真实联调

最小修复路径：

- 在真实 WSL 本机终端中执行 `bash code/server/wan_local_service/scripts/run_service.sh start`
- 再从 Windows Qt 客户端发起一次真实任务
- 核对客户端最终是否拿到：
  - `status=succeeded`
  - `output_path`
  - 长任务期间的轮询结果

### 9. 当前 agent sandbox 下直接运行 `generate.py` 会给出伪造的 CUDA 假阻塞

当前会话真实对照：

```text
RuntimeError: Found no NVIDIA driver on your system. Please check that you have an NVIDIA GPU and installed a driver
```

触发上下文：

- 在当前 agent sandbox 中直接执行官方 `generate.py`
- 同一环境里 `nvidia-smi` 可用，但未提权的 PyTorch CUDA 初始化失败
- 同一条命令在提权后恢复正常，重新到达：
  - T5 / VAE / shard 加载
  - `Generating video ...`
  - `assert FLASH_ATTN_2_AVAILABLE`

影响：

- 当前 agent sandbox 中的“找不到 NVIDIA driver”不是项目代码真实前沿
- 服务端真实阻塞判断应以提权后的直接生成结果为准

最小修复路径：

- 后续涉及真实 Wan GPU 推理验证时，优先使用真实 WSL 终端或提权会话执行
- 不要把未提权 sandbox 中的 CUDA 初始化报错误判成模型链路回退
