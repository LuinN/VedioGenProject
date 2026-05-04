from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Callable

import httpx
import pytest
from websocket import WebSocketConnectionClosedException

import app.comfyui_backend as comfyui_backend_module
import app.comfyui_manager as comfyui_manager_module
from app.db import init_db
from app.repository import TaskRepository


WORKFLOW_TEMPLATE_PATH = (
    Path(__file__).resolve().parents[1]
    / "workflows"
    / "wan22_i2v_a14b_lowvram_template.json"
)


def fake_object_info() -> dict[str, Any]:
    return {
        "LoadImage": {
            "input": {"required": {"image": ["STRING"], "upload": ["STRING"]}},
            "input_order": {"required": ["image", "upload"], "optional": []},
        },
        "CLIPLoader": {
            "input": {
                "required": {
                    "clip_name": ["COMBO"],
                    "type": ["STRING"],
                    "device": ["STRING"],
                }
            },
            "input_order": {"required": ["clip_name", "type", "device"], "optional": []},
        },
        "CLIPTextEncode": {
            "input": {"required": {"clip": ["CLIP"], "text": ["STRING"]}},
            "input_order": {"required": ["clip", "text"], "optional": []},
        },
        "VAELoader": {
            "input": {"required": {"vae_name": ["COMBO"]}},
            "input_order": {"required": ["vae_name"], "optional": []},
        },
        "UNETLoader": {
            "input": {"required": {"unet_name": ["COMBO"], "device": ["STRING"]}},
            "input_order": {"required": ["unet_name", "device"], "optional": []},
        },
        "ModelSamplingSD3": {
            "input": {"required": {"model": ["MODEL"], "shift": ["FLOAT"]}},
            "input_order": {"required": ["model", "shift"], "optional": []},
        },
        "WanImageToVideo": {
            "input": {
                "required": {
                    "positive": ["CONDITIONING"],
                    "negative": ["CONDITIONING"],
                    "vae": ["VAE"],
                    "clip_vision_output": ["CLIP_VISION_OUTPUT"],
                    "start_image": ["IMAGE"],
                    "width": ["INT"],
                    "height": ["INT"],
                    "length": ["INT"],
                    "batch_size": ["INT"],
                }
            },
            "input_order": {
                "required": [
                    "positive",
                    "negative",
                    "vae",
                    "clip_vision_output",
                    "start_image",
                    "width",
                    "height",
                    "length",
                    "batch_size",
                ],
                "optional": [],
            },
        },
        "KSamplerAdvanced": {
            "input": {
                "required": {
                    "model": ["MODEL"],
                    "add_noise": ["STRING"],
                    "noise_seed": ["INT"],
                    "steps": ["INT"],
                    "cfg": ["FLOAT"],
                    "sampler_name": ["STRING"],
                    "scheduler": ["STRING"],
                    "positive": ["CONDITIONING"],
                    "negative": ["CONDITIONING"],
                    "latent_image": ["LATENT"],
                    "start_at_step": ["INT"],
                    "end_at_step": ["INT"],
                    "return_with_leftover_noise": ["STRING"],
                }
            },
            "input_order": {
                "required": [
                    "model",
                    "add_noise",
                    "noise_seed",
                    "steps",
                    "cfg",
                    "sampler_name",
                    "scheduler",
                    "positive",
                    "negative",
                    "latent_image",
                    "start_at_step",
                    "end_at_step",
                    "return_with_leftover_noise",
                ],
                "optional": [],
            },
        },
        "VAEDecode": {
            "input": {"required": {"samples": ["LATENT"], "vae": ["VAE"]}},
            "input_order": {"required": ["samples", "vae"], "optional": []},
        },
        "CreateVideo": {
            "input": {
                "required": {"images": ["IMAGE"], "audio": ["AUDIO"], "fps": ["FLOAT"]}
            },
            "input_order": {"required": ["images", "audio", "fps"], "optional": []},
        },
        "SaveVideo": {
            "input": {
                "required": {
                    "video": ["VIDEO"],
                    "filename_prefix": ["STRING"],
                    "format": ["STRING"],
                    "save_metadata": ["STRING"],
                }
            },
            "input_order": {
                "required": ["video", "filename_prefix", "format", "save_metadata"],
                "optional": [],
            },
        },
    }


