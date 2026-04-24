from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.requests import Request

from app.errors import ApiError
from app.main import app, download_result_file


def _download_request(task_id: str) -> Request:
    return Request(
        {
            "type": "http",
            "app": app,
            "scheme": "http",
            "method": "GET",
            "path": f"/api/results/{task_id}/file",
            "raw_path": f"/api/results/{task_id}/file".encode("utf-8"),
            "query_string": b"",
            "headers": [],
            "server": ("testserver", 80),
            "client": ("testclient", 50000),
            "root_path": "",
        }
    )


@pytest.mark.anyio
async def test_healthz(service_env: dict[str, Path]) -> None:
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            response = await client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"ok": True, "service": "wan-local-service"}


@pytest.mark.anyio
async def test_create_task_uses_null_semantics(service_env: dict[str, Path]) -> None:
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            response = await client.post(
                "/api/tasks",
                json={
                    "mode": "t2v",
                    "prompt": "A cinematic cyberpunk street at night",
                    "size": "1280*704",
                },
            )

    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == "pending"
    assert payload["output_path"] is None
    assert payload["error_message"] is None
    assert payload["log_path"].endswith(".log")


@pytest.mark.anyio
async def test_error_code_and_status_mappings(service_env: dict[str, Path]) -> None:
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            unsupported_mode = await client.post(
                "/api/tasks",
                json={"mode": "i2v", "prompt": "hello", "size": "1280*704"},
            )
            invalid_size = await client.post(
                "/api/tasks",
                json={"mode": "t2v", "prompt": "hello", "size": "999*999"},
            )
            validation = await client.post(
                "/api/tasks",
                json={"mode": "t2v", "prompt": "   ", "size": "1280*704"},
            )
            missing = await client.get("/api/tasks/missing-task")

    assert unsupported_mode.status_code == 400
    assert unsupported_mode.json()["error"]["code"] == "unsupported_mode"
    assert invalid_size.status_code == 400
    assert invalid_size.json()["error"]["code"] == "invalid_size"
    assert validation.status_code == 422
    assert validation.json()["error"]["code"] == "validation_error"
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "task_not_found"


@pytest.mark.anyio
async def test_task_detail_and_results_respect_null_and_output_flags(
    service_env: dict[str, Path],
) -> None:
    output_path = service_env["outputs_dir"] / "task-succeeded" / "result.mp4"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("video", encoding="utf-8")

    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            repository = app.state.service_context.repository
            pending = repository.create_task(
                task_id="task-pending",
                mode="t2v",
                prompt="pending prompt",
                size="1280*704",
                log_path=str(service_env["logs_dir"] / "task-pending.log"),
            )
            succeeded = repository.create_task(
                task_id="task-succeeded",
                mode="t2v",
                prompt="done prompt",
                size="1280*704",
                log_path=str(service_env["logs_dir"] / "task-succeeded.log"),
            )
            repository.mark_task_succeeded(succeeded.task_id, str(output_path))

            detail_response = await client.get(f"/api/tasks/{pending.task_id}")
            results_response = await client.get("/api/results")
            tasks_response = await client.get("/api/tasks")

    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload["status"] == "pending"
    assert detail_payload["output_path"] is None
    assert detail_payload["error_message"] is None
    assert detail_payload["output_exists"] is False
    assert detail_payload["download_url"] is None

    assert results_response.status_code == 200
    result_payload = results_response.json()
    assert result_payload["total"] == 1
    assert result_payload["items"][0]["task_id"] == "task-succeeded"
    assert result_payload["items"][0]["output_exists"] is True
    assert result_payload["items"][0]["download_url"].endswith(
        "/api/results/task-succeeded/file"
    )

    assert tasks_response.status_code == 200
    task_list_payload = tasks_response.json()
    assert task_list_payload["total"] >= 2
    assert "output_exists" not in task_list_payload["items"][0]


