import json
import sqlite3
from pathlib import Path

from childdiary_downloader.state import SavedMedia, State, sha256_of


def test_fresh_database_is_empty(tmp_path: Path) -> None:
    with State.open(tmp_path / "data" / "state.db") as state:
        assert state.processed_ids == {} and state.failed_ids == []
        st = state.stats()
        assert (st.done, st.failed, st.media_files) == (0, 0, 0)


def test_marks_persist_and_failures_clear(tmp_path: Path) -> None:
    db = tmp_path / "state.db"
    with State.open(db) as state:
        state.mark_failed("a", "boom")
        state.mark_failed("a", "boom again")  # idempotent, keeps the latest error
        state.mark_processed("a", "2026-01-01T00:00:00Z")  # clears the failure
        state.mark_processed("b", "2026-01-02T00:00:00Z")
        state.mark_failed("c", "x" * 1000)
    with State.open(db) as state:
        assert state.processed_ids == {"a": "2026-01-01T00:00:00Z", "b": "2026-01-02T00:00:00Z"}
        assert state.failed_ids == ["c"]
        st = state.stats()
        assert (st.done, st.failed) == (2, 1)
        assert st.first_entry == "2026-01-01T00:00:00Z" and st.last_entry == "2026-01-02T00:00:00Z"
    error = sqlite3.connect(db).execute("SELECT error FROM entries WHERE id = 'c'").fetchone()[0]
    assert len(error) == 500


def test_media_records(tmp_path: Path) -> None:
    f = tmp_path / "x.jpg"
    f.write_bytes(b"abc")
    with State.open(":memory:") as state:
        saved = [SavedMedia("m1", f, 3, sha256_of(f))]
        state.record_media("e1", saved)
        state.record_media("e1", saved)  # replace, not duplicate
        state.record_media("e2", [])
        assert state.media_for("e1") == saved
        assert state.media_for("e2") == []
        assert state.stats().media_files == 1 and state.stats().media_bytes == 3
    assert sha256_of(f) == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_forget_since(tmp_path: Path) -> None:
    with State.open(":memory:") as state:
        state.mark_processed("old", "2025-12-31T23:59:59Z")
        state.mark_processed("new", "2026-01-01T00:00:00Z")
        state.mark_failed("f")
        assert state.forget_since("2026-01-01") == 1
        assert set(state.processed_ids) == {"old"}
        assert state.failed_ids == ["f"]  # no created_on: never matched by a date


def test_legacy_json_is_migrated_once(tmp_path: Path) -> None:
    legacy = tmp_path / "state.json"
    legacy.write_text(
        json.dumps(
            {
                "processed_ids": {"a": "2026-01-01T00:00:00Z", "b": "2026-01-02T00:00:00Z"},
                "failed_ids": ["b", "c"],  # b is both: processed wins
            }
        )
    )
    with State.open(tmp_path / "state.db", legacy) as state:
        assert state.processed_ids == {"a": "2026-01-01T00:00:00Z", "b": "2026-01-02T00:00:00Z"}
        assert state.failed_ids == ["c"]
    assert not legacy.exists()
    assert (tmp_path / "state.json.migrated").exists()
    # Opening again with the (now missing) legacy path changes nothing.
    with State.open(tmp_path / "state.db", legacy) as state:
        assert len(state.processed_ids) == 2


def test_unreadable_legacy_json_is_ignored(tmp_path: Path) -> None:
    legacy = tmp_path / "state.json"
    legacy.write_text("{not json")
    with State.open(tmp_path / "state.db", legacy) as state:
        assert state.processed_ids == {}
    assert legacy.exists()
