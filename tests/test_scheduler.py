from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from click.testing import CliRunner

from childdiary_downloader.cli import main
from childdiary_downloader.scheduler import (
    HEARTBEAT_INTERVAL,
    DaemonFiles,
    check_health,
    run_daemon,
    validate_schedule,
)

TZ = ZoneInfo("Europe/Lisbon")


class FakeClock:
    def __init__(self, start: datetime) -> None:
        self.t = start

    def now(self) -> datetime:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.t += timedelta(seconds=seconds)


def test_validate_schedule() -> None:
    validate_schedule("0 19 * * *")
    with pytest.raises(ValueError, match="Invalid cron"):
        validate_schedule("every day at 7pm")


def test_daemon_runs_at_next_cron_time_and_keeps_heartbeat(tmp_path: Path) -> None:
    clock = FakeClock(datetime(2026, 3, 10, 18, 0, tzinfo=TZ))
    files = DaemonFiles.in_dir(tmp_path)
    fired: list[datetime] = []
    sleeps: list[float] = []

    def sleep(s: float) -> None:
        sleeps.append(s)
        clock.sleep(s)

    run_daemon(
        "0 19 * * *",
        TZ,
        files,
        lambda: fired.append(clock.now()) or 0,
        sleep=sleep,
        now=clock.now,
        max_runs=2,
    )
    assert fired == [
        datetime(2026, 3, 10, 19, 0, tzinfo=TZ),
        datetime(2026, 3, 11, 19, 0, tzinfo=TZ),
    ]
    assert max(sleeps) <= HEARTBEAT_INTERVAL  # heartbeat touched at least every minute
    assert files.heartbeat.exists()
    last = json.loads(files.last_run.read_text())
    assert last["exit_code"] == 0 and last["finished"].startswith("2026-03-11T19:00")


def test_daemon_run_on_start_and_crash_survival(tmp_path: Path) -> None:
    clock = FakeClock(datetime(2026, 3, 10, 18, 0, tzinfo=TZ))
    files = DaemonFiles.in_dir(tmp_path)
    calls = {"n": 0}

    def flaky() -> int:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("api down")
        return 0

    run_daemon(
        "0 19 * * *",
        TZ,
        files,
        flaky,
        run_on_start=True,
        sleep=clock.sleep,
        now=clock.now,
        max_runs=2,
    )
    assert calls["n"] == 2
    assert json.loads(files.last_run.read_text())["exit_code"] == 0


def test_check_health_states(tmp_path: Path) -> None:
    files = DaemonFiles.in_dir(tmp_path)
    assert check_health(files) == (False, "no heartbeat yet")
    files.heartbeat.touch()
    assert check_health(files)[0] is True
    stale = datetime.now() + timedelta(minutes=10)
    ok, detail = check_health(files, now=stale)
    assert ok is False and "heartbeat is" in detail
    files.last_run.write_text(json.dumps({"exit_code": 1, "finished": "2026-03-10T19:00:00"}))
    ok, detail = check_health(files)
    assert ok is False and "last run failed" in detail
    files.last_run.write_text("{not json")
    assert check_health(files)[0] is False


def test_cli_health_and_daemon_validation(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        main, ["--config", str(tmp_path / "c.yaml"), "--data-dir", str(tmp_path), "health"]
    )
    assert result.exit_code == 1 and "no heartbeat" in result.output
    (tmp_path / "heartbeat").touch()
    result = runner.invoke(
        main, ["--config", str(tmp_path / "c.yaml"), "--data-dir", str(tmp_path), "health"]
    )
    assert result.exit_code == 0
    result = runner.invoke(
        main,
        [
            "--config",
            str(tmp_path / "c.yaml"),
            "--data-dir",
            str(tmp_path),
            "daemon",
            "--schedule",
            "nope",
        ],
    )
    assert result.exit_code == 1 and "Invalid cron" in result.output
