from __future__ import annotations

import re
from dataclasses import dataclass


_PROGRESS_RE = re.compile(
    r"(?P<percent>\d{1,3})%\|.*?\|\s*(?P<current>\d+)/(?P<total>\d+)\s*\["
)


@dataclass(slots=True)
class TaskProgressState:
    status_message: str | None = None
    progress_current: int | None = None
    progress_total: int | None = None
    progress_percent: int | None = None


def progress_from_log_line(
    current: TaskProgressState,
    raw_line: str,
) -> TaskProgressState:
    line = raw_line.strip()
    if not line:
        return current

    updated = TaskProgressState(
        status_message=current.status_message,
        progress_current=current.progress_current,
        progress_total=current.progress_total,
        progress_percent=current.progress_percent,
    )

    progress_match = _PROGRESS_RE.search(line)
    if progress_match is not None:
        updated.progress_current = int(progress_match.group("current"))
        updated.progress_total = int(progress_match.group("total"))
        updated.progress_percent = int(progress_match.group("percent"))
        updated.status_message = "sampling"
        return updated

    lower_line = line.lower()
    if line.startswith("Creating Wan") and "pipeline." in line:
        updated.status_message = "creating pipeline"
    elif "Creating WanModel" in line or "loading " in lower_line:
        updated.status_message = "loading checkpoints"
    elif "Generating video ..." in line:
        updated.status_message = "sampling"
    elif "Saving generated video to " in line:
        updated.status_message = "saving video"
    elif line == "generate.py exit code: 0" or "Finished." in line:
        updated.status_message = "finished"
        updated.progress_percent = 100
        if updated.progress_total is not None and updated.progress_current is None:
            updated.progress_current = updated.progress_total
        elif updated.progress_current is not None and updated.progress_total is None:
            updated.progress_total = updated.progress_current
    return updated


def merge_progress_states(
    primary: TaskProgressState,
    fallback: TaskProgressState,
) -> TaskProgressState:
    return TaskProgressState(
        status_message=primary.status_message or fallback.status_message,
        progress_current=(
            primary.progress_current
            if primary.progress_current is not None
            else fallback.progress_current
        ),
        progress_total=(
            primary.progress_total
            if primary.progress_total is not None
            else fallback.progress_total
        ),
        progress_percent=(
            primary.progress_percent
            if primary.progress_percent is not None
            else fallback.progress_percent
        ),
    )