class FakeHttpResponse:
    def __init__(self, *, status_code: int = 200, payload: Any = None, text: str | None = None) -> None:
        self.status_code = status_code
        self._payload = payload
        self._text = text

    @property
    def is_error(self) -> bool:
        return self.status_code >= 400

    @property
    def text(self) -> str:
        if self._text is not None:
            return self._text
        if self._payload is None:
            return ""
        return json.dumps(self._payload)

    def json(self) -> Any:
        return self._payload

    def raise_for_status(self) -> None:
        if not self.is_error:
            return
        request = httpx.Request("GET", "http://fake-comfyui.invalid")
        response = httpx.Response(self.status_code, request=request, text=self.text)
        raise httpx.HTTPStatusError(
            f"HTTP {self.status_code}",
            request=request,
            response=response,
        )


class FakeComfyUiScenario:
    def __init__(
        self,
        *,
        scenario: str,
        input_dir: Path,
        output_dir: Path,
        object_info_payload: dict[str, Any],
    ) -> None:
        self.scenario = scenario
        self.input_dir = input_dir
        self.output_dir = output_dir
        self.object_info_payload = object_info_payload
        self.prompt_calls: list[dict[str, Any]] = []
        self.history_polls: dict[str, int] = {}
        self.generated_outputs: dict[str, Path] = {}
        self._prompt_counter = 0
        self._last_prompt_id: str | None = None

    @property
    def last_prompt_id(self) -> str:
        return self._last_prompt_id or "prompt-0"

    def build_client(self, *args, **kwargs) -> "_FakeHttpClient":
        return _FakeHttpClient(self, *args, **kwargs)

    def create_connection(self, *_args, **_kwargs) -> "_FakeWebSocket":
        return _FakeWebSocket(self)

    def handle_get(self, path: str) -> FakeHttpResponse:
        if path == "/object_info":
            return FakeHttpResponse(payload=self.object_info_payload)

        if path.startswith("/history/"):
            prompt_id = path.rsplit("/", 1)[-1]
            self.history_polls[prompt_id] = self.history_polls.get(prompt_id, 0) + 1
            poll_count = self.history_polls[prompt_id]

            if self.scenario == "history_fallback_success" and poll_count == 1:
                return FakeHttpResponse(payload={})

            if self.scenario == "oom_failure":
                return FakeHttpResponse(
                    payload={
                        prompt_id: {
                            "status": {"completed": True, "status_str": "error"},
                            "message": "CUDA out of memory while sampling",
                        }
                    }
                )

            if self.scenario == "output_missing":
                return FakeHttpResponse(
                    payload={
                        prompt_id: {
                            "status": {"completed": True, "status_str": "success"},
                            "outputs": {},
                        }
                    }
                )

            if prompt_id in self.generated_outputs:
                return FakeHttpResponse(
                    payload={
                        prompt_id: {
                            "status": {"completed": True, "status_str": "success"},
                            "outputs": {
                                "108": {
                                    "videos": [
                                        {"filename": self.generated_outputs[prompt_id].name}
                                    ]
                                }
                            },
                        }
                    }
                )

            return FakeHttpResponse(payload={})

        raise AssertionError(f"unexpected GET path: {path}")

    def handle_post(
        self,
        path: str,
        *,
        files: dict[str, tuple[str, Any, str]] | None = None,
        json_payload: dict[str, Any] | None = None,
    ) -> FakeHttpResponse:
        if path == "/upload/image":
            if files is None or "image" not in files:
                raise AssertionError("upload/image called without image file")
            filename, file_handle, _content_type = files["image"]
            content = file_handle.read()
            destination = self.input_dir / filename
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
            return FakeHttpResponse(payload={"name": destination.name, "subfolder": "", "type": "input"})

        if path == "/prompt":
            self._prompt_counter += 1
            prompt_id = f"prompt-{self._prompt_counter}"
            self._last_prompt_id = prompt_id

            if self.scenario == "validation_error":
                return FakeHttpResponse(
                    status_code=400,
                    payload={
                        "error": "validation failed",
                        "node_errors": {"108": {"errors": ["bad output node"]}},
                    },
                )

            if json_payload is None:
                raise AssertionError("/prompt called without JSON payload")
            self.prompt_calls.append(json_payload)
            prompt = json_payload["prompt"]
            prefix = prompt["108"]["inputs"]["filename_prefix"]
            if self.scenario in {"success", "history_fallback_success"}:
                output_path = self.output_dir / f"{prefix}_00001_.mp4"
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(b"fake-video")
                self.generated_outputs[prompt_id] = output_path

            return FakeHttpResponse(
                payload={
                    "prompt_id": prompt_id,
                    "number": self._prompt_counter,
                    "node_errors": {},
                }
            )

        raise AssertionError(f"unexpected POST path: {path}")


