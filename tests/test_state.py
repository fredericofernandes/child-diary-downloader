import json
from pathlib import Path

from childdiary_downloader.state import State


def test_load_missing_file_gives_empty_state(tmp_path: Path) -> None:
    state = State.load(tmp_path / "state.json")
    assert state.processed_ids == {} and state.failed_ids == []


def test_round_trip_and_atomic_write(tmp_path: Path) -> None:
    path = tmp_path / "data" / "state.json"
    state = State()
    state.mark_failed("a")
    state.mark_failed("a")  # idempotent
    state.mark_processed("a", "2026-01-01T00:00:00Z")  # clears the failure
    state.mark_processed("b", "2026-01-02T00:00:00Z")
    state.save(path)
    assert not path.with_suffix(".json.tmp").exists()
    loaded = State.load(path)
    assert loaded.processed_ids == {"a": "2026-01-01T00:00:00Z", "b": "2026-01-02T00:00:00Z"}
    assert loaded.failed_ids == []
    assert json.loads(path.read_text())["failed_ids"] == []


def test_legacy_file_without_keys(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    path.write_text('{"processed_ids": {"x": "d"}}')
    assert State.load(path).failed_ids == []
