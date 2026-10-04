from __future__ import annotations

from pathlib import Path
from typing import Any

import apprise
import pytest

from childdiary_downloader.config import NotifierConfig
from childdiary_downloader.notify import (
    AppriseNotifier,
    NotificationError,
    NullNotifier,
    build_notifier,
)
from childdiary_downloader.notify.apprise import _redact


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    def fake_notify(
        self: apprise.Apprise, body: str = "", tag: Any = None, attach: Any = None, **kw: Any
    ) -> bool:
        files = [a.path for a in attach] if attach else []
        calls.append({"body": body, "tag": tag, "files": files, "targets": len(self)})
        return not body.startswith("FAIL")

    monkeypatch.setattr(apprise.Apprise, "notify", fake_notify)
    return calls


def test_build_notifier_without_services_is_null() -> None:
    assert isinstance(build_notifier([]), NullNotifier)


def test_message_goes_to_text_targets_and_files_to_media_targets(
    sent: list[dict[str, Any]], tmp_path: Path
) -> None:
    photo = tmp_path / "a.jpg"
    photo.write_bytes(b"x")
    notifier = build_notifier(
        [
            NotifierConfig(url="tgram://123:ABC/42/", media=True, name="telegram"),
            NotifierConfig(url="mailto://user:pw@example.com?to=a@b.c", media=False, name="email"),
        ]
    )
    assert repr(notifier) == "AppriseNotifier(tgram://…/42/, mailto://…)"
    notifier.send_message("olá")
    notifier.send_files([photo], "legenda")
    assert sent[0] == {"body": "olá", "tag": "text", "files": [], "targets": 2}
    assert sent[1]["tag"] == "media" and sent[1]["body"] == "legenda"
    assert sent[1]["files"] == [str(photo)]


def test_files_are_skipped_when_no_media_target(sent: list[dict[str, Any]], tmp_path: Path) -> None:
    notifier = AppriseNotifier([("ntfy://ntfy.sh/x", False)])
    notifier.send_files([tmp_path / "a.jpg"], "x")
    notifier.send_files([], "x")
    assert sent == []


def test_delivery_failure_raises(sent: list[dict[str, Any]]) -> None:
    notifier = AppriseNotifier([("ntfy://ntfy.sh/x", True)])
    with pytest.raises(NotificationError):
        notifier.send_message("FAIL please")


def test_bad_url_is_rejected_with_secret_redacted() -> None:
    with pytest.raises(ValueError, match="not-a-service://…"):
        AppriseNotifier([("not-a-service://secret-token/1", True)])


def test_redact() -> None:
    assert _redact("tgram://123:ABC/42/") == "tgram://…/42/"
    assert _redact("ntfy://ntfy.sh/topic") == "ntfy://…/topic"
    assert _redact("plain") == "plain"
