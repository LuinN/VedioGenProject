from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


DEFAULT_RUNTIME_PYTHON = ".venv/bin/python"


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
    configured_python: str
    configured_python_resolved: str | None
    service_ready: bool
    inference_ready: bool
    flash_attn_build_enabled: bool
    flash_attn_build_ready: bool
    checks: list[CheckResult]

    def to_dict(self) -> dict[str, object]:
        return {
            "service_root": str(self.service_root),
            "configured_python": self.configured_python,
            "configured_python_resolved": self.configured_python_resolved,
            "service_ready": self.service_ready,
            "inference_ready": self.inference_ready,
            "flash_attn_build_enabled": self.flash_attn_build_enabled,
            "flash_attn_build_ready": self.flash_attn_build_ready,
            "checks": [item.to_dict() for item in self.checks],
        }


def _resolve_path(base_dir: Path, raw_value: str | None, default_value: Path) -> Path:
    candidate = Path(raw_value) if raw_value else default_value
    if not candidate.is_absolute():
        candidate = base_dir / candidate
    return candidate.resolve()


def _resolve_exec_or_path(base_dir: Path, raw_value: str | None, default_value: str) -> str:
    candidate = raw_value or default_value
    if "/" not in candidate:
        return candidate
    path = Path(candidate)
    if not path.is_absolute():
        path = (base_dir / path).resolve()
    return str(path)


def _resolve_command(raw_value: str) -> str | None:
    if "/" in raw_value:
        path = Path(raw_value)
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
        return None
    return shutil.which(raw_value)


def _resolve_service_python(base_dir: Path) -> str:
    explicit_service_python = os.getenv("WAN_SERVICE_PYTHON_BIN")
    if explicit_service_python:
        return _resolve_exec_or_path(base_dir, explicit_service_python, DEFAULT_RUNTIME_PYTHON)

    default_venv_python = base_dir / DEFAULT_RUNTIME_PYTHON
    if default_venv_python.is_file() and os.access(default_venv_python, os.X_OK):
        return str(default_venv_python)

    return _resolve_exec_or_path(
        base_dir,
        os.getenv("WAN_PYTHON_BIN"),
        DEFAULT_RUNTIME_PYTHON,
    )


