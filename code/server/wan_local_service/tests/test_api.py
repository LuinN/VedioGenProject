from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


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


@pytest.mark.anyio
async def test_healthz_reports_backend_readiness(
    service_env: dict[str, Path],
    install_fake_comfyui,
) -> None:
    install_fake_comfyui("success")
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            response = await client.get("/healthz")

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["backend"] == "comfyui_native"
    assert response.json()["backend_ready"] is True
    assert response.json()["model_ready"] is True


@pytest.mark.anyio
async def test_create_task_rejects_json_requests(
    service_env: dict[str, Path],
) -> None:
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            response = await client.post(
                "/api/tasks",
                json={"mode": "i2v", "prompt": "hello", "size": "832*480"},
            )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


@pytest.mark.anyio
async def test_create_task_rejects_t2v(
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
                    mode="t2v",
                    prompt="hello",
                    size="832*480",
                ),
            )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "unsupported_mode"


@pytest.mark.anyio
async def test_create_i2v_task_persists_backend_fields_and_image(
    service_env: dict[str, Path],
    install_fake_comfyui,
) -> None:
    install_fake_comfyui("success")
    image_bytes = b"\x89PNG\r\n\x1a\nfake-png"

    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            create_response = await client.post(
                "/api/tasks",
                files=_multipart_task_fields(
                    mode="i2v",
                    prompt="A fox looking at the camera",
                    size="832*480",
                    image=("frame.png", image_bytes, "image/png"),
                ),
            )

            task_id = create_response.json()["task_id"]
            detail_response = await client.get(f"/api/tasks/{task_id}")

    assert create_response.status_code == 201
    payload = create_response.json()
    assert payload["mode"] == "i2v"
    assert payload["status"] == "pending"
    assert payload["backend"] == "comfyui_native"
    assert payload["backend_prompt_id"] is None
    assert payload["failure_code"] is None
    assert payload["input_image_path"] is not None
    input_image_path = Path(payload["input_image_path"])
    assert input_image_path.exists()
    assert input_image_path.read_bytes() == image_bytes

    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["backend"] == "comfyui_native"
    assert detail["input_image_exists"] is True


@pytest.mark.anyio
async def test_create_i2v_rejects_invalid_size(
    service_env: dict[str, Path],
    install_fake_comfyui,
) -> None:
    install_fake_comfyui("success")

    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            response = await client.post(
                "/api/tasks",
                files=_multipart_task_fields(
                    mode="i2v",
                    prompt="bad size prompt",
                    size="1280*704",
                    image=("frame.png", b"fake", "image/png"),
                ),
            )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_size"
