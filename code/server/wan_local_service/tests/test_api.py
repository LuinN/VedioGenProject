from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.requests import Request

from app.errors import ApiError
from app.main import app, download_result_file
from app.progress import TaskProgressState


def _multipart_task_fields(
    *,
    mode: str,
    prompt: str,
    size: str,
    image: tuple[str, bytes, str] | None = None,
) -> list[tuple[str, object]]:
    fields: list[tuple[str, object]] = [
        ("mode", (None, mode)),
        ("prompt", (None, prompt)),
        ("size", (None, size)),
    ]
    if image is not None:
        filename, content, content_type = image
        fields.append(("image", (filename, content, content_type)))
    return fields


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
    assert payload["mode"] == "t2v"
    assert payload["status"] == "pending"
    assert payload["size"] == "1280*704"
    assert payload["output_path"] is None
    assert payload["input_image_path"] is None
    assert payload["error_message"] is None
    assert payload["log_path"].endswith(".log")


@pytest.mark.anyio
async def test_create_task_accepts_multipart_t2v(service_env: dict[str, Path]) -> None:
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            response = await client.post(
                "/api/tasks",
                files=_multipart_task_fields(
                    mode="t2v",
                    prompt="A quiet river at sunrise",
                    size="1280*704",
                ),
            )

    assert response.status_code == 201
    payload = response.json()
    assert payload["mode"] == "t2v"
    assert payload["status"] == "pending"
    assert payload["input_image_path"] is None


@pytest.mark.anyio
async def test_create_task_accepts_multipart_i2v_and_saves_image(
    service_env: dict[str, Path],
) -> None:
    image_bytes = b"\x89PNG\r\n\x1a\nfake-png"

    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            response = await client.post(
                "/api/tasks",
                files=_multipart_task_fields(
                    mode="i2v",
                    prompt="A fox looking at the camera",
                    size="1280*704",
                    image=("frame.png", image_bytes, "image/png"),
                ),
            )

    assert response.status_code == 201
    payload = response.json()
    assert payload["mode"] == "i2v"
    assert payload["status"] == "pending"
    assert payload["input_image_path"] is not None
    input_image_path = Path(payload["input_image_path"])
    assert input_image_path.exists()
    assert input_image_path.read_bytes() == image_bytes


@pytest.mark.anyio
async def test_error_code_and_status_mappings(service_env: dict[str, Path]) -> None:
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            unsupported_mode = await client.post(
                "/api/tasks",
                json={"mode": "bad-mode", "prompt": "hello", "size": "1280*704"},
            )
            invalid_size = await client.post(
                "/api/tasks",
                json={"mode": "t2v", "prompt": "hello", "size": "999*999"},
            )
            validation = await client.post(
                "/api/tasks",
                json={"mode": "t2v", "prompt": "   ", "size": "1280*704"},
            )
            image_not_allowed = await client.post(
                "/api/tasks",
                files=_multipart_task_fields(
                    mode="t2v",
                    prompt="hello",
                    size="1280*704",
                    image=("frame.png", b"fake", "image/png"),
                ),
            )
            missing = await client.get("/api/tasks/missing-task")

    assert unsupported_mode.status_code == 400
    assert unsupported_mode.json()["error"]["code"] == "unsupported_mode"
    assert invalid_size.status_code == 400
    assert invalid_size.json()["error"]["code"] == "invalid_size"
    assert validation.status_code == 422
    assert validation.json()["error"]["code"] == "validation_error"
    assert image_not_allowed.status_code == 422
    assert image_not_allowed.json()["error"]["code"] == "validation_error"
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "task_not_found"


@pytest.mark.anyio
async def test_create_i2v_requires_image(service_env: dict[str, Path]) -> None:
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            response = await client.post(
                "/api/tasks",
                files=_multipart_task_fields(
                    mode="i2v",
                    prompt="missing image prompt",
                    size="1280*704",
                ),
            )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "image_required"


@pytest.mark.anyio
async def test_create_i2v_rejects_unsupported_image_type(
    service_env: dict[str, Path],
) -> None:
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            response = await client.post(
                "/api/tasks",
                files=_multipart_task_fields(
                    mode="i2v",
                    prompt="bad image prompt",
                    size="1280*704",
                    image=("frame.gif", b"GIF89a", "image/gif"),
                ),
            )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "image_not_supported"


@pytest.mark.anyio
async def test_create_i2v_rejects_oversized_image(
    service_env: dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WAN_MAX_INPUT_IMAGE_BYTES", "1024")
    oversized_image = b"a" * 1025

    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            response = await client.post(
                "/api/tasks",
                files=_multipart_task_fields(
                    mode="i2v",
                    prompt="large image prompt",
                    size="1280*704",
                    image=("frame.png", oversized_image, "image/png"),
                ),
            )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "image_too_large"


@pytest.mark.anyio
async def test_task_detail_and_results_respect_null_and_output_flags(
    service_env: dict[str, Path],
) -> None:
    output_path = service_env["outputs_dir"] / "task-succeeded" / "result.mp4"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("video", encoding="utf-8")
    input_image_path = service_env["outputs_dir"] / "task-pending" / "input_image.png"
    input_image_path.parent.mkdir(parents=True, exist_ok=True)
    input_image_path.write_bytes(b"\x89PNG\r\n\x1a\nfake-png")

    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            repository = app.state.service_context.repository
            pending = repository.create_task(
                task_id="task-pending",
                mode="i2v",
                prompt="pending prompt",
                size="1280*704",
                log_path=str(service_env["logs_dir"] / "task-pending.log"),
                input_image_path=str(input_image_path.resolve()),
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
    assert detail_payload["mode"] == "i2v"
    assert detail_payload["status"] == "pending"
    assert detail_payload["size"] == "1280*704"
    assert detail_payload["output_path"] is None
    assert detail_payload["input_image_path"] == str(input_image_path.resolve())
    assert detail_payload["input_image_exists"] is True
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
async def test_task_progress_endpoint_returns_persisted_progress(
    service_env: dict[str, Path],
) -> None:
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            repository = app.state.service_context.repository
            task = repository.create_task(
                task_id="task-progress-endpoint",
                mode="t2v",
                prompt="progress endpoint prompt",
                size="1280*704",
                log_path=str(service_env["logs_dir"] / "task-progress-endpoint.log"),
            )
            repository.mark_task_running(task.task_id)
            repository.update_task_progress(
                task.task_id,
                TaskProgressState(
                    status_message="sampling",
                    progress_current=9,
                    progress_total=50,
                    progress_percent=18,
                ),
            )

            progress_response = await client.get(f"/api/tasks/{task.task_id}/progress")
            detail_response = await client.get(f"/api/tasks/{task.task_id}")

    assert progress_response.status_code == 200
    progress_payload = progress_response.json()
    assert progress_payload["task_id"] == task.task_id
    assert progress_payload["status"] == "running"
    assert progress_payload["output_exists"] is False
    assert progress_payload["status_message"] == "sampling"
    assert progress_payload["progress_current"] == 9
    assert progress_payload["progress_total"] == 50
    assert progress_payload["progress_percent"] == 18
    assert progress_payload["download_url"] is None

    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload["status_message"] == "sampling"
    assert detail_payload["progress_current"] == 9
    assert detail_payload["progress_total"] == 50
    assert detail_payload["progress_percent"] == 18


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
