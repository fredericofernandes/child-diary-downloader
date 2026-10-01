"""Built-in scheduler for ``childdiary daemon`` (Docker and NAS installs).

A long-running loop computes the next fire time from a cron expression in the
school's timezone, sleeps until then (touching a heartbeat file every minute
so a HEALTHCHECK can tell a live daemon from a hung one) and then calls the
run callback. No cron binary inside the container, same behaviour everywhere.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from croniter import croniter

log = logging.getLogger(__name__)

HEARTBEAT_INTERVAL = 60.0
# A heartbeat older than this means the daemon is stuck (or dead).
HEARTBEAT_MAX_AGE = timedelta(minutes=5)
DEFAULT_SCHEDULE = "0 19 * * *"


@dataclass(frozen=True)
class DaemonFiles:
    heartbeat: Path
    last_run: Path

    @classmethod
    def in_dir(cls, data_dir: Path) -> DaemonFiles:
        return cls(heartbeat=data_dir / "heartbeat", last_run=data_dir / "last_run.json")


def validate_schedule(expression: str) -> None:
    if not croniter.is_valid(expression):
        raise ValueError(f"Invalid cron expression: {expression!r}")


def touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()


def record_run(path: Path, exit_code: int, started: datetime, finished: datetime) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "exit_code": exit_code,
                "started": started.isoformat(timespec="seconds"),
                "finished": finished.isoformat(timespec="seconds"),
            }
        )
    )


def run_daemon(
    schedule: str,
    tz: ZoneInfo,
    files: DaemonFiles,
    run_once: Callable[[], int],
    *,
    run_on_start: bool = False,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], datetime] | None = None,
    max_runs: int | None = None,
) -> None:
    """Loop forever (or ``max_runs`` times, for tests) running on schedule.

    ``sleep`` and ``now`` are injectable so tests can drive the loop without
    waiting. Exceptions from ``run_once`` are logged and the loop continues:
    a bad day at the API must not kill the daemon.
    """
    validate_schedule(schedule)
    clock = now or (lambda: datetime.now(tz))
    runs = 0

    def fire() -> None:
        nonlocal runs
        started = clock()
        log.info("Scheduled run starting.")
        try:
            code = run_once()
        except Exception:
            log.exception("Scheduled run crashed.")
            code = 1
        finished = clock()
        record_run(files.last_run, code, started, finished)
        log.info("Scheduled run finished with exit code %d.", code)
        runs += 1

    touch(files.heartbeat)
    if run_on_start:
        fire()

    while max_runs is None or runs < max_runs:
        current = clock()
        next_fire = croniter(schedule, current).get_next(datetime)
        log.info("Next run at %s.", next_fire.isoformat(timespec="minutes"))
        while (remaining := (next_fire - clock()).total_seconds()) > 0:
            sleep(min(remaining, HEARTBEAT_INTERVAL))
            touch(files.heartbeat)
        fire()


def check_health(files: DaemonFiles, now: datetime | None = None) -> tuple[bool, str]:
    """Liveness for Docker HEALTHCHECK: recent heartbeat, last run not crashed."""
    if not files.heartbeat.exists():
        return False, "no heartbeat yet"
    age = (now or datetime.now()) - datetime.fromtimestamp(files.heartbeat.stat().st_mtime)
    if age > HEARTBEAT_MAX_AGE:
        return False, f"heartbeat is {int(age.total_seconds())}s old"
    if files.last_run.exists():
        try:
            last = json.loads(files.last_run.read_text())
        except ValueError:
            return False, "last_run.json unreadable"
        if last.get("exit_code", 0) != 0:
            return False, f"last run failed (exit {last['exit_code']}) at {last.get('finished')}"
        return True, f"ok, last run {last.get('finished')}"
    return True, "ok, no run yet"
