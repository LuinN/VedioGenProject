# 2026-04-24 Result Download API

## Purpose

为 Windows Qt 客户端补一条不依赖 `\\wsl$` 的结果获取路径：服务端在任务成功后直接通过 HTTP 返回 `mp4` 文件，客户端可将其保存到 Windows 本地目录。

## Implemented

- `GET /api/results/{task_id}/file`
  - 成功时返回 `video/mp4`
  - 响应头包含 `Content-Disposition: attachment; filename="<task_id>.mp4"`
- `GET /api/tasks/{task_id}` 新增 `download_url`
- `GET /api/results` 新增 `download_url`
- 稳定错误码新增：
  - `result_not_ready`
  - `result_file_missing`

## Verification

Executed:

```bash
cd code/server/wan_local_service
PYTHONPATH=. pytest -q tests/test_api.py
```

Result:

```text
.........                                                                [100%]
9 passed in 0.54s
```

新增覆盖点：

- 成功下载已完成任务的视频响应
- 未完成任务返回 `result_not_ready`
- 结果文件缺失返回 `result_file_missing`

真实后台服务复验：

```bash
bash code/server/wan_local_service/scripts/run_service.sh start
curl --noproxy '*' --silent --show-error \
  http://127.0.0.1:8000/api/tasks/18439c7f-d91b-42a4-a5f3-2e90624587f8
curl --noproxy '*' --silent --show-error --output /tmp/18439c7f.mp4 \
  http://127.0.0.1:8000/api/results/18439c7f-d91b-42a4-a5f3-2e90624587f8/file
ffprobe -v error -show_entries format=duration,size \
  -show_entries stream=codec_name,width,height,nb_frames \
  -of json /tmp/18439c7f.mp4
```

真实结果：

- 任务详情已返回 `download_url`
- 下载后的文件大小：`8060815` bytes
- `ffprobe` 确认：
  - `codec_name=h264`
  - `width=1280`
  - `height=704`
  - `nb_frames=121`
  - `duration=5.041667`

## Current Handoff

WSL 服务端协议已具备“把视频传回客户端”的能力。下一步由 Windows 客户端接入 `download_url`，并将返回的 `mp4` 保存到用户选择的本地目录。