class _FakeHttpClient:
    def __init__(self, scenario: FakeComfyUiScenario, *args, **kwargs) -> None:
        self.scenario = scenario

    def __enter__(self) -> "_FakeHttpClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def get(self, path: str, *args, **kwargs) -> FakeHttpResponse:
        return self.scenario.handle_get(path)

    def post(self, path: str, *args, **kwargs) -> FakeHttpResponse:
        return self.scenario.handle_post(
            path,
            files=kwargs.get("files"),
            json_payload=kwargs.get("json"),
        )


class _FakeWebSocket:
    def __init__(self, scenario: FakeComfyUiScenario) -> None:
        self.scenario = scenario
        prompt_id = scenario.last_prompt_id

        if scenario.scenario == "history_fallback_success":
            self._messages = [
                json.dumps({"type": "status", "data": {"prompt_id": prompt_id}}),
                WebSocketConnectionClosedException("history fallback"),
            ]
        elif scenario.scenario == "oom_failure":
            self._messages = [
                json.dumps(
                    {
                        "type": "execution_error",
                        "data": {
                            "prompt_id": prompt_id,
                            "exception_message": "CUDA out of memory while sampling",
                        },
                    }
                )
            ]
        else:
            self._messages = [
                json.dumps({"type": "status", "data": {"prompt_id": prompt_id}}),
                json.dumps(
                    {"type": "progress", "data": {"prompt_id": prompt_id, "value": 3, "max": 20}}
                ),
                json.dumps({"type": "executing", "data": {"prompt_id": prompt_id, "node": "108"}}),
                json.dumps({"type": "execution_success", "data": {"prompt_id": prompt_id}}),
            ]

    def recv(self) -> str:
        if not self._messages:
            raise WebSocketConnectionClosedException("closed")
        next_item = self._messages.pop(0)
        if isinstance(next_item, Exception):
            raise next_item
        return next_item

    def close(self) -> None:
        return None


