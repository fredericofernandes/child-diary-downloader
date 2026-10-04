from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from childdiary_downloader.config import ConfigError, NotifierConfig
from childdiary_downloader.i18n import get_strings
from childdiary_downloader.notify import (
    AppriseNotifier,
    CompositeNotifier,
    DigestNotifier,
    NullNotifier,
    build_notifier,
)
from childdiary_downloader.notify.digest import MAX_CHUNK
from tests.conftest import RecordingNotifier, make_config

PT = get_strings("pt")
NOW = datetime(2026, 3, 10, 19, 0)


def test_digest_collects_and_sends_once() -> None:
    inner = RecordingNotifier()
    digest = DigestNotifier(inner, PT, now=NOW)
    digest.send_message("[Maria] Rotina Diária:\nAlmoço: sopa")
    digest.send_files([Path("/a/1.jpg"), Path("/a/2.jpg")], "legenda")
    digest.send_message("[Sala Girassóis] Dia da Primavera")
    assert inner.calls == []  # nothing yet
    digest.flush()
    assert inner.messages == [
        "📒 Resumo ChildDiary — 10/03/2026\n\n— — —\n\n"
        "[Maria] Rotina Diária:\nAlmoço: sopa\n\n— — —\n\n"
        "[Sala Girassóis] Dia da Primavera"
    ]
    assert inner.files == [(["1.jpg", "2.jpg"], "10/03/2026 — 2 fotos, vídeos e documentos")]
    digest.flush()  # empty now: no second delivery
    assert len(inner.calls) == 2


def test_digest_splits_long_runs_at_entry_boundaries() -> None:
    inner = RecordingNotifier()
    digest = DigestNotifier(inner, PT, now=NOW)
    for i in range(6):
        digest.send_message(f"[{i}] " + "x" * 1000)
    digest.flush()
    assert len(inner.messages) == 2
    assert all(len(m) <= MAX_CHUNK for m in inner.messages)
    assert all(m.startswith("📒 Resumo ChildDiary") for m in inner.messages)
    assert "[0]" in inner.messages[0] and "[5]" in inner.messages[1]


def test_digest_clears_buffer_even_when_delivery_fails() -> None:
    class Broken(RecordingNotifier):
        def send_message(self, text: str) -> None:
            raise RuntimeError("down")

    digest = DigestNotifier(Broken(), PT, now=NOW)
    digest.send_message("x")
    with pytest.raises(RuntimeError):
        digest.flush()
    assert digest._texts == []


def test_build_notifier_modes() -> None:
    assert isinstance(build_notifier([], PT), NullNotifier)
    only_immediate = build_notifier([NotifierConfig(url="ntfy://ntfy.sh/a")], PT)
    assert isinstance(only_immediate, AppriseNotifier)
    only_digest = build_notifier([NotifierConfig(url="ntfy://ntfy.sh/a", mode="digest")], PT)
    assert isinstance(only_digest, DigestNotifier)
    both = build_notifier(
        [
            NotifierConfig(url="ntfy://ntfy.sh/a"),
            NotifierConfig(url="mailto://u:p@example.com?to=x@y.z", mode="digest", media=False),
        ],
        PT,
    )
    assert isinstance(both, CompositeNotifier)
    assert (
        repr(both)
        == "CompositeNotifier(AppriseNotifier(ntfy://…/a), DigestNotifier(AppriseNotifier(mailto://…)))"
    )


def test_composite_fans_out_and_flushes() -> None:
    a, b = RecordingNotifier(), RecordingNotifier()
    digest = DigestNotifier(b, PT, now=NOW)
    composite = CompositeNotifier([a, digest])
    composite.send_message("olá")
    composite.send_files([Path("/x.jpg")], "c")
    assert a.calls == [("message", "olá"), ("files", (["x.jpg"], "c"))] and b.calls == []
    composite.flush()
    assert a.calls[-1] == ("flush", None)
    assert [k for k, _ in b.calls] == ["message", "files"]


def test_config_mode_validation() -> None:
    cfg = make_config(notifiers=[{"url": "ntfy://ntfy.sh/a", "mode": "Digest"}])
    assert cfg.notifiers[0].mode == "digest"
    with pytest.raises(ConfigError, match="mode must be one of"):
        make_config(notifiers=[{"url": "ntfy://ntfy.sh/a", "mode": "weekly"}])
