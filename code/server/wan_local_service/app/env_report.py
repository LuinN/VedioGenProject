from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence
from urllib.error import URLError
from urllib.request import urlopen

from .config import load_settings


@dataclass(slots=True)
class CheckResult:
    name: str
    ok: bool
    detail: str
    required_for: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "ok": self.ok,
            "detail": self.detail,
            "required_for": list(self.required_for),
        }


@dataclass(slots=True)
class EnvironmentReport:
    service_root: Path
    service_ready: bool
    backend_ready: bool
    model_ready: bool
    checks: list[CheckResult]

    def to_dict(self) -> dict[str, object]:
        return {
            "service_root": str(self.service_root),
            "service_ready": self.service_ready,
            "backend_ready": self.backend_ready,
            "model_ready": self.model_ready,
            "checks": [item.to_dict() for item in self.checks],
        }


def _resolve_command(raw_value: str) -> str | None:
    if "/" in raw_value:
        path = Path(raw_value)
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
        return None
    return shutil.which(raw_value)


def _run_command(command: Sequence[str]) -> tuple[bool, str]:
    try:
        completed = subprocess.run(
            list(command),
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except FileNotFoundError:
        return False, "command not found"
    except Exception as exc:  # pragma: no cover - defensive path
        return False, f"{type(exc).__name__}: {exc}"

    output = "\n".join(
        part.strip() for part in (completed.stdout, completed.stderr) if part.strip()
    ).strip()
    if completed.returncode == 0:
        return True, output or "ok"
    return False, output or f"exit code {completed.returncode}"


def _python_import_results(
    python_bin: str | None,
    modules: Sequence[str],
) -> dict[str, tuple[bool, str]]:
    if python_bin is None:
        return {module: (False, "python executable not available") for module in modules}

    script = """
import importlib
import json
import sys

results = []
for module_name in sys.argv[1:]:
    try:
        importlib.import_module(module_name)
        results.append({"module": module_name, "ok": True, "detail": "ok"})
    except Exception as exc:
        results.append({"module": module_name, "ok": False, "detail": f"{type(exc).__name__}: {exc}"})
print(json.dumps(results))
"""
    try:
        completed = subprocess.run(
            [python_bin, "-c", script, *modules],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except FileNotFoundError:
        return {module: (False, "command not found") for module in modules}
    except Exception as exc:  # pragma: no cover - defensive path
        return {module: (False, f"{type(exc).__name__}: {exc}") for module in modules}

    stdout = completed.stdout.strip()
    stderr = completed.stderr.strip()
    if completed.returncode != 0:
        detail = stderr or stdout or f"exit code {completed.returncode}"
        return {module: (False, detail) for module in modules}

    payload = json.loads(stdout)
    return {
        str(item["module"]): (bool(item["ok"]), str(item["detail"]))
        for item in payload
    }


def _torch_cuda_status(python_bin: str | None) -> tuple[bool, str]:
    if python_bin is None:
        return False, "python executable not available"

    script = """
import json
import torch
payload = {
    "ok": bool(torch.cuda.is_available()),
    "detail": f"torch={torch.__version__}, torch_cuda={torch.version.cuda}, cuda_available={bool(torch.cuda.is_available())}",
}
print(json.dumps(payload))
"""
    try:
        completed = subprocess.run(
            [python_bin, "-c", script],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except FileNotFoundError:
        return False, "command not found"
    except Exception as exc:  # pragma: no cover
        return False, f"{type(exc).__name__}: {exc}"

    stdout = completed.stdout.strip()
    stderr = completed.stderr.strip()
    if completed.returncode != 0:
        return False, stderr or stdout or f"exit code {completed.returncode}"
    payload = json.loads(stdout)
    return bool(payload["ok"]), str(payload["detail"])


def _http_json_ok(url: str, timeout_seconds: float) -> tuple[bool, str]:
    try:
        with urlopen(url, timeout=timeout_seconds) as response:
            body = response.read().decode("utf-8", errors="replace").strip()
            if response.status != 200:
                return False, f"HTTP {response.status}: {body}"
            return True, body or "ok"
    except URLError as exc:
        return False, f"{type(exc).__name__}: {exc}"
    except Exception as exc:  # pragma: no cover
        return False, f"{type(exc).__name__}: {exc}"


def collect_environment_report() -> EnvironmentReport:
    settings = load_settings()
    service_python_resolved = _resolve_command(settings.service_python_bin)
    comfyui_python_resolved = _resolve_command(settings.comfyui_python_bin)

    service_imports = _python_import_results(
        service_python_resolved,
        ("fastapi", "uvicorn", "multipart", "httpx", "websocket"),
    )
    comfyui_imports = _python_import_results(
        comfyui_python_resolved,
        ("torch", "aiohttp", "PIL"),
    )
    torch_cuda_ok, torch_cuda_detail = _torch_cuda_status(comfyui_python_resolved)
    object_info_ok, object_info_detail = _http_json_ok(
        f"{settings.comfyui_base_url}/object_info",
        settings.comfyui_health_timeout_seconds,
    )

    checks: list[CheckResult] = [
        CheckResult(
            name="service_python",
            ok=service_python_resolved is not None,
            detail=service_python_resolved or f"not found: {settings.service_python_bin}",
            required_for=("service",),
        ),
        CheckResult(
            name="comfyui_python",
            ok=comfyui_python_resolved is not None,
            detail=comfyui_python_resolved or f"not found: {settings.comfyui_python_bin}",
            required_for=("backend",),
        ),
        CheckResult(
            name="comfyui_dir",
            ok=settings.comfyui_root_dir.is_dir(),
            detail=(
                str(settings.comfyui_root_dir)
                if settings.comfyui_root_dir.is_dir()
                else f"missing: {settings.comfyui_root_dir}"
            ),
            required_for=("backend",),
        ),
        CheckResult(
            name="workflow_template",
            ok=settings.comfyui_workflow_template.is_file(),
            detail=(
                str(settings.comfyui_workflow_template)
                if settings.comfyui_workflow_template.is_file()
                else f"missing: {settings.comfyui_workflow_template}"
            ),
            required_for=("backend",),
        ),
    ]

    for model_path in settings.comfyui_required_model_paths:
        checks.append(
            CheckResult(
                name=f"model:{model_path.name}",
                ok=model_path.is_file(),
                detail=str(model_path) if model_path.is_file() else f"missing: {model_path}",
                required_for=("model", "backend"),
            )
        )

    checks.append(
        CheckResult(
            name="nvidia_smi",
            ok=shutil.which("nvidia-smi") is not None,
            detail=(
                _run_command(["nvidia-smi"])[1]
                if shutil.which("nvidia-smi") is not None
                else "nvidia-smi not found on PATH"
            ),
            required_for=("backend",),
        )
    )

    for module_name, (ok, detail) in service_imports.items():
        checks.append(
            CheckResult(
                name=f"service_import:{module_name}",
                ok=ok,
                detail=detail,
                required_for=("service",),
            )
        )

    for module_name, (ok, detail) in comfyui_imports.items():
        checks.append(
            CheckResult(
                name=f"comfyui_import:{module_name}",
                ok=ok,
                detail=detail,
                required_for=("backend",),
            )
        )

    checks.append(
        CheckResult(
            name="torch_cuda",
            ok=torch_cuda_ok,
            detail=torch_cuda_detail,
            required_for=("backend",),
        )
    )
    checks.append(
        CheckResult(
            name="comfyui_object_info",
            ok=object_info_ok,
            detail=object_info_detail,
            required_for=("backend",),
        )
    )

    service_ready = all(
        check.ok for check in checks if "service" in check.required_for
    )
    model_ready = all(
        check.ok for check in checks if "model" in check.required_for
    )
    backend_ready = all(
        check.ok for check in checks if "backend" in check.required_for
    )

    return EnvironmentReport(
        service_root=settings.service_root,
        service_ready=service_ready,
        backend_ready=backend_ready,
        model_ready=model_ready,
        checks=checks,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Report Wan local service environment status.")
    parser.add_argument(
        "--require",
        choices=("service", "backend", "model"),
        default=None,
        help="Exit non-zero when the selected readiness target is not satisfied.",
    )
    args = parser.parse_args(argv)

    report = collect_environment_report()

    print("[env] Wan local service environment report")
    print(f"[env] service_root={report.service_root}")
    print(f"[summary] service_ready={'yes' if report.service_ready else 'no'}")
    print(f"[summary] backend_ready={'yes' if report.backend_ready else 'no'}")
    print(f"[summary] model_ready={'yes' if report.model_ready else 'no'}")

    for check in report.checks:
        label = "ok" if check.ok else "missing"
        scopes = ",".join(check.required_for) or "info"
        print(f"[{label}] {check.name} ({scopes}) -> {check.detail}")

    if args.require == "service" and not report.service_ready:
        return 1
    if args.require == "backend" and not report.backend_ready:
        return 1
    if args.require == "model" and not report.model_ready:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
