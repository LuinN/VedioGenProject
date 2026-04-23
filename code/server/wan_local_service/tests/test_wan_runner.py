from __future__ import annotations

from pathlib import Path

from app.config import load_settings
from app.wan_runner import WanRunner


def test_wan_runner_returns_specific_failure_summary(
    repository,
    service_env: dict[str, Path],
) -> None:
    service_env["generate_py"].write_text(
        """
import sys

print("Traceback (most recent call last):")
print("  File \\"fake.py\\", line 1, in <module>")
print("ModuleNotFoundError: No module named 'einops'")
sys.exit(1)
""".strip()
        + "\n",
        encoding="utf-8",
    )

    settings = load_settings()
    task = repository.create_task(
        task_id="task-generate-failure",
        mode="t2v",
        prompt="failure prompt",
        size="1280*704",
        log_path=str(service_env["logs_dir"] / "task-generate-failure.log"),
    )

    result = WanRunner(settings).run_task(task)

    assert result.success is False
    assert result.output_path is None
    assert (
        result.error_message
        == "ModuleNotFoundError: No module named 'einops' (generate.py exit code 1)"
    )


def test_wan_runner_reports_success_and_output_path(
    repository,
    service_env: dict[str, Path],
) -> None:
    service_env["generate_py"].write_text(
        """
import pathlib
import sys

args = sys.argv[1:]
save_file = pathlib.Path(args[args.index("--save_file") + 1])
save_file.parent.mkdir(parents=True, exist_ok=True)
save_file.write_text("video-bytes", encoding="utf-8")
print("generation finished")
""".strip()
        + "\n",
        encoding="utf-8",
    )

    settings = load_settings()
    task = repository.create_task(
        task_id="task-generate-success",
        mode="t2v",
        prompt="success prompt",
        size="1280*704",
        log_path=str(service_env["logs_dir"] / "task-generate-success.log"),
    )

    result = WanRunner(settings).run_task(task)

    assert result.success is True
    assert result.error_message is None
    assert result.output_path is not None
    assert Path(result.output_path).exists()