@pytest.fixture()
def service_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    storage_dir = tmp_path / "storage"
    logs_dir = tmp_path / "logs"
    outputs_dir = tmp_path / "outputs"
    third_party_dir = tmp_path / "third_party"
    comfyui_dir = third_party_dir / "ComfyUI"
    comfyui_models_dir = comfyui_dir / "models"
    comfyui_input_dir = storage_dir / "comfyui_input"
    comfyui_output_dir = storage_dir / "comfyui_output"

    for path in (
        storage_dir,
        logs_dir,
        outputs_dir,
        third_party_dir,
        comfyui_dir,
        comfyui_models_dir / "diffusion_models",
        comfyui_models_dir / "text_encoders",
        comfyui_models_dir / "vae",
        comfyui_input_dir,
        comfyui_output_dir,
    ):
        path.mkdir(parents=True, exist_ok=True)

    for model_path in (
        comfyui_models_dir / "diffusion_models" / "wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors",
        comfyui_models_dir / "diffusion_models" / "wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors",
        comfyui_models_dir / "text_encoders" / "umt5_xxl_fp8_e4m3fn_scaled.safetensors",
        comfyui_models_dir / "vae" / "wan_2.1_vae.safetensors",
    ):
        model_path.write_text("fake-model", encoding="utf-8")

    monkeypatch.setenv("WAN_STORAGE_DIR", str(storage_dir))
    monkeypatch.setenv("WAN_LOG_DIR", str(logs_dir))
    monkeypatch.setenv("WAN_OUTPUT_DIR", str(outputs_dir))
    monkeypatch.setenv("WAN_THIRD_PARTY_DIR", str(third_party_dir))
    monkeypatch.setenv("WAN_DB_PATH", str(storage_dir / "tasks.db"))
    monkeypatch.setenv("WAN_SERVICE_PYTHON_BIN", sys.executable)
    monkeypatch.setenv("WAN_COMFYUI_PYTHON_BIN", sys.executable)
    monkeypatch.setenv("WAN_COMFYUI_DIR", str(comfyui_dir))
    monkeypatch.setenv("WAN_COMFYUI_INPUT_DIR", str(comfyui_input_dir))
    monkeypatch.setenv("WAN_COMFYUI_OUTPUT_DIR", str(comfyui_output_dir))
    monkeypatch.setenv("WAN_COMFYUI_WORKFLOW_TEMPLATE", str(WORKFLOW_TEMPLATE_PATH))
    monkeypatch.setenv("WAN_ALLOWED_SIZES", "832*480,480*832")
    monkeypatch.setenv("WAN_DEFAULT_SIZE", "832*480")
    monkeypatch.setenv("WAN_VIDEO_LENGTH", "49")
    monkeypatch.setenv("WAN_VIDEO_FPS", "16")
    monkeypatch.setenv("WAN_COMFYUI_HOST", "127.0.0.1")
    monkeypatch.setenv("WAN_COMFYUI_PORT", "8188")
    monkeypatch.setenv("WAN_COMFYUI_HISTORY_POLL_INTERVAL_SECONDS", "0.01")
    monkeypatch.setenv("WAN_COMFYUI_TASK_TIMEOUT_SECONDS", "5")
    monkeypatch.setenv("WAN_COMFYUI_WS_RECEIVE_TIMEOUT_SECONDS", "0.1")

    return {
        "storage_dir": storage_dir,
        "logs_dir": logs_dir,
        "outputs_dir": outputs_dir,
        "third_party_dir": third_party_dir,
        "comfyui_dir": comfyui_dir,
        "comfyui_input_dir": comfyui_input_dir,
        "comfyui_output_dir": comfyui_output_dir,
        "db_path": storage_dir / "tasks.db",
    }


@pytest.fixture()
def repository(service_env: dict[str, Path]) -> TaskRepository:
    init_db(service_env["db_path"])
    return TaskRepository(service_env["db_path"])


@pytest.fixture()
def comfyui_object_info() -> dict[str, Any]:
    return fake_object_info()


@pytest.fixture()
def install_fake_comfyui(
    service_env: dict[str, Path],
    comfyui_object_info: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[[str], FakeComfyUiScenario]:
    def factory(scenario: str = "success") -> FakeComfyUiScenario:
        fake = FakeComfyUiScenario(
            scenario=scenario,
            input_dir=service_env["comfyui_input_dir"],
            output_dir=service_env["comfyui_output_dir"],
            object_info_payload=comfyui_object_info,
        )
        monkeypatch.setattr(comfyui_manager_module.httpx, "Client", fake.build_client)
        monkeypatch.setattr(comfyui_backend_module.httpx, "Client", fake.build_client)
        monkeypatch.setattr(comfyui_backend_module, "create_connection", fake.create_connection)
        return fake

    return factory
