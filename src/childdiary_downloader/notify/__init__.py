"""Notifiers. Everything goes through apprise; ``NullNotifier`` only logs."""

from __future__ import annotations

from childdiary_downloader.config import NotifierConfig
from childdiary_downloader.notify.apprise import AppriseNotifier
from childdiary_downloader.notify.base import NotificationError, Notifier, NullNotifier


def build_notifier(notifiers: list[NotifierConfig]) -> Notifier:
    """The notifier for a run: apprise over every configured service, or a
    NullNotifier when none is configured (archive-only)."""
    if not notifiers:
        return NullNotifier()
    return AppriseNotifier([(n.url, n.media) for n in notifiers])


__all__ = ["AppriseNotifier", "NotificationError", "Notifier", "NullNotifier", "build_notifier"]
