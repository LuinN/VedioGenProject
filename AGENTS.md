# AGENTS.md

## 1. 文档目的

本文件用于约束本项目中 Codex 的执行边界、目录职责、跨 Win/WSL 协作方式、状态文档维护要求与交付标准。

本项目采用 **双执行位协作模式**：

- **Windows Codex**
  - 负责 Windows 原生工具链相关工作
  - 主要负责 Qt6 客户端开发、Windows 侧编译与联调
- **WSL Codex**
  - 负责 Linux / WSL 原生工具链相关工作
  - 主要负责 Wan2.2 模型部署、FastAPI 服务、本地推理链路

除非任务明确要求，不要跨边界接管对方职责。

---

## 2. 总体架构原则

本项目采用以下固定架构：

- **Windows 侧**
  - Qt6 + CMake + Widgets 桌面客户端
  - 仅负责 UI、交互、HTTP 调用、状态展示、结果展示
  - 不直接运行模型推理
- **WSL 侧**
  - Python + FastAPI 本地服务
  - 负责任务管理、日志记录、调用 Wan2.2 官方推理脚本
- **模型执行**
  - 统一由 WSL 侧完成
  - 统一使用官方 Wan2.2 主路径
  - MVP 阶段仅支持 `Wan2.2-TI2V-5B`

禁止把模型推理直接塞进 Qt 主进程。

---

## 3. 目录职责边界

默认目录结构如下：

```text
project/
  AGENTS.md
  STATUS.md
  BLOCKERS.md
  NEXT_STEP.md

  code/
    client/
      qt_wan_chat/
    server/
      wan_local_service/

  docs/
    reports/
      self_test/
        client/
        server/
      integration/
```

### 3.1 Windows Codex 允许修改的主目录

- `code/client/qt_wan_chat/**`
- `docs/reports/self_test/client/**`
- `docs/reports/integration/**`
- `STATUS.md`
- `BLOCKERS.md`
- `NEXT_STEP.md`

### 3.2 WSL Codex 允许修改的主目录

- `code/server/wan_local_service/**`
- `docs/reports/self_test/server/**`
- `docs/reports/integration/**`
- `STATUS.md`
- `BLOCKERS.md`
- `NEXT_STEP.md`

### 3.3 双方共享可读目录

- `AGENTS.md`
- `STATUS.md`
- `BLOCKERS.md`
- `NEXT_STEP.md`
- `docs/reports/integration/**`

### 3.4 修改限制

- **Windows Codex 不应主动重构服务端目录**
- **WSL Codex 不应主动重构客户端目录**
- 如需跨目录修改，必须是为了：
  - 修复接口契约不一致
  - 修复联调阻塞
  - 补齐最小运行所需文件
- 不允许无必要的大范围改名、迁移、清空目录

---

## 4. Windows Codex 职责

Windows Codex 负责以下事项：

### 4.1 Qt 客户端开发
- Qt6
- CMake
- Widgets
- QNetworkAccessManager
- Windows 原生编译与运行验证

### 4.2 客户端功能范围
- 主窗口
- 三栏布局
- 聊天消息区
- 输入框
- 发送按钮
- 任务列表
- 结果列表
- 配置区
- 调用本地 HTTP 服务
- 轮询任务状态
- 打开输出目录

### 4.3 Windows 专属联调职责
- 使用真实 Windows Qt6 工具链构建
- 修复 Qt/CMake/链接/插件/路径问题
- 负责 `\\wsl$\<distro>\...` 路径转换与 `explorer.exe` 打开目录逻辑
- 验证 Windows 客户端访问 WSL 服务端的本地地址

### 4.4 Windows Codex 禁止事项
- 不要尝试在 Qt 客户端里直接加载 Wan2.2 模型
- 不要把 Python 推理逻辑嵌入 Qt 进程
- 不要自行重写服务端推理逻辑
- 不要把客户端改成 Electron / Web 前端 / QML，除非明确收到修改指令

---

## 5. WSL Codex 职责

WSL Codex 负责以下事项：

### 5.1 Wan2.2 模型与服务端
- Wan2.2 官方仓库接入
- 模型目录与权重目录整理
- FastAPI 服务开发
- SQLite 或轻量持久化
- 任务执行器
- 调用官方 `generate.py`
- 服务端脚本与 README

### 5.2 服务端功能范围
- `GET /healthz`
- `POST /api/tasks`
- `GET /api/tasks/{task_id}`
- `GET /api/tasks`
- `GET /api/results`

### 5.3 推理执行原则
- 严格沿用官方 Wan2.2 主路径
- MVP 仅支持 `mode=t2v`
- 内部模型固定为 `Wan2.2-TI2V-5B`
- 优先确保 3090 24GB 可跑通
- 优先保守参数，不优先追求最高画质

### 5.4 WSL Codex 禁止事项
- 不要接管 Qt UI 主开发
- 不要为了“方便”把服务端改成 Windows 原生专用脚本
- 不要引入 Redis / Celery / Postgres 等重型依赖作为 MVP 前置
- 不要把模型权重纳入仓库版本控制

