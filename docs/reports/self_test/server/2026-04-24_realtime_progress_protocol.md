# 2026-04-24 Realtime Progress Protocol

## Purpose

把 Wan2.2 的阶段日志和 `tqdm` 采样步数实时透传到服务端，并提供一个比 `GET /api/tasks/{task_id}` 更轻的进度轮询接口。

## Implemented

- `WanRunner` 现在以非缓冲模式启动 `generate.py`
  - 命令行增加 `-u`
  - 子进程环境增加 `PYTHONUNBUFFERED=1`
- `WanRunner` 不再只按换行读取输出
  - 会同时按 `\r` 和 `\n` 拆分记录
  - `tqdm` 的采样进度会被实时落到任务日志
- 任务表新增持久化进度字段：
  - `status_message`
  - `progress_current`
  - `progress_total`
  - `progress_percent`
- `update_time` 会在进度推进时刷新
- 新增轻量接口：
  - `GET /api/tasks/{task_id}/progress`
- 原有 `GET /api/tasks/{task_id}` 也会优先返回持久化进度，保留兼容

## Verification

Executed:

```bash
cd code/server/wan_local_service
PYTHONPATH=. pytest -q tests/test_api.py tests/test_repository.py tests/test_task_runner.py tests/test_wan_runner.py
```

Result:

```text
....................                                                     [100%]
20 passed in 1.17s
```

覆盖点：

- repository 层持久化实时进度
- task runner 把 WanRunner 的进度回调写回 SQLite
- wan runner 实时解析 `Creating WanTI2V pipeline.`、`Generating video ...` 和 `tqdm` 步数
- 轻量进度接口 `GET /api/tasks/{task_id}/progress`

## Live Verification

后台服务已重启到新代码：

```bash
bash code/server/wan_local_service/scripts/run_service.sh stop
bash code/server/wan_local_service/scripts/run_service.sh start
```

真实查询：

```bash
curl --noproxy '*' --silent --show-error \
  http://127.0.0.1:8000/api/tasks/0dfbe405-19cb-4256-a86b-13c49569a5b5/progress
```

真实结果：

```json
{
  "task_id": "0dfbe405-19cb-4256-a86b-13c49569a5b5",
  "status": "succeeded",
  "update_time": "2026-04-24T15:02:14+00:00",
  "output_exists": true,
  "error_message": null,
  "status_message": "finished",
  "progress_current": 50,
  "progress_total": 50,
  "progress_percent": 100,
  "download_url": "http://127.0.0.1:8000/api/results/0dfbe405-19cb-4256-a86b-13c49569a5b5/file"
}
```

## Current Handoff

WSL 服务端已经具备稳定的阶段/步数进度链路。Windows 客户端后续可以继续沿用 `GET /api/tasks/{task_id}`，也可以切到更轻的 `GET /api/tasks/{task_id}/progress`。