@pytest.mark.anyio
async def test_task_detail_reports_runtime_progress(
    service_env: dict[str, Path],
) -> None:
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            repository = app.state.service_context.repository
            task = repository.create_task(
                task_id="task-running-progress",
                mode="t2v",
                prompt="progress prompt",
                size="1280*704",
                log_path=str(service_env["logs_dir"] / "task-running-progress.log"),
            )
            repository.mark_task_running(task.task_id)
            Path(task.log_path).write_text(
                "\n".join(
                    [
                        "[2026-04-24 11:24:03,984] INFO: Creating WanTI2V pipeline.",
                        "[2026-04-24 11:25:08,005] INFO: Generating video ...",
                        " 42%|████▏     | 21/50 [07:18<09:31, 19.72s/it]",
                    ]
                ),
                encoding="utf-8",
            )

            detail_response = await client.get(f"/api/tasks/{task.task_id}")

    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload["status"] == "running"
    assert detail_payload["output_exists"] is False
    assert detail_payload["status_message"] == "sampling"
    assert detail_payload["progress_current"] == 21
    assert detail_payload["progress_total"] == 50
    assert detail_payload["progress_percent"] == 42


@pytest.mark.anyio
async def test_startup_and_results_reconcile_running_task_with_output(
    repository,
    service_env: dict[str, Path],
) -> None:
    task = repository.create_task(
        task_id="task-recovered-output",
        mode="t2v",
        prompt="recovered prompt",
        size="1280*704",
        log_path=str(service_env["logs_dir"] / "task-recovered-output.log"),
    )
    repository.mark_task_running(task.task_id)
    output_path = service_env["outputs_dir"] / task.task_id / "result.mp4"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("video", encoding="utf-8")

    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            detail_response = await client.get(f"/api/tasks/{task.task_id}")
            results_response = await client.get("/api/results")

    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload["status"] == "succeeded"
    assert detail_payload["output_path"] == str(output_path.resolve())
    assert detail_payload["output_exists"] is True
    assert detail_payload["progress_percent"] == 100
    assert detail_payload["download_url"].endswith(
        f"/api/results/{task.task_id}/file"
    )

    assert results_response.status_code == 200
    result_payload = results_response.json()
    assert result_payload["total"] == 1
    assert result_payload["items"][0]["task_id"] == task.task_id
    assert result_payload["items"][0]["download_url"].endswith(
        f"/api/results/{task.task_id}/file"
    )


@pytest.mark.anyio
async def test_result_download_returns_video_file(service_env: dict[str, Path]) -> None:
    output_path = service_env["outputs_dir"] / "task-downloadable" / "result.mp4"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    video_bytes = b"fake-mp4-binary"
    output_path.write_bytes(video_bytes)

    async with app.router.lifespan_context(app):
        repository = app.state.service_context.repository
        task = repository.create_task(
            task_id="task-downloadable",
            mode="t2v",
            prompt="download prompt",
            size="1280*704",
            log_path=str(service_env["logs_dir"] / "task-downloadable.log"),
        )
        repository.mark_task_succeeded(task.task_id, str(output_path.resolve()))
        response = await download_result_file(_download_request(task.task_id), task.task_id)

    assert response.status_code == 200
    assert response.body == video_bytes
    assert response.media_type == "video/mp4"
    assert "attachment; filename=\"task-downloadable.mp4\"" in response.headers[
        "content-disposition"
    ]
    assert response.headers["content-length"] == str(len(video_bytes))


@pytest.mark.anyio
async def test_result_download_rejects_unsucceeded_task(
    service_env: dict[str, Path],
) -> None:
    async with app.router.lifespan_context(app):
        repository = app.state.service_context.repository
        task = repository.create_task(
            task_id="task-not-ready",
            mode="t2v",
            prompt="pending prompt",
            size="1280*704",
            log_path=str(service_env["logs_dir"] / "task-not-ready.log"),
        )

        with pytest.raises(ApiError) as exc_info:
            await download_result_file(_download_request(task.task_id), task.task_id)

    assert exc_info.value.code == "result_not_ready"
    assert exc_info.value.status_code == 409


@pytest.mark.anyio
async def test_result_download_rejects_missing_output_file(
    service_env: dict[str, Path],
) -> None:
    output_path = service_env["outputs_dir"] / "task-missing-file" / "result.mp4"

    async with app.router.lifespan_context(app):
        repository = app.state.service_context.repository
        task = repository.create_task(
            task_id="task-missing-file",
            mode="t2v",
            prompt="missing file prompt",
            size="1280*704",
            log_path=str(service_env["logs_dir"] / "task-missing-file.log"),
        )
        repository.mark_task_succeeded(task.task_id, str(output_path.resolve()))

        with pytest.raises(ApiError) as exc_info:
            await download_result_file(_download_request(task.task_id), task.task_id)

    assert exc_info.value.code == "result_file_missing"
    assert exc_info.value.status_code == 404