---

## 6. Win/WSL 协作规则

### 6.1 接口契约优先
客户端与服务端通过 HTTP 交互。  
联调时以服务端接口契约为准，客户端不得臆造字段；服务端不得随意破坏已承诺字段。

### 6.2 共享字段最小集合

创建任务请求最小字段：
- `mode`
- `prompt`
- `size`

任务详情最小字段：
- `task_id`
- `status`
- `prompt`
- `output_path`
- `error_message`
- `log_path`

结果列表最小字段：
- `task_id`
- `output_path`
- `create_time`

### 6.3 联调变更规则
如果接口字段、端口、目录结构有变化：

1. 先更新对应代码
2. 再更新 `STATUS.md`
3. 如造成阻塞，写入 `BLOCKERS.md`
4. 给出下一步动作到 `NEXT_STEP.md`

不要只改代码，不改文档状态。

---

## 7. 状态文档维护规则

以下文件是本项目长期必维护文件：

- `STATUS.md`
- `BLOCKERS.md`
- `NEXT_STEP.md`

### 7.1 STATUS.md
记录当前已完成内容、当前主路径状态、最近一次重要进展。

### 7.2 BLOCKERS.md
记录真实阻塞项，必须写真实错误，不允许淡化或伪造通过。

例如：
- WSL 中 `nvidia-smi` 不可用
- GPU access blocked by the operating system
- Wan 权重未下载完成
- Windows Qt6 工具链未就绪
- 客户端与服务端接口字段不一致

### 7.3 NEXT_STEP.md
只写下一步最小可执行动作，不写泛泛规划。

---

## 8. MVP 范围约束

当前 MVP 固定目标：

- 打通“Qt 输入 prompt -> FastAPI 创建任务 -> Wan2.2 本地推理 -> Qt 展示任务状态和输出路径”的闭环

### 当前明确只做
- `Wan2.2-TI2V-5B`
- 文生视频 `t2v`
- Windows Qt Widgets 客户端
- WSL FastAPI 服务
- 单机串行任务执行

### 当前明确不做
- A14B
- 多模型切换
- Docker
- 云端部署
- 用户系统
- 鉴权
- Electron
- QML
- 客户端直连模型
- 复杂任务调度
- 复杂美术打磨

---

## 9. 路径与环境原则

### 9.1 路径原则
- 所有路径必须配置化
- 不要写死个人用户名路径
- Windows 与 WSL 路径转换必须显式处理
- 输出目录必须可追踪、可打开

### 9.2 环境原则
- Windows 原生工具链相关问题，由 Windows Codex 主处理
- WSL/Linux 原生工具链相关问题，由 WSL Codex 主处理
- 如果某侧环境缺失，必须如实记录到 `BLOCKERS.md`

---

## 10. 测试与报告原则

必须保留以下报告目录：

- `docs/reports/self_test/client/`
- `docs/reports/self_test/server/`
- `docs/reports/integration/`

### 10.1 客户端报告
记录：
- 编译结果
- 运行结果
- 聊天发送流程
- 状态轮询流程
- 成功/失败展示逻辑

### 10.2 服务端报告
记录：
- 环境检查
- 接口测试
- 真实推理结果
- 日志与输出路径
- 真实报错

### 10.3 集成报告
记录：
- Windows 访问的服务地址
- task_id
- 输出文件路径
- 客户端与服务端联调结果
- 当前已知问题

---

## 11. 执行优先级

所有 Codex 执行都应遵循以下优先级：

1. 先保证主链路闭环
2. 先保证真实可运行
3. 先保证结构清晰
4. 再考虑体验优化
5. 再考虑扩展能力

禁止一开始发散做复杂优化。

---

## 12. 真实原则

- 不允许伪造“已跑通”
- 不允许伪造“已测试通过”
- 不允许把 stub 测试写成真实推理完成
- 不允许隐瞒 blocker
- 如果用户要求“提交代码”，默认语义是：
  - 先完成本地 `git commit`
  - 再把对应提交 `push` 到远端
  - 只有在明确说明“只本地提交、不推远端”时，才停止在本地 commit
- 无法完成时，必须交付：
  - 已完成代码
  - 已完成脚本
  - 当前真实报错
  - 最小修复路径

---

## 13. 推荐工作方式

### 13.1 Windows Codex
适合在 Windows 原生 agent 下执行，直接使用本机 Qt6 环境。

### 13.2 WSL Codex
适合在 WSL2 agent 下执行，直接使用 Linux 环境完成 Wan2.2 与 FastAPI 部署。

在 Windows 环境下，如果项目和工具链位于 WSL，可切换 agent 到 WSL。反之，如果工具链在 Windows，本地原生执行更合适。  
因此本项目推荐：
- Qt 客户端：Windows agent
- Wan/FastAPI 服务：WSL agent