def _env_bool(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


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
    if output:
        return False, output
    return False, f"exit code {completed.returncode}"


def _python_import_results(
    python_bin: str | None,
    modules: Sequence[str],
) -> dict[str, tuple[bool, str]]:
    if python_bin is None:
        return {module: (False, "configured runtime python is not available") for module in modules}

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
        results.append(
            {
                "module": module_name,
                "ok": False,
                "detail": f"{type(exc).__name__}: {exc}",
            }
        )
print(json.dumps(results))
"""
    try:
        completed = subprocess.run(
            [python_bin, "-c", script, *modules],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
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
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        detail = stderr or f"unexpected stdout: {stdout}"
        return {module: (False, detail) for module in modules}

    results: dict[str, tuple[bool, str]] = {}
    for item in payload:
        module_name = str(item["module"])
        results[module_name] = (bool(item["ok"]), str(item["detail"]))
    return results


def _torch_cuda_status(python_bin: str | None) -> tuple[bool, str]:
    if python_bin is None:
        return False, "configured runtime python is not available"

    script = """
import json

payload = {}
try:
    import torch
except Exception as exc:
    payload = {"ok": False, "detail": f"{type(exc).__name__}: {exc}"}
else:
    try:
        cuda_available = bool(torch.cuda.is_available())
        payload = {
            "ok": cuda_available,
            "detail": (
                f"torch={torch.__version__}, torch_cuda={torch.version.cuda}, "
                f"cuda_available={cuda_available}"
            ),
        }
    except Exception as exc:
        payload = {
            "ok": False,
            "detail": f"{type(exc).__name__}: {exc}",
        }
print(json.dumps(payload))
"""
    try:
        completed = subprocess.run(
            [python_bin, "-c", script],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except FileNotFoundError:
        return False, "command not found"
    except Exception as exc:  # pragma: no cover - defensive path
        return False, f"{type(exc).__name__}: {exc}"

    stdout = completed.stdout.strip()
    stderr = completed.stderr.strip()
    if completed.returncode != 0:
        return False, stderr or stdout or f"exit code {completed.returncode}"
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        return False, stderr or f"unexpected stdout: {stdout}"
    return bool(payload["ok"]), str(payload["detail"])


def collect_environment_report() -> EnvironmentReport:
    service_root = Path(__file__).resolve().parents[1]
    configured_python = _resolve_service_python(service_root)
    configured_python_resolved = _resolve_command(configured_python)
    allow_sdpa_fallback = _env_bool("WAN_ALLOW_SDPA_FALLBACK", True)
    flash_attn_build_enabled = _env_bool("WAN_ENABLE_FLASH_ATTN_BUILD", False)

    wan_repo_dir = _resolve_path(
        service_root,
        os.getenv("WAN_REPO_DIR"),
        Path("third_party/Wan2.2"),
    )
    wan_model_dir = _resolve_path(
        service_root,
        os.getenv("WAN_MODEL_DIR"),
        Path("third_party/Wan2.2-TI2V-5B"),
    )
    wan_generate_py = _resolve_path(
        service_root,
        os.getenv("WAN_GENERATE_PY"),
        Path("third_party/Wan2.2/generate.py"),
    )
    default_venv_dir = service_root / ".venv"

    checks: list[CheckResult] = [
        CheckResult(
            name="configured_python",
            ok=configured_python_resolved is not None,
            detail=(
                configured_python_resolved
                if configured_python_resolved is not None
                else f"not found: {configured_python}"
            ),
            required_for=("service", "inference"),
        ),
        CheckResult(
            name="default_venv_dir",
            ok=default_venv_dir.is_dir(),
            detail=(
                str(default_venv_dir)
                if default_venv_dir.is_dir()
                else f"missing: {default_venv_dir}"
            ),
            required_for=(),
        ),
        CheckResult(
            name="wan_repo_dir",
            ok=wan_repo_dir.is_dir(),
            detail=str(wan_repo_dir) if wan_repo_dir.is_dir() else f"missing: {wan_repo_dir}",
            required_for=("inference",),
        ),
        CheckResult(
            name="wan_generate_py",
            ok=wan_generate_py.is_file(),
            detail=(
                str(wan_generate_py)
                if wan_generate_py.is_file()
                else f"missing: {wan_generate_py}"
            ),
            required_for=("inference",),
        ),
        CheckResult(
            name="wan_model_dir",
            ok=wan_model_dir.is_dir(),
            detail=(
                str(wan_model_dir)
                if wan_model_dir.is_dir()
                else f"missing: {wan_model_dir}"
            ),
            required_for=("inference",),
        ),
    ]

    nvidia_smi_path = shutil.which("nvidia-smi")
    if nvidia_smi_path is None:
        checks.append(
            CheckResult(
                name="nvidia_smi",
                ok=False,
                detail="nvidia-smi not found on PATH",
                required_for=("inference",),
            )
        )
    else:
        ok, detail = _run_command(["nvidia-smi"])
        checks.append(
            CheckResult(
                name="nvidia_smi",
                ok=ok,
                detail=detail.splitlines()[0] if detail else nvidia_smi_path,
                required_for=("inference",),
            )
        )

    nvcc_path = shutil.which("nvcc")
    if nvcc_path is None:
        checks.append(
            CheckResult(
                name="nvcc",
                ok=False,
                detail="nvcc not found on PATH",
                required_for=("build",) if flash_attn_build_enabled else (),
            )
        )
    else:
        ok, detail = _run_command(["nvcc", "-V"])
        checks.append(
            CheckResult(
                name="nvcc",
                ok=ok,
                detail=detail.splitlines()[-1] if detail else nvcc_path,
                required_for=("build",) if flash_attn_build_enabled else (),
            )
        )

    import_results = _python_import_results(
        configured_python_resolved,
        ("fastapi", "uvicorn", "torch", "flash_attn"),
    )
    for module_name, required_for in (
        ("fastapi", ("service", "inference")),
        ("uvicorn", ("service", "inference")),
        ("torch", ("inference",)),
        ("flash_attn", () if allow_sdpa_fallback else ("inference",)),
    ):
        ok, detail = import_results[module_name]
        checks.append(
            CheckResult(
                name=f"python_import:{module_name}",
                ok=ok,
                detail=detail,
                required_for=required_for,
            )
        )

    torch_cuda_ok, torch_cuda_detail = _torch_cuda_status(configured_python_resolved)
    checks.append(
        CheckResult(
            name="torch_cuda",
            ok=torch_cuda_ok,
            detail=torch_cuda_detail,
            required_for=("inference",),
        )
    )

    service_ready = all(
        check.ok for check in checks if "service" in check.required_for
    )
    inference_ready = all(
        check.ok for check in checks if "inference" in check.required_for
    )
    flash_attn_build_ready = all(
        check.ok for check in checks if "build" in check.required_for
    )

    return EnvironmentReport(
        service_root=service_root,
        configured_python=configured_python,
        configured_python_resolved=configured_python_resolved,
        service_ready=service_ready,
        inference_ready=inference_ready,
        flash_attn_build_enabled=flash_attn_build_enabled,
        flash_attn_build_ready=flash_attn_build_ready,
        checks=checks,
    )


def _format_text(report: EnvironmentReport) -> str:
    lines = [
        "[env] Wan local service environment report",
        f"[env] service_root={report.service_root}",
        f"[env] configured_python={report.configured_python}",
        (
            f"[env] configured_python_resolved={report.configured_python_resolved}"
            if report.configured_python_resolved
            else "[env] configured_python_resolved=<missing>"
        ),
        f"[summary] service_ready={'yes' if report.service_ready else 'no'}",
        f"[summary] inference_ready={'yes' if report.inference_ready else 'no'}",
        (
            "[summary] flash_attn_build_enabled="
            f"{'yes' if report.flash_attn_build_enabled else 'no'}"
        ),
        (
            "[summary] flash_attn_build_ready="
            f"{'yes' if report.flash_attn_build_ready else 'no'}"
        ),
    ]

    for check in report.checks:
        status = "ok" if check.ok else "missing"
        required = ",".join(check.required_for) if check.required_for else "info"
        lines.append(
            f"[{status}] {check.name} ({required}) -> {check.detail}"
        )

    if not report.service_ready:
        lines.append(
            "[hint] Service runtime is incomplete. Run `bash scripts/setup_wan22.sh` "
            "inside code/server/wan_local_service."
        )
    if not report.inference_ready:
        lines.append(
            "[hint] Inference runtime is incomplete. Check the missing Wan repo, "
            "model directory, torch CUDA state, and flash_attn import above."
        )
    elif _env_bool("WAN_ALLOW_SDPA_FALLBACK", True):
        lines.append(
            "[hint] flash_attn import is optional in the current SDPA fallback mode. "
            "Inference can run without it, but performance may be lower."
        )
    if not report.flash_attn_build_enabled:
        lines.append(
            "[hint] flash_attn local build is disabled by default. Current setup "
            "and runtime validation target the SDPA fallback path."
        )
    elif not report.flash_attn_build_ready:
        lines.append(
            "[hint] flash_attn build prerequisites are incomplete. Install the CUDA "
            "toolkit so `nvcc` is available before retrying setup."
        )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Report Wan local service environment readiness.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format.",
    )
    parser.add_argument(
        "--require",
        choices=("service", "inference", "build"),
        default=None,
        help="Exit non-zero if the selected readiness target is not satisfied.",
    )
    args = parser.parse_args(argv)

    report = collect_environment_report()
    if args.format == "json":
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(_format_text(report))

    if args.require == "service":
        return 0 if report.service_ready else 1
    if args.require == "inference":
        return 0 if report.inference_ready else 1
    if args.require == "build":
        return 0 if report.flash_attn_build_ready else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
