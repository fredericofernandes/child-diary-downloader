"""Notifications through apprise: one URL per service (Telegram, ntfy, email,
Discord, Slack, Matrix…), all handled by the same code.

Telegram deserves a note because it is the most used: apprise's ``tgram://``
plugin groups photos and videos into albums of up to 10, puts a short text as
the caption of the first item, sends other files as documents and respects
the 10 MB / 50 MB upload limits.
"""

from __future__ import annotations

import logging
from pathlib import Path

import apprise

from childdiary_downloader.notify.base import NotificationError

log = logging.getLogger(__name__)

MEDIA_TAG = "media"
TEXT_TAG = "text"


class AppriseNotifier:
    def __init__(self, urls: list[tuple[str, bool]]) -> None:
        """``urls``: (apprise URL, receives files?) per service."""
        self._apprise = apprise.Apprise()
        self._names: list[str] = []
        for url, with_media in urls:
            tags = [TEXT_TAG, MEDIA_TAG] if with_media else [TEXT_TAG]
            if not self._apprise.add(url, tag=tags):
                raise ValueError(f"apprise did not accept this URL: {_redact(url)}")
            self._names.append(_redact(url))
        self.has_media_targets = any(with_media for _, with_media in urls)

    def __repr__(self) -> str:
        return f"AppriseNotifier({', '.join(self._names)})"

    def send_message(self, text: str) -> None:
        if not self._apprise.notify(body=text, tag=TEXT_TAG):
            raise NotificationError("at least one service refused the message")

    def flush(self) -> None:
        pass

    def send_files(self, paths: list[Path], text: str = "") -> None:
        if not paths or not self.has_media_targets:
            return
        attach = apprise.AppriseAttachment()
        for path in paths:
            attach.add(str(path))
        if not self._apprise.notify(body=text or " ", attach=attach, tag=MEDIA_TAG):
            raise NotificationError(f"at least one service refused {len(paths)} file(s)")


def _redact(url: str) -> str:
    """``tgram://123:ABC/42`` -> ``tgram://…/42`` for logs and errors."""
    scheme, sep, rest = url.partition("://")
    if not sep:
        return url
    parts = rest.split("/")
    if parts and parts[0]:
        parts[0] = "…"
    return f"{scheme}://{'/'.join(parts)}"
