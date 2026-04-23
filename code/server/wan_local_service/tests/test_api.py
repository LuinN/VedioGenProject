from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


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

    assert results_response.status_code == 200
    result_payload = results_response.json()
    assert result_payload["total"] == 1
    assert result_payload["items"][0]["task_id"] == "task-succeeded"
    assert result_payload["items"][0]["output_exists"] is True

    assert tasks_response.status_code == 200
    task_list_payload = tasks_response.json()
    assert task_list_payload["total"] >= 2
    assert "output_exists" not in task_list_payload["items"][0]
