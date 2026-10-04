"""Notifier protocol and the no-op implementation."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Protocol

log = logging.getLogger(__name__)


class NotificationError(Exception):
    """A notification could not be delivered. The entry is retried next run."""


class Notifier(Protocol):
    """Receives the family-facing output of a run.

    ``send_files`` gets photos, videos or documents already on disk, with an
    optional text; how they are grouped (albums, one per message) is up to
    the service. Implementations raise NotificationError when delivery fails
    so the runner can retry the entry later; they never raise for an
    unsupported file, which they log and skip.
    """

    def send_message(self, text: str) -> None: ...
    def send_files(self, paths: list[Path], text: str = "") -> None: ...
    def flush(self) -> None:
        """Called once at the end of a run; digests deliver here."""
        ...


class NullNotifier:
    """Logs instead of sending (``--no-notify``, dry runs, archive-only setups)."""

    def send_message(self, text: str) -> None:
        log.info("notify(message): %s", text[:120].replace("\n", " | "))

    def send_files(self, paths: list[Path], text: str = "") -> None:
        log.info("notify(files): %d file(s) %r", len(paths), text[:80])

    def flush(self) -> None:
        pass
