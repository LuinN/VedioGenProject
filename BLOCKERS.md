# BLOCKERS

## 当前真实阻塞

### 1. Windows 客户端尚未完成当前契约的真实端到端联调

当前事实：

- 客户端代码已同步服务端当前单模型 `i2v` 契约
- Windows 原生 Qt/MinGW 构建与 release 打包已通过
- 还没有用当前客户端对正在运行的 WSL 服务端重新提交一条真实 `i2v` 生成任务

当前风险：

- 代码级契约已经对齐，但真实用户链路仍需重新验证：
  - Windows Qt 客户端选择图片
  - `POST /api/tasks(mode=i2v, image, prompt, size)`
  - 轮询任务状态
  - 下载并播放 `result.mp4`

影响：

- 在完成上述真实联调前，不能把当前客户端最终形态视为已完整验收

### 2. `AGENTS.md` 仍保留早期 5B MVP 文字

当前冲突：

- `AGENTS.md` 仍写：
  - 官方 `generate.py`
  - MVP 仅 `Wan2.2-TI2V-5B`
  - MVP 仅 `t2v`
- 当前服务端实际主线已切到：
  - `ComfyUI`
  - `Wan2.2 I2V-A14B`
  - 单模型 `i2v`

影响：

- 仓库协作约束文本与当前服务端产品目标不一致
- 后续 Win/WSL 协作仍可能被旧约束误导

### 3. ComfyUI 后台进程管理仍需收敛

当前事实：

- 真实 14B 任务已经成功跑通
- 但重复执行启动脚本时仍出现过：
  - `database lock`
  - `port already in use`

影响：

- 不会阻止当前服务端真实出片
- 但会增加重复自测和后续自动化的混乱度
