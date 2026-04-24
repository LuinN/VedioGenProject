# BLOCKERS

## 当前真实阻塞

### 新增：删除任务协议已完成，但当前不支持删除 `running` 任务

当前状态：

- 服务端已支持 `DELETE /api/tasks/{task_id}`
- 当前允许删除：
  - `pending`
  - `succeeded`
  - `failed`
- 当前拒绝删除：
  - `running`

原因：

- 当前仍是单 worker + 单推理子进程模型
- 服务端尚未实现“中断正在运行的 Wan2.2 generate.py 并安全回收资源”的取消机制
- 因此这轮删除功能只覆盖“非运行中任务删除”

影响：

- Windows 客户端可以先接入历史任务、失败任务和待执行任务的删除
- 如果后续确实需要“删除时连带取消当前生成”，需要单独补任务取消协议和 runner/subprocess 终止逻辑

### 新增：客户端已实现本地任务删除，但还没切到新的服务端删除接口

当前状态：

- Windows 客户端当前的 Tasks 删除仍是本地语义：
  - 从 UI 中移除任务
  - 清理本地任务 metadata、输入图缓存、缩略图和预览缓存
  - 写入 `QStandardPaths::AppDataLocation/deleted_tasks.json`
  - `/api/tasks` 与 `/api/results` 再返回同一 `task_id` 时继续隐藏
- 本地 Tasks 删除不会：
  - 调用 `DELETE /api/tasks/{task_id}`
  - 删除服务端任务历史或输出目录
  - 删除 Videos 页面中的本地 mp4
- Videos 页面里的本地 mp4 仍然只在 `Delete Selected` 时删除

影响：

- 当前仓库里已经同时存在：
  - 服务端真实删除协议
  - 客户端本地隐藏式删除
- 两边语义还没有接到一起
- 如果需要真正清理服务端任务历史，需要 Windows 客户端补接 `DELETE /api/tasks/{task_id}`

### 新增：Windows 客户端已实现 multipart i2v，但当前运行中的服务端进程仍按旧 JSON-only 协议响应

当前客户端完成状态：

- 输入区已支持添加一张本地图片
- 图片会复制到 `%LOCALAPPDATA%/VideoGenProject/tasks/pending_<uuid>/input_image.<ext>`
- 有图片时 `POST /api/tasks` 已改为 `multipart/form-data`
- 无图片时仍保留原 `application/json` 的 `mode=t2v`
- 上传失败会展示稳定错误码，并清理 pending 图片缓存

真实 smoke 结果：

```text
qt_wan_chat.exe --smoke-prompt="i2v client smoke test" --smoke-image=... --smoke-timeout-ms=10000
body: Input should be a valid dictionary or object to extract fields from [HTTP 422] [code=validation_error]
```

当前判断：

- 仓库中的服务端代码和协议文档已经支持 multipart `i2v`
- 但用户已启动的当前服务端进程明显仍按旧 JSON body 解析 `POST /api/tasks`
- 本轮按要求没有启动、停止或重启服务端，因此不能把真实 `i2v` 创建任务验收到成功

影响：

- 客户端代码路径已编译通过
- 现有 T2V 任务 monitor smoke 仍通过
- 真实 `i2v` HTTP 成功创建需要服务端侧重启/更新运行进程后再复验

### 新增：`i2v` 上传协议已完成，但真实 GPU `i2v` 长任务还没在本轮重跑

当前状态：

- 服务端已经支持：
  - `mode=i2v`
  - `multipart/form-data`
  - 输入图片保存到 `outputs/<task_id>/input_image.<ext>`
  - `WanRunner` 调用官方 `generate.py --image <input_image_path>`
- 新增协议和落盘逻辑已通过服务端自测：
  - `31 passed`
- `check_env.sh --require service` 也已纳入 `python-multipart` 检查

当前未完成的真实验证：

