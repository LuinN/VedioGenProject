# BLOCKERS

## 当前真实阻塞

### 1. Windows 客户端与服务端最终契约仍存在漂移

当前服务端主线：

- 只支持 `mode=i2v`
- 不实现 `/api/capabilities`
- 固定 `backend="comfyui_native"`

当前风险：

- Windows 客户端如果仍请求 `/api/capabilities`，会拿到 `404`
- Windows 客户端如果仍提交 `t2v`，会拿到 `unsupported_mode`
- Windows 客户端如果仍按多 profile 形态驱动 UI，会与当前服务端收口后的协议冲突

影响：

- 在客户端同步新契约前，不能把 Win/WSL 联调视为已最终打通

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
