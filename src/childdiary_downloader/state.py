"""Persistent state in SQLite: which entries were processed, which failed and
why, and which files each entry produced (path, size, SHA-256).

One file, ``state.db``, in the data folder. The first run migrates an existing
``state.json`` from older versions and renames it to ``state.json.migrated``.
Every change is its own transaction, so a crash mid-run never corrupts the
state (the old JSON was rewritten whole after each entry).
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType

log = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS entries (
    id           TEXT PRIMARY KEY,
    created_on   TEXT,
    status       TEXT NOT NULL CHECK (status IN ('done', 'failed')),
    processed_at TEXT NOT NULL,
    error        TEXT
);
CREATE INDEX IF NOT EXISTS entries_status ON entries (status);
CREATE INDEX IF NOT EXISTS entries_created ON entries (created_on);

CREATE TABLE IF NOT EXISTS media (
    entry_id TEXT NOT NULL,
    media_id TEXT NOT NULL,
    path     TEXT NOT NULL,
    size     INTEGER NOT NULL,
    sha256   TEXT NOT NULL,
    PRIMARY KEY (entry_id, path)
);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""
SCHEMA_VERSION = "1"


@dataclass(frozen=True)
class SavedMedia:
    media_id: str
    path: Path
    size: int
    sha256: str


@dataclass(frozen=True)
class Stats:
    done: int
    failed: int
    media_files: int
    media_bytes: int
    first_entry: str | None
    last_entry: str | None
    last_run: str | None


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class State:
    """Open with ``State.open(db_path)``; ``":memory:"`` works for tests."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        conn.executescript(SCHEMA)
        conn.execute(
            "INSERT OR IGNORE INTO meta (key, value) VALUES ('schema_version', ?)",
            (SCHEMA_VERSION,),
        )
        conn.commit()

    @classmethod
    def open(cls, db_path: Path | str, legacy_json: Path | None = None) -> State:
        if isinstance(db_path, Path):
            db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA journal_mode=WAL")
        state = cls(conn)
        if legacy_json is not None and legacy_json.exists():
            state._migrate_legacy(legacy_json)
        return state

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> State:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    # -- migration -------------------------------------------------------------

    def _migrate_legacy(self, legacy_json: Path) -> None:
        """Import state.json from versions before 0.2 and rename it."""
        try:
            data = json.loads(legacy_json.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            log.warning("Ignoring unreadable legacy state %s: %s", legacy_json, e)
            return
        processed = data.get("processed_ids") or {}
        failed = data.get("failed_ids") or []
        now = _now()
        with self._conn:
            self._conn.executemany(
                "INSERT OR IGNORE INTO entries (id, created_on, status, processed_at) "
                "VALUES (?, ?, 'done', ?)",
                [(eid, created, now) for eid, created in processed.items()],
            )
            self._conn.executemany(
                "INSERT OR IGNORE INTO entries (id, status, processed_at, error) "
                "VALUES (?, 'failed', ?, 'migrated from state.json')",
                [(eid, now) for eid in failed if eid not in processed],
            )
            self._conn.execute(
                "INSERT OR REPLACE INTO meta (key, value) VALUES ('migrated_from', ?)",
                (str(legacy_json),),
            )
        legacy_json.rename(legacy_json.with_suffix(legacy_json.suffix + ".migrated"))
        log.info(
            "Migrated %d processed and %d failed entries from %s.",
            len(processed),
            len(failed),
            legacy_json.name,
        )

    # -- reads -----------------------------------------------------------------

    @property
    def processed_ids(self) -> dict[str, str]:
        rows = self._conn.execute(
            "SELECT id, created_on FROM entries WHERE status = 'done'"
        ).fetchall()
        return {eid: created or "" for eid, created in rows}

    @property
    def failed_ids(self) -> list[str]:
        rows = self._conn.execute(
            "SELECT id FROM entries WHERE status = 'failed' ORDER BY processed_at"
        ).fetchall()
        return [eid for (eid,) in rows]

    def media_for(self, entry_id: str) -> list[SavedMedia]:
        rows = self._conn.execute(
            "SELECT media_id, path, size, sha256 FROM media WHERE entry_id = ? ORDER BY path",
            (entry_id,),
        ).fetchall()
        return [SavedMedia(m, Path(p), s, h) for m, p, s, h in rows]

    def stats(self) -> Stats:
        done, failed = self._conn.execute(
            "SELECT COALESCE(SUM(status = 'done'), 0), COALESCE(SUM(status = 'failed'), 0) "
            "FROM entries"
        ).fetchone()
        files, nbytes = self._conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(size), 0) FROM media"
        ).fetchone()
        first, last = self._conn.execute(
            "SELECT MIN(created_on), MAX(created_on) FROM entries WHERE status = 'done'"
        ).fetchone()
        last_run = self._conn.execute("SELECT MAX(processed_at) FROM entries").fetchone()[0]
        return Stats(done, failed, files, nbytes, first, last, last_run)

    # -- writes ----------------------------------------------------------------

    def mark_processed(self, entry_id: str, created_on: str) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT INTO entries (id, created_on, status, processed_at, error) "
                "VALUES (?, ?, 'done', ?, NULL) "
                "ON CONFLICT(id) DO UPDATE SET created_on = excluded.created_on, "
                "status = 'done', processed_at = excluded.processed_at, error = NULL",
                (entry_id, created_on, _now()),
            )

    def mark_failed(self, entry_id: str, error: str = "") -> None:
        with self._conn:
            self._conn.execute(
                "INSERT INTO entries (id, status, processed_at, error) "
                "VALUES (?, 'failed', ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET status = 'failed', "
                "processed_at = excluded.processed_at, error = excluded.error",
                (entry_id, _now(), error[:500]),
            )

    def record_media(self, entry_id: str, saved: list[SavedMedia]) -> None:
        if not saved:
            return
        with self._conn:
            self._conn.executemany(
                "INSERT OR REPLACE INTO media (entry_id, media_id, path, size, sha256) "
                "VALUES (?, ?, ?, ?, ?)",
                [(entry_id, m.media_id, str(m.path), m.size, m.sha256) for m in saved],
            )

    def forget_since(self, date: str) -> int:
        """Drop entries created on or after ``date`` (YYYY-MM-DD) so the next
        run processes them again. Returns how many were forgotten."""
        with self._conn:
            cur = self._conn.execute("DELETE FROM entries WHERE created_on >= ?", (date,))
            return cur.rowcount
