"""Digest mode: hold everything a run produces and send it as one message
(plus one batch of files) at the end, instead of a message per entry.

Meant for email, or for anyone who finds a message per post too chatty.
Long digests are split at entry boundaries so no service rejects them.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from childdiary_downloader.i18n import Strings
from childdiary_downloader.notify.base import Notifier

log = logging.getLogger(__name__)

# Below Telegram's 4096 and comfortable for every other service.
MAX_CHUNK = 3500
SEPARATOR = "\n\n— — —\n\n"


class DigestNotifier:
    def __init__(self, inner: Notifier, strings: Strings, now: datetime | None = None) -> None:
        self._inner = inner
        self._strings = strings
        self._date = (now or datetime.now()).strftime(strings.caption_date_format)
        self._texts: list[str] = []
        self._files: list[Path] = []

    def __repr__(self) -> str:
        return f"DigestNotifier({self._inner!r})"

    def send_message(self, text: str) -> None:
        self._texts.append(text.strip())

    def send_files(self, paths: list[Path], text: str = "") -> None:
        self._files.extend(paths)

    def flush(self) -> None:
        """Deliver what was collected; safe to call with nothing collected."""
        if not self._texts and not self._files:
            return
        title = self._strings.digest_title.format(date=self._date)
        try:
            for chunk in self._chunks(title):
                self._inner.send_message(chunk)
            if self._files:
                caption = self._strings.digest_files.format(date=self._date, count=len(self._files))
                self._inner.send_files(self._files, caption)
        finally:
            self._texts.clear()
            self._files.clear()

    def _chunks(self, title: str) -> list[str]:
        chunks: list[str] = []
        current = title
        for text in self._texts:
            candidate = current + SEPARATOR + text
            if len(candidate) > MAX_CHUNK and current != title:
                chunks.append(current)
                current = title + SEPARATOR + text
            else:
                current = candidate
        if current != title or not chunks:
            chunks.append(current)
        return chunks
