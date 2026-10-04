"""Notifiers. Everything goes through apprise; ``NullNotifier`` only logs,
``DigestNotifier`` holds a run's output for one message at the end."""

from __future__ import annotations

from pathlib import Path

from childdiary_downloader.config import NotifierConfig
from childdiary_downloader.i18n import Strings
from childdiary_downloader.notify.apprise import AppriseNotifier
from childdiary_downloader.notify.base import NotificationError, Notifier, NullNotifier
from childdiary_downloader.notify.digest import DigestNotifier


class CompositeNotifier:
    """Fans every call out to several notifiers."""

    def __init__(self, parts: list[Notifier]) -> None:
        self.parts = parts

    def __repr__(self) -> str:
        return f"CompositeNotifier({', '.join(repr(p) for p in self.parts)})"

    def send_message(self, text: str) -> None:
        for part in self.parts:
            part.send_message(text)

    def send_files(self, paths: list[Path], text: str = "") -> None:
        for part in self.parts:
            part.send_files(paths, text)

    def flush(self) -> None:
        for part in self.parts:
            part.flush()


def build_notifier(notifiers: list[NotifierConfig], strings: Strings) -> Notifier:
    """The notifier for a run: immediate services share one apprise instance,
    digest services share another behind a DigestNotifier; none configured
    means archive-only."""
    immediate = [(n.url, n.media) for n in notifiers if n.mode == "immediate"]
    digest = [(n.url, n.media) for n in notifiers if n.mode == "digest"]
    parts: list[Notifier] = []
    if immediate:
        parts.append(AppriseNotifier(immediate, strings))
    if digest:
        parts.append(DigestNotifier(AppriseNotifier(digest, strings), strings))
    if not parts:
        return NullNotifier()
    return parts[0] if len(parts) == 1 else CompositeNotifier(parts)


__all__ = [
    "AppriseNotifier",
    "CompositeNotifier",
    "DigestNotifier",
    "NotificationError",
    "Notifier",
    "NullNotifier",
    "build_notifier",
]
