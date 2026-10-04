"""End-to-end through `childdiary run` with the API mocked."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import unquote_plus

import pytest
import responses
from click.testing import CliRunner

from childdiary_downloader import api, cli, handlers
from childdiary_downloader.cli import main
from childdiary_downloader.notify import NullNotifier
from childdiary_downloader.runner import run_account
from childdiary_downloader.state import State
from tests import factories as f
from tests.conftest import RecordingNotifier, make_config

CONFIG_YAML = """
archive_dir: {archive}
language: pt
accounts:
  - name: Creche Exemplo
    username: familia@example.test
    password: ${{CDD_PASSWORD}}
    children:
      "{maria}": Maria
      "{tomas}": Tomás
routing:
  groups:
    "Sala Girassóis": [Maria]
telegram:
  token: ${{CDD_TOKEN}}
  chat_id: "1"
"""


def mock_api(rsps: Any, entries: list[dict[str, Any]]) -> None:
    rsps.add(responses.POST, api.LOGIN_URL, json={}, status=200)

    def pages(request: Any) -> tuple[int, dict[str, str], str]:
        from urllib.parse import parse_qs, urlparse

        qs = parse_qs(urlparse(request.url).query)
        count, page = int(qs["count"][0]), int(qs["page"][0])
        return 200, {}, json.dumps({"Entries": entries[page * count : (page + 1) * count]})

    rsps.add_callback(responses.GET, api.ENTRIES_URL, callback=pages)


@pytest.fixture
def rsps() -> Any:
    with responses.RequestsMock(assert_all_requests_are_fired=False) as r:
        yield r


def test_run_account_processes_new_entries_oldest_first(
    tmp_path: Path, rsps: Any, notifier: RecordingNotifier
) -> None:
    cfg = make_config(archive_dir=str(tmp_path / "archive"))
    entries = [f.event(), f.magazine(), f.routine(), f.post()]  # newest first, as the API does
    mock_api(rsps, entries)
    db = tmp_path / "state.db"
    with State.open(db) as state:
        processed, failed = run_account(cfg.accounts[0], cfg, state, notifier)
        assert (processed, failed) == (4, 0)
        assert set(state.processed_ids) == {e["Id"] for e in entries}
        # Every archived file was recorded with its hash.
        event_media = state.media_for(entries[0]["Id"])
        assert [m.path.name for m in event_media] == ["2026-03-12_152710_01.pdf"]
        assert event_media[0].size == len(b"%PDF-1.4 fake document")
    with State.open(db) as state:
        assert len(state.processed_ids) == 4
    assert [m.split("\n")[0] for m in notifier.messages] == [
        "[Maria] Rotina Diária:",
        "[Maria] Hoje fizemos pinturas com os dedos.",
        "[Sala Girassóis] Dia da Primavera 🌸",
        "[Maria & Tomás] 📅 Evento: Festa da Primavera",
    ]
    # The event is addressed only to our two children -> Documentos copies.
    assert (tmp_path / "archive/Maria/Documentos/2026-03-12 — Festa da Primavera.pdf").exists()
    assert (tmp_path / "archive/Tomás/Documentos/2026-03-12 — Festa da Primavera.pdf").exists()


def test_old_entries_are_archived_silently(
    tmp_path: Path, rsps: Any, notifier: RecordingNotifier
) -> None:
    cfg = make_config(
        archive_dir=str(tmp_path), telegram={"token": "t", "chat_id": "1", "max_age_days": 3}
    )
    mock_api(rsps, [f.post(created="2020-01-01T10:00:00.000Z")])
    with State.open(":memory:") as state:
        run_account(cfg.accounts[0], cfg, state, notifier)
    assert notifier.calls == []
    assert list((tmp_path / "Maria/2020/2020-01-01").iterdir())


def test_known_entries_are_skipped(tmp_path: Path, rsps: Any, notifier: RecordingNotifier) -> None:
    cfg = make_config(archive_dir=str(tmp_path))
    entry = f.post()
    mock_api(rsps, [entry])
    with State.open(":memory:") as state:
        state.mark_processed(entry["Id"], entry["CreatedOn"])
        assert run_account(cfg.accounts[0], cfg, state, notifier) == (0, 0)
    assert notifier.calls == []


def test_failed_entry_is_recorded_and_retried(
    tmp_path: Path, rsps: Any, notifier: RecordingNotifier, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = make_config(archive_dir=str(tmp_path))
    entry = f.post()
    mock_api(rsps, [entry])
    db = tmp_path / "state.db"

    def boom(url: str) -> bytes:
        raise RuntimeError("cdn down")

    monkeypatch.setattr(handlers, "download_file", boom)
    with State.open(db) as state:
        assert run_account(cfg.accounts[0], cfg, state, notifier) == (0, 1)
        assert state.failed_ids == [entry["Id"]]
    with State.open(db) as state:
        assert state.failed_ids == [entry["Id"]]
        # Next run: the failure forces a full fetch and the entry succeeds.
        monkeypatch.setattr(handlers, "download_file", lambda url: b"ok")
        assert run_account(cfg.accounts[0], cfg, state, notifier) == (1, 0)
        assert state.failed_ids == [] and entry["Id"] in state.processed_ids


def test_group_posts_use_discovered_mapping_when_not_configured(
    tmp_path: Path, rsps: Any, notifier: RecordingNotifier
) -> None:
    cfg = make_config(archive_dir=str(tmp_path), routing={})
    # Tomás's own routine teaches us ROOM_B -> Tomás; the group post then routes there.
    entries = [
        f.magazine(for_items=[f.group(f.ROOM_B_ID, "Sala Papoilas")]),
        f.routine(for_items=[f.child(f.TOMAS_ID, "Tomás", f.ROOM_B_ID)]),
    ]
    mock_api(rsps, entries)
    with State.open(":memory:") as state:
        run_account(cfg.accounts[0], cfg, state, notifier)
    assert (tmp_path / "Tomás/2026/2026-03-11").is_dir()
    assert not (tmp_path / "Sala Papoilas").exists()


# --- CLI -------------------------------------------------------------------


def write_config(tmp_path: Path) -> Path:
    cfg_dir = tmp_path / "cfg"
    cfg_dir.mkdir()
    (cfg_dir / "config.yaml").write_text(
        CONFIG_YAML.format(archive=tmp_path / "archive", maria=f.MARIA_ID, tomas=f.TOMAS_ID)
    )
    (cfg_dir / ".env").write_text("CDD_PASSWORD=pw\nCDD_TOKEN=tok\n")
    return cfg_dir / "config.yaml"


def test_cli_run_no_telegram(tmp_path: Path, rsps: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CDD_PASSWORD", raising=False)
    monkeypatch.delenv("CDD_TOKEN", raising=False)
    config_file = write_config(tmp_path)
    mock_api(rsps, [f.post()])
    result = CliRunner().invoke(
        main,
        [
            "--config",
            str(config_file),
            "--data-dir",
            str(tmp_path / "data"),
            "run",
            "--no-telegram",
        ],
    )
    assert result.exit_code == 0, result.output
    assert (tmp_path / "data/state.db").exists()
    assert (tmp_path / "data/logs/childdiary.log").exists()
    assert (tmp_path / "archive/Maria/2026/2026-03-10/2026-03-10_101530_01.jpg").exists()
    assert not any(c.request.url.startswith("https://api.telegram.org") for c in rsps.calls)


def test_cli_run_sends_failure_alert_through_real_bot(
    tmp_path: Path, rsps: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("CDD_PASSWORD", raising=False)
    monkeypatch.delenv("CDD_TOKEN", raising=False)
    config_file = write_config(tmp_path)
    rsps.add(responses.POST, api.LOGIN_URL, status=401)
    rsps.add(responses.POST, "https://api.telegram.org/bottok/sendMessage", json={"ok": True})
    result = CliRunner().invoke(
        main, ["--config", str(config_file), "--data-dir", str(tmp_path), "run", "--no-telegram"]
    )
    assert result.exit_code == 1
    alert = [c for c in rsps.calls if "sendMessage" in c.request.url]
    assert len(alert) == 1
    assert "Erro ao correr conta(s)" in unquote_plus(alert[0].request.body)


def test_cli_missing_config_is_friendly(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        main, ["--config", str(tmp_path / "x.yaml"), "--data-dir", str(tmp_path), "run"]
    )
    assert result.exit_code == 1
    assert "Configuration file not found" in result.output


def test_cli_lock_prevents_overlap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import fcntl

    config_file = write_config(tmp_path)
    data = tmp_path / "data"
    data.mkdir()
    holder = (data / ".lock").open("w")
    fcntl.flock(holder, fcntl.LOCK_EX | fcntl.LOCK_NB)
    result = CliRunner().invoke(
        main, ["--config", str(config_file), "--data-dir", str(data), "run"]
    )
    assert result.exit_code == 0
    assert "already in progress" in result.output


def test_cli_version() -> None:
    result = CliRunner().invoke(main, ["--version"])
    assert result.exit_code == 0 and "childdiary" in result.output


def test_null_notifier_logs_only(caplog: pytest.LogCaptureFixture) -> None:
    n = NullNotifier()
    n.send_message("olá\nmundo")
    assert "olá | mundo" in caplog.text


def test_cli_list_groups(tmp_path: Path, rsps: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CDD_PASSWORD", raising=False)
    monkeypatch.delenv("CDD_TOKEN", raising=False)
    config_file = write_config(tmp_path)
    mock_api(rsps, [f.post(), f.magazine()])
    result = CliRunner().invoke(
        main, ["--config", str(config_file), "--data-dir", str(tmp_path), "list-groups"]
    )
    assert result.exit_code == 0, result.output
    assert "Maria" in result.output and "Sala Girassóis" in result.output


def test_cli_discover(tmp_path: Path, rsps: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CDD_PASSWORD", raising=False)
    monkeypatch.delenv("CDD_TOKEN", raising=False)
    config_file = write_config(tmp_path)
    mock_api(rsps, [f.post(), f.routine(), f.post(entry_id="e1000000-0000-0000-0000-000000000002")])
    result = CliRunner().invoke(
        main, ["--config", str(config_file), "--data-dir", str(tmp_path), "discover"]
    )
    assert result.exit_code == 0, result.output
    dump = json.loads((tmp_path / "discovery_dump.json").read_text())
    assert sorted(dump) == ["1", "2"]
    assert cli.console is not None


def test_cli_run_migrates_legacy_state_then_status(
    tmp_path: Path, rsps: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("CDD_PASSWORD", raising=False)
    monkeypatch.delenv("CDD_TOKEN", raising=False)
    config_file = write_config(tmp_path)
    data = tmp_path / "data"
    data.mkdir()
    entry = f.post()
    (data / "state.json").write_text(
        json.dumps({"processed_ids": {entry["Id"]: entry["CreatedOn"]}, "failed_ids": []})
    )
    mock_api(rsps, [entry])
    runner = CliRunner()
    result = runner.invoke(
        main, ["--config", str(config_file), "--data-dir", str(data), "run", "--no-telegram"]
    )
    assert result.exit_code == 0, result.output
    assert "Fetched 1 entries, 0 new" in result.output
    assert (data / "state.json.migrated").exists() and not (data / "state.json").exists()
    result = runner.invoke(main, ["--config", str(config_file), "--data-dir", str(data), "status"])
    assert result.exit_code == 0, result.output
    assert "Entries processed: 1" in result.output