- 本轮没有在真实 GPU 环境里重新跑一条完整 `i2v` 长任务
- 当前 agent 从独立命令会话直接探测临时前台端口时表现不稳定，不适合把“跨会话 HTTP 联调”当成这轮真实验收手段
- 因此当前对 `i2v` 的完成度是：
  - 协议完成
  - 图片落盘完成
  - `--image` 命令拼装完成
  - 单测完成
  - 真实 GPU `i2v` 端到端尚待补跑

影响：

- 服务端代码已经具备 Windows 客户端接入 `i2v` 的前置条件
- 但真实推理性能、真实日志形态和最终视频产出仍需要用一条 `i2v` 任务再复验一次

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
  - Windows 客户端调用系统默认播放器播放本地视频仍需真实桌面会话手动复验
  - 当前 Windows agent 会话对 `\\wsl$` 输出目录访问仍被拒绝，但这条路径已不再是唯一结果获取方案
- 服务端实时进度链路和轻量进度协议已完成，不再是 blocker
- Windows 客户端代码已接入 `status_message` / `progress_percent` 展示
- Windows 客户端已用真实任务 `18439c7f-d91b-42a4-a5f3-2e90624587f8` 复验到 `status=succeeded` 和 `output_path`

### 新增：服务端已补实时进度协议，Windows 客户端尚未决定是否切换到轻量轮询端点

当前服务端新增能力：

- `GET /api/tasks/{task_id}/progress`
- `update_time` 会在进度推进时刷新
- `status_message` / `progress_*` 已实时持久化到 SQLite

当前状态：

- 现有 Windows 客户端继续轮询 `GET /api/tasks/{task_id}` 也能拿到进度
- 新的轻量进度端点不是当前功能 blocker
- 但如果后续要降低轮询开销，Windows 侧应评估是否切到 `/progress`

### 新增：客户端下载与本地持久视频列表已接入，播放动作仍需桌面复验

当前服务端新增能力：

- `GET /api/tasks/{task_id}` 与 `GET /api/results` 现在会返回 `download_url`
- `GET /api/results/{task_id}/file` 会直接返回 `video/mp4`

当前客户端完成状态：

- Windows Qt 客户端已解析 `download_url`
- 已实现“选择本地目录 -> 下载视频 -> 保存到 Windows 文件夹”
- 已实现本地 `Videos` 列表与 `downloaded_videos.json` 持久索引
- 已实现双击视频或点击 `Play Selected` 调用 Windows 默认播放器

真实验证：

- `qt_wan_chat.exe --smoke-task-id=18439c7f-d91b-42a4-a5f3-2e90624587f8 --smoke-download-dir=... --smoke-timeout-ms=10000`
- 下载文件：
  - `code/client/qt_wan_chat/build/smoke_downloads/18439c7f-d91b-42a4-a5f3-2e90624587f8.mp4`
- 文件大小：
  - `8060815` bytes
- 持久索引：
  - `C:/Users/37545/AppData/Roaming/VideoGenProject/qt_wan_chat/downloaded_videos.json`

当前剩余问题：

- 当前 agent 会话不做 GUI 播放器启动断言
- 需要在真实 Windows 桌面中点击本地视频列表的 `Play Selected` 或双击条目，确认默认播放器能打开 mp4

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
- Windows 客户端已用真实任务补过一次终态复验；剩余问题主要是当前 Windows agent 会话访问 `\\wsl$` 输出目录被拒绝，导致 Explorer 成功打开路径仍需在真实桌面权限下补验

### 3. 历史记录：`flash_attn` 本地编译曾触发 WSL 全局 OOM

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
- 这条链路现已降级为历史记录，不再是当前默认交付路径

已知放大因素：

- `setup_wan22.sh` 之前默认 `WAN_FLASH_ATTN_MAX_JOBS=4`
- 同期日志里还能看到 `dockerd` / `containerd` / `postgres` 等常驻进程占用额外内存
- Windows `.wslconfig` 当前虽然已设置：
  - `memory=24GB`
  - `swap=12GB`
  - `processors=12`
  但多路 `cicc` 仍可把 RAM 和 swap 全部耗尽

