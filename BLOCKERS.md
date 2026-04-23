# BLOCKERS

## 当前真实阻塞

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
- 服务端现已新增 `bash scripts/run_service.sh start|status|stop` 后台模式，优先缓解“服务绑在临时终端上”的问题
- 该缓解措施尚未在真实 Windows -> WSL 客户端联调中完成闭环复验

### 2. 官方 TI2V-5B 主路径已确认 `flash_attn` 是运行时硬依赖

最新服务端真实任务：

- `task_id`: `16daa568-fede-4da1-b20b-28f1138d09a1`
- `log_path`: `/mnt/d/projects/videogenproject/code/server/wan_local_service/logs/16daa568-fede-4da1-b20b-28f1138d09a1.log`

真实运行进展：

- 已加载 T5 checkpoint
- 已加载 VAE checkpoint
- 已加载 3 个模型 shard
- 已进入 `Generating video ...` 的首个采样 step

真实尾部：

```text
File "/mnt/d/projects/videogenproject/code/server/wan_local_service/third_party/Wan2.2/wan/modules/attention.py", line 112, in flash_attention
    assert FLASH_ATTN_2_AVAILABLE
AssertionError
generate.py exit code: 1
```

代码依据：

- `wan/modules/model.py` 直接调用 `flash_attention(...)`
- `wan/modules/attention.py` 的 `flash_attention()` 在无 FA3 时会走 `assert FLASH_ATTN_2_AVAILABLE`
- TI2V 主路径没有走 `attention()` 中的 `scaled_dot_product_attention` 回退逻辑

影响：

- 这已经不是单纯的 Python 缺包问题
- 对当前官方 TI2V-5B 主路径，不应尝试无 `flash_attn` 绕过方案
- 当前没有真实 `output_path`
- 2026-04-24 已再次用“绕过客户端、直接运行官方 `generate.py`”的方式复验到同一失败点，结论没有变化

### 3. `flash_attn` 安装失败

真实错误：

```text
OSError: CUDA_HOME environment variable is not set. Please set it to your CUDA install root.
```

同一次报错上下文还包含：

```text
flash_attn was requested, but nvcc was not found
```

触发位置：

- `bash code/server/wan_local_service/scripts/setup_wan22.sh`
- `python -m pip install flash_attn --no-build-isolation`

影响：

- Wan 主依赖链没有完成到官方推荐状态
- 最新真实采样任务已经证明：在当前环境中确实会阻塞在 attention 路径

最小修复路径：

- 优先安装和当前 `torch 2.11.0+cu130` 更贴近的 `cuda-toolkit-13-0`
- 执行：
  - `sudo apt-get update`
  - `sudo apt-get install -y cuda-toolkit-13-0`
  - `export CUDA_HOME=/usr/local/cuda-13.0`
  - `export PATH="${CUDA_HOME}/bin:${PATH}"`
- 重跑 `bash code/server/wan_local_service/scripts/setup_wan22.sh`
- 再重跑 `bash code/server/wan_local_service/scripts/run_sample_t2v.sh`

### 4. 当前 agent 会话无法直接完成 NVIDIA CUDA apt 安装

当前状态：

- 官方 keyring 安装包已下载：
  - `/tmp/cuda-keyring_1.1-1_all.deb`
- 本机操作者已在 WSL 中完成：
  - `sudo dpkg -i /tmp/cuda-keyring_1.1-1_all.deb`
- `cuda-ubuntu2404-x86_64.list` 已存在，NVIDIA apt 源接入完成

当前 agent 侧真实错误：

```text
sudo: a terminal is required to read the password
sudo: a password is required
```

影响：

- 不能在当前 agent 会话里直接完成后续 `sudo apt-get update` / `sudo apt-get install`
- 因此 `nvcc` / `CUDA_HOME` 仍未进入可验证状态

最小修复路径：

- 使用具备 sudo 权限的 WSL 会话继续完成 NVIDIA CUDA `13.x` toolkit 安装
- 优先执行：
  - `sudo apt-get update`
  - `sudo apt-get install -y cuda-toolkit-13-0`
- 或由本机操作者先完成 toolkit 安装，再回到当前服务端脚本复验

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

- 当前 agent 会话可以完成 `run_service.sh` 的进程级后台起停验证
- 但不能在本会话里把后台模式的 `/healthz` ready check 写成真实已复验

最小修复路径：

- 在真实 WSL 本机终端中执行 `bash code/server/wan_local_service/scripts/run_service.sh start`
- 立刻执行 `curl --noproxy '*' --fail --silent --show-error http://127.0.0.1:8000/healthz`
- 再从 Windows Qt 客户端重跑一次 smoke task

### 8. 当前 agent sandbox 下直接运行 `generate.py` 会给出伪造的 CUDA 假阻塞

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
