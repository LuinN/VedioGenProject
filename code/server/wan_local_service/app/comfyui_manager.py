from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from .config import BACKEND_ID_COMFYUI_NATIVE, Settings


@dataclass(slots=True)
class ComfyUiStatus:
    backend: str
    backend_ready: bool
    model_ready: bool
    reason: str | None = None


class ComfyUiManager:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._object_info_cache: dict[str, Any] | None = None

    def workflow_template_exists(self) -> bool:
        return self.settings.comfyui_workflow_template.is_file()

    def missing_model_paths(self) -> list[Path]:
        return [
            path
            for path in self.settings.comfyui_required_model_paths
            if not path.is_file()
        ]

    def get_status(self, *, refresh_object_info: bool = False) -> ComfyUiStatus:
        missing_models = self.missing_model_paths()
        model_ready = not missing_models
        if not self.workflow_template_exists():
            return ComfyUiStatus(
                backend=BACKEND_ID_COMFYUI_NATIVE,
                backend_ready=False,
                model_ready=model_ready,
                reason=(
                    "workflow template missing: "
                    f"{self.settings.comfyui_workflow_template}"
                ),
            )

        if missing_models:
            return ComfyUiStatus(
                backend=BACKEND_ID_COMFYUI_NATIVE,
                backend_ready=False,
                model_ready=False,
                reason=f"missing model file: {missing_models[0]}",
            )

        try:
            with httpx.Client(
                base_url=self.settings.comfyui_base_url,
                timeout=self.settings.comfyui_health_timeout_seconds,
            ) as client:
                response = client.get("/object_info")
                response.raise_for_status()
                if refresh_object_info or self._object_info_cache is None:
                    payload = response.json()
                    if not isinstance(payload, dict):
                        raise TypeError("object_info did not return a JSON object")
                    self._object_info_cache = payload
        except Exception as exc:
            return ComfyUiStatus(
                backend=BACKEND_ID_COMFYUI_NATIVE,
                backend_ready=False,
                model_ready=model_ready,
                reason=f"ComfyUI unavailable: {type(exc).__name__}: {exc}",
            )

        return ComfyUiStatus(
            backend=BACKEND_ID_COMFYUI_NATIVE,
            backend_ready=True,
            model_ready=True,
            reason=None,
        )

    def fetch_object_info(self) -> dict[str, Any]:
        if self._object_info_cache is not None:
            return self._object_info_cache

        status = self.get_status(refresh_object_info=True)
        if not status.backend_ready or self._object_info_cache is None:
            reason = status.reason or "ComfyUI object_info is unavailable"
            raise RuntimeError(reason)
        return self._object_info_cache
