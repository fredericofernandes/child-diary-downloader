"""Notifier protocol and the no-op implementation."""

from __future__ import annotations

import logging
from typing import IO, Protocol

log = logging.getLogger(__name__)

MediaItem = tuple[IO[bytes], str, str]  # (open file, extension, caption)


class Notifier(Protocol):
    """Anything that can receive the family-facing output of a run.

    Implementations must tolerate being called with files that are large or
    of unknown type; what they cannot deliver they should log and skip,
    never raise, so the archive side of a run is unaffected.
    """

    def send_message(self, text: str) -> None: ...
    def send_photo(self, fh: IO[bytes], caption: str = "") -> None: ...
    def send_video(self, fh: IO[bytes], caption: str = "") -> None: ...
    def send_document(self, fh: IO[bytes], caption: str = "") -> None: ...
    def send_media_group(self, items: list[MediaItem]) -> None: ...


class NullNotifier:
    """Logs instead of sending (``--no-telegram`` and archive-only setups)."""

    def send_message(self, text: str) -> None:
        log.info("notify(message): %s", text[:120].replace("\n", " | "))

    def send_photo(self, fh: IO[bytes], caption: str = "") -> None:
        log.info("notify(photo) caption=%r", caption[:80])

    def send_video(self, fh: IO[bytes], caption: str = "") -> None:
        log.info("notify(video) caption=%r", caption[:80])

    def send_document(self, fh: IO[bytes], caption: str = "") -> None:
        log.info("notify(document) caption=%r", caption[:80])

    def send_media_group(self, items: list[MediaItem]) -> None:
        log.info("notify(media group) %d items", len(items))
