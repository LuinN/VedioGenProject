from __future__ import annotations

from collections import deque
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .config import INTERNAL_WAN_TASK, Settings, TASK_OUTPUT_FILENAME
from .repository import TaskRecord


@dataclass(slots=True)
class WanExecutionResult:
    success: bool
    output_path: str | None
    error_message: str | None


def _read_meminfo_kib(field_name: str) -> int | None:
    try:
        with Path("/proc/meminfo").open("r", encoding="utf-8") as meminfo:
            for line in meminfo:
                if not line.startswith(f"{field_name}:"):
                    continue
                _, raw_value = line.split(":", 1)
                return int(raw_value.strip().split()[0])
    except (FileNotFoundError, OSError, ValueError):
        return None
    return None


def _format_gib_from_kib(value_kib: int | None) -> str:
    if value_kib is None:
        return "unknown"
    return f"{value_kib / (1024 * 1024):.1f} GiB"


def _env_bool(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


class WanRunner:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def run_task(self, task: TaskRecord) -> WanExecutionResult:
        log_path = Path(task.log_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        output_dir = self.settings.outputs_dir / task.task_id
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / TASK_OUTPUT_FILENAME
        command = self._build_command(task, output_file)
        resource_snapshot = self._resource_snapshot()

        with log_path.open("a", encoding="utf-8") as log_file:
            self._write_log_header(log_file, task, command, resource_snapshot)
            missing_reason = self._check_prerequisites()
            if missing_reason is not None:
                log_file.write(f"{missing_reason}\n")
                return WanExecutionResult(False, None, missing_reason)

            recent_lines: deque[str] = deque(maxlen=40)
            process = subprocess.Popen(
                command,
                cwd=self.settings.wan_repo_dir,
                env=self._build_subprocess_env(),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            assert process.stdout is not None
            for line in process.stdout:
                log_file.write(line)
                normalized = self._normalize_log_line(line)
                if normalized:
                    recent_lines.append(normalized)
            return_code = process.wait()
            log_file.write(f"generate.py exit code: {return_code}\n")

        if return_code != 0:
            return WanExecutionResult(
                False,
                None,
                self._build_failure_message(return_code, recent_lines),
            )
        if not output_file.exists():
            return WanExecutionResult(
                False,
                None,
                f"output file was not generated at {output_file}",
            )
        return WanExecutionResult(True, str(output_file), None)

    def _check_prerequisites(self) -> str | None:
        if not self.settings.wan_repo_dir.exists():
            return f"Wan2.2 repository not found: {self.settings.wan_repo_dir}"
        if not self.settings.wan_generate_py.exists():
            return f"generate.py not found: {self.settings.wan_generate_py}"
        if not self.settings.wan_model_dir.exists():
            return f"model directory not found: {self.settings.wan_model_dir}"
        allow_sdpa_fallback = _env_bool("WAN_ALLOW_SDPA_FALLBACK", True)
        if (
            os.getenv("WAN_SKIP_FLASH_ATTN_PRECHECK") != "1"
            and not allow_sdpa_fallback
        ):
            flash_attn_ready, flash_attn_detail = self._python_module_available(
                "flash_attn"
            )
            if not flash_attn_ready:
                return (
                    "flash_attn import failed for inference runtime "
                    f"({self.settings.python_bin}): {flash_attn_detail}"
                )
        if self.settings.runtime_memory_guard_enabled:
            guard_message = self._runtime_memory_guard_message()
            if guard_message is not None:
                return guard_message
        return None

    def _build_command(self, task: TaskRecord, output_file: Path) -> list[str]:
        command = [
            self.settings.python_bin,
            str(self.settings.wan_generate_py),
            "--task",
            INTERNAL_WAN_TASK,
            "--size",
            task.size,
            "--ckpt_dir",
            str(self.settings.wan_model_dir),
            "--offload_model",
            "True" if self.settings.offload_model else "False",
            "--sample_solver",
            self.settings.sample_solver,
            "--prompt",
            task.prompt,
            "--save_file",
            str(output_file),
        ]
        if self.settings.convert_model_dtype:
            command.append("--convert_model_dtype")
        if self.settings.t5_cpu:
            command.append("--t5_cpu")
        if self.settings.frame_num is not None:
            command.extend(["--frame_num", str(self.settings.frame_num)])
        if self.settings.sample_steps is not None:
            command.extend(["--sample_steps", str(self.settings.sample_steps)])
        if self.settings.sample_shift is not None:
            command.extend(["--sample_shift", str(self.settings.sample_shift)])
        if self.settings.sample_guide_scale is not None:
            command.extend(
                ["--sample_guide_scale", str(self.settings.sample_guide_scale)]
            )
        return command

    def _build_subprocess_env(self) -> dict[str, str]:
        env = os.environ.copy()
        env.setdefault("OMP_NUM_THREADS", "1")
        env.setdefault("MKL_NUM_THREADS", "1")
        env.setdefault("TOKENIZERS_PARALLELISM", "false")
        env.setdefault("CUDA_MODULE_LOADING", "LAZY")
        if self.settings.low_memory_profile:
            env.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
        return env

    def _resource_snapshot(self) -> str:
        mem_available_kib = _read_meminfo_kib("MemAvailable")
        swap_free_kib = _read_meminfo_kib("SwapFree")
        return (
            f"mem_available={_format_gib_from_kib(mem_available_kib)}, "
            f"swap_free={_format_gib_from_kib(swap_free_kib)}"
        )

    def _runtime_memory_guard_message(self) -> str | None:
        mem_available_kib = _read_meminfo_kib("MemAvailable")
        swap_free_kib = _read_meminfo_kib("SwapFree")
        if mem_available_kib is None or swap_free_kib is None:
            return None

        min_mem_available_kib = int(self.settings.min_mem_available_gb * 1024 * 1024)
        min_swap_available_kib = int(self.settings.min_swap_available_gb * 1024 * 1024)
        if (
            mem_available_kib >= min_mem_available_kib
            and swap_free_kib >= min_swap_available_kib
        ):
            return None

        return (
            "insufficient memory headroom before generation: "
            f"MemAvailable={_format_gib_from_kib(mem_available_kib)}, "
            f"SwapFree={_format_gib_from_kib(swap_free_kib)}. "
            "Stop Docker/other WSL services or lower WAN_FRAME_NUM/WAN_SAMPLE_STEPS."
        )

    def _python_module_available(self, module_name: str) -> tuple[bool, str]:
        try:
            completed = subprocess.run(
                [self.settings.python_bin, "-c", f"import {module_name}"],
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except FileNotFoundError:
            return False, "command not found"
        except Exception as exc:  # pragma: no cover - defensive path
            return False, f"{type(exc).__name__}: {exc}"

        if completed.returncode == 0:
            return True, "ok"
        detail = completed.stderr.strip() or completed.stdout.strip()
        return False, detail or f"exit code {completed.returncode}"

    @staticmethod
    def _normalize_log_line(line: str) -> str:
        return line.strip()

    @classmethod
    def _build_failure_message(cls, return_code: int, recent_lines: deque[str]) -> str:
        summary = cls._extract_failure_summary(recent_lines)
        if summary is None:
            return f"generate.py exited with code {return_code}"
        return f"{summary} (generate.py exit code {return_code})"

    @staticmethod
    def _extract_failure_summary(recent_lines: deque[str]) -> str | None:
        fallback: str | None = None
        ignored_prefixes = (
            "started_at:",
            "task_id:",
            "mode:",
            "size:",
            "command:",
        )
        ignored_exact = {
            "-" * 80,
            "Generating video ...",
        }
        for line in reversed(recent_lines):
            if line.startswith(ignored_prefixes):
                continue
            if line in ignored_exact:
                continue
            if line == "Traceback (most recent call last):":
                if fallback is None:
                    fallback = line
                continue
            return line
        return fallback

    @staticmethod
    def _write_log_header(
        log_file,
        task: TaskRecord,
        command: list[str],
        resource_snapshot: str,
    ) -> None:
        started_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        log_file.write(f"started_at: {started_at}\n")
        log_file.write(f"task_id: {task.task_id}\n")
        log_file.write(f"mode: {task.mode}\n")
        log_file.write(f"size: {task.size}\n")
        log_file.write(f"resources: {resource_snapshot}\n")
        log_file.write(f"command: {' '.join(command)}\n")
        log_file.write("-" * 80 + "\n")
