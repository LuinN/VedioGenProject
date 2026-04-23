from __future__ import annotations

from collections import deque
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .config import INTERNAL_WAN_TASK, Settings
from .repository import TaskRecord


@dataclass(slots=True)
class WanExecutionResult:
    success: bool
    output_path: str | None
    error_message: str | None


class WanRunner:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def run_task(self, task: TaskRecord) -> WanExecutionResult:
        log_path = Path(task.log_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        output_dir = self.settings.outputs_dir / task.task_id
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / "result.mp4"

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
            "True",
            "--convert_model_dtype",
            "--t5_cpu",
            "--prompt",
            task.prompt,
            "--save_file",
            str(output_file),
        ]

        with log_path.open("a", encoding="utf-8") as log_file:
            self._write_log_header(log_file, task, command)
            missing_reason = self._check_prerequisites()
            if missing_reason is not None:
                log_file.write(f"{missing_reason}\n")
                return WanExecutionResult(False, None, missing_reason)

            recent_lines: deque[str] = deque(maxlen=40)
            process = subprocess.Popen(
                command,
                cwd=self.settings.wan_repo_dir,
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
        return None

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
    ) -> None:
        started_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        log_file.write(f"started_at: {started_at}\n")
        log_file.write(f"task_id: {task.task_id}\n")
        log_file.write(f"mode: {task.mode}\n")
        log_file.write(f"size: {task.size}\n")
        log_file.write(f"command: {' '.join(command)}\n")
        log_file.write("-" * 80 + "\n")