### 4. 历史记录：更早一轮的 `nvcc` / `CUDA_HOME` 缺失错误

历史错误仍真实存在过：

```text
OSError: CUDA_HOME environment variable is not set. Please set it to your CUDA install root.
flash_attn was requested, but nvcc was not found
```

但根据 `apt` 历史记录，这个阶段已经在真实 WSL 上被推进到“可以真正启动本地编译”。

当前应优先处理的已经不是继续追 `nvcc`，也不是继续做本地编译。

当前缓解状态：

- 编译脚本已经默认降到单并发
- 编译前会先检查 `MemAvailable` / `SwapFree`
- 当前这次真实编译也已转存到仓库内持久源码树 `code/server/wan_local_service/third_party/flash-attn-2.8.3-src`
- 已记录下 `22 / 73` 个 `.o` 目标的当前快照，可以直接续编
- 这可以减少再次把 WSL 打挂的概率，也避免每次都从 `pip` 的临时目录重新开始
- 但当前 workspace 已明确放弃把这条高性能编译链作为默认目标

当前续编入口仅保留作历史参考：

- `cd code/server/wan_local_service`
- `bash scripts/build_flash_attn_resumable.sh status`
- `WAN_FLASH_ATTN_MAX_JOBS=1 bash scripts/build_flash_attn_resumable.sh resume`

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

最新同类错误：

```text
Access to the path '\\wsl$\Ubuntu-24.04\home\liupengkun\VedioGenProject\code\server\wan_local_service\outputs\18439c7f-d91b-42a4-a5f3-2e90624587f8' is denied.
```

影响：

- 客户端已实现 `\\wsl$` 路径转换和错误提示
- 客户端现已对 `\\wsl$` / `\\wsl.localhost` 路径跳过 `QDir.exists()` 预检查，避免当前 agent 权限问题提前拦截 `explorer.exe`
- 但“打开输出目录”的成功路径仍未在本会话真实验证
- 这已不再阻塞结果文件传回客户端，因为服务端已提供 HTTP 下载端点

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

### 8. Windows 客户端长轮询已补真实终态复验，但打开输出目录仍待桌面权限验证

最新真实现象：

- 脚本当前已优先用 `setsid` 启动后台服务
- 本轮在当前 agent 里已真实通过：
  - `run_service.sh start`
  - `run_service.sh status`
  - `curl /healthz`
  - `run_service.sh stop`
- 因此当前 WSL 侧的“后台服务起不来”已不再是主阻塞

当前已完成：

- 用户已启动服务端，本轮未启动或停止服务端
- Windows Qt 客户端真实提交任务：
  - `18439c7f-d91b-42a4-a5f3-2e90624587f8`
- 该任务最终完成：
  - `status=succeeded`
  - `status_message=finished`
  - `progress_current=50`
  - `progress_total=50`
  - `progress_percent=100`
  - `output_path=/home/liupengkun/VedioGenProject/code/server/wan_local_service/outputs/18439c7f-d91b-42a4-a5f3-2e90624587f8/result.mp4`
- `qt_wan_chat.exe --smoke-task-id=18439c7f-d91b-42a4-a5f3-2e90624587f8 --smoke-timeout-ms=10000` 已成功返回终态和 `output_path`

当前剩余问题：

- 第一次 `--smoke-prompt` 使用 45 分钟窗口，任务实际约 46 分 45 秒完成，因此客户端超时窗口偏短；现已把默认窗口提升到 60 分钟
- 当前 Windows agent 对 `\\wsl$` 仍访问被拒绝，无法把 Explorer 成功打开输出目录写成通过

最小修复路径：

- 在真实 Windows 桌面中打开 `code\client\qt_wan_chat\build\qt_wan_chat.exe`
- 选择任务或结果 `18439c7f-d91b-42a4-a5f3-2e90624587f8`
- 点击输出目录按钮，验证 Explorer 是否能打开对应 `\\wsl$` 路径

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
