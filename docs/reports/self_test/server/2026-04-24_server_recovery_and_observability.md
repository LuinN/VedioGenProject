# 2026-04-24 服务端恢复与可观测性增强记录

## 目标

- 继续完善服务端主链路，解决“长任务不可观测”和“任务实际已出片但状态未回填”的阻塞

## 本轮关键改动

- `app/task_runtime.py`
  - 新增任务运行态解析：
    - 从 `logs/<task_id>.log` 提取 `status_message`
    - 从 tqdm 行提取 `progress_current / progress_total / progress_percent`
  - 新增恢复逻辑：
    - 如果 `outputs/<task_id>/result.mp4` 已存在，优先把遗留 `pending/running` 回填成 `succeeded`
- `app/main.py`
  - `GET /api/tasks/{task_id}` 现在会返回：
    - `output_exists`
    - `status_message`
    - `progress_current`
    - `progress_total`
    - `progress_percent`
  - 读取任务详情时会先做一次“输出文件存在 -> 自动回填成功”的 reconcile
  - 服务启动恢复时改成“先看输出文件，再决定是否标失败”
- `scripts/run_sample_t2v.sh`
  - 默认等待窗口提高到 40 分钟
  - 轮询时会打印 `stage` 和采样进度
- `scripts/run_service.sh`
  - 后台启动时优先使用 `setsid`
  - 停止超时后会强制回收 PID

## 验证

### 单测与语法检查

执行：

```bash
cd code/server/wan_local_service
.venv/bin/python -m py_compile app/main.py app/task_runtime.py app/repository.py app/wan_runner.py app/schemas.py
PYTHONPATH=$PWD .venv/bin/python -m pytest tests -q
```

结果：

- `py_compile` 通过
- `17 passed`

### 后台服务脚本复验

执行：

```bash
bash code/server/wan_local_service/scripts/run_service.sh start
bash code/server/wan_local_service/scripts/run_service.sh status
curl --noproxy '*' --fail --silent --show-error http://127.0.0.1:8000/healthz
bash code/server/wan_local_service/scripts/run_service.sh stop
```

结果：

- `run_service.sh start` 返回 `Service started in background`
- `run_service.sh status` 返回 `Service is running`
- `/healthz` 返回 `{"ok":true,"service":"wan-local-service"}`
- `run_service.sh stop` 返回 `Service stopped`

## 当前结论

- 服务端当前已经具备：
  - 真实出片能力
  - 长任务进度可观测性
  - 输出文件驱动的任务状态自动修正
  - 可复验的后台服务起停能力
- 当前剩余阻塞已进一步收敛到：
  - Windows Qt 客户端对长任务轮询的真实闭环复验
  - `flash_attn` 高性能路径仍未编完
