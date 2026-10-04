from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import responses
from click.testing import CliRunner

from childdiary_downloader import api, checks
from childdiary_downloader.checks import run_checks
from childdiary_downloader.cli import main
from childdiary_downloader.state import State
from tests import factories as f
from tests.conftest import make_config
from tests.test_runner import mock_api, write_config


@pytest.fixture
def rsps() -> Any:
    with responses.RequestsMock(assert_all_requests_are_fired=False) as r:
        yield r


def test_checks_all_green(tmp_path: Path, rsps: Any) -> None:
    cfg = make_config(archive_dir=str(tmp_path / "a"), telegram={"token": "tok", "chat_id": "1"})
    mock_api(rsps, [f.post()])
    rsps.add(responses.POST, "https://api.telegram.org/bottok/sendMessage", json={"ok": True})
    results = {r.name: r for r in run_checks(cfg, send_test_message=True)}
    assert results["archive folder"].ok and (tmp_path / "a").is_dir()
    assert results["account 'Creche Exemplo'"].ok
    assert "1 mention your children" in results["account 'Creche Exemplo'"].detail
    assert results["telegram"].detail == "test message sent"


def test_checks_detect_wrong_children_and_bad_login(tmp_path: Path, rsps: Any) -> None:
    cfg = make_config(archive_dir=str(tmp_path))
    mock_api(rsps, [f.post(for_items=[f.child(f.OTHER_CHILD_ID, "Outra", f.ROOM_A_ID)])])
    results = {r.name: r for r in run_checks(cfg)}
    assert not results["account 'Creche Exemplo'"].ok
    assert "none mention the configured children" in results["account 'Creche Exemplo'"].detail
    assert results["telegram"].detail.startswith("not configured")

    rsps.reset()
    rsps.add(responses.POST, api.LOGIN_URL, status=401)
    results = {r.name: r for r in run_checks(cfg)}
    assert "401" in results["account 'Creche Exemplo'"].detail


def test_exiftool_missing_is_reported_but_not_fatal(
    tmp_path: Path, rsps: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(checks.shutil, "which", lambda name: None)
    monkeypatch.delenv("CDD_PASSWORD", raising=False)
    config_file = write_config(tmp_path)
    mock_api(rsps, [f.post()])
    result = CliRunner().invoke(
        main, ["--config", str(config_file), "--data-dir", str(tmp_path), "check"]
    )
    assert result.exit_code == 0, result.output
    assert "FAIL exiftool" in result.output
    assert "OK  account" in result.output


def test_dry_run_touches_nothing(
    tmp_path: Path, rsps: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("CDD_PASSWORD", raising=False)
    config_file = write_config(tmp_path)
    mock_api(rsps, [f.post()])
    result = CliRunner().invoke(
        main,
        ["--config", str(config_file), "--data-dir", str(tmp_path / "data"), "run", "--dry-run"],
    )
    assert result.exit_code == 0, result.output
    assert "Would process type=1" in result.output
    assert not (tmp_path / "archive").exists()
    assert (
        not (tmp_path / "data" / "state.db").exists()
        or State.open(tmp_path / "data" / "state.db").stats().done == 0
    )
