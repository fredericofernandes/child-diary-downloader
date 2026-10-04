from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from childdiary_downloader import handlers
from childdiary_downloader.api import set_request_delay
from childdiary_downloader.config import Config, parse_config
from childdiary_downloader.handlers import ArchiveContext
from tests.factories import CHILDREN

FAKE_BYTES = {
    ".jpg": b"\xff\xd8\xff\xe0JFIF-fake-photo",
    ".png": b"\x89PNG-fake-photo",
    ".mp4": b"\x00\x00\x00\x18ftypmp42-fake-video",
    ".pdf": b"%PDF-1.4 fake document",
}


class RecordingNotifier:
    """Records every call as ("message", text) or ("files", ([names], text))."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []

    @property
    def messages(self) -> list[str]:
        return [payload for kind, payload in self.calls if kind == "message"]

    @property
    def files(self) -> list[tuple[list[str], str]]:
        return [payload for kind, payload in self.calls if kind == "files"]

    def send_message(self, text: str) -> None:
        self.calls.append(("message", text))

    def send_files(self, paths: list[Path], text: str = "") -> None:
        self.calls.append(("files", ([p.name for p in paths], text)))

    def flush(self) -> None:
        self.calls.append(("flush", None))


def make_config(**overrides: Any) -> Config:
    data: dict[str, Any] = {
        "archive_dir": "/nonexistent",
        "accounts": [
            {
                "name": "Creche Exemplo",
                "username": "familia@example.test",
                "password": "secret",
                "children": CHILDREN,
            }
        ],
        "routing": {
            "groups": {
                "Sala Girassóis": ["Maria"],
                "Sala Papoilas": ["Tomás"],
                "Música": ["Maria", "Tomás"],
            },
            "instances": {"Creche Exemplo": ["Maria", "Tomás"]},
            "child_since": {"Tomás": "2025-09-01"},
        },
    }
    data.update(overrides)
    # Fixtures carry fixed dates; unless a test sets the cut-off (directly or
    # through the legacy telegram section) nothing is treated as old.
    legacy = overrides.get("telegram") or {}
    if "max_age_days" not in data and "max_age_days" not in legacy:
        data["max_age_days"] = 0
    return parse_config(data)


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    """Replace media downloads and exiftool; count downloads per URL."""
    downloads: dict[str, int] = {}
    set_request_delay(0)
    monkeypatch.delenv("CDD_ARCHIVE_DIR", raising=False)

    def fake_download(url: str) -> bytes:
        downloads[url] = downloads.get(url, 0) + 1
        ext = "." + url.split("?")[0].rsplit(".", 1)[-1]
        return FAKE_BYTES.get(ext, b"fake")

    monkeypatch.setattr(handlers, "download_file", fake_download)
    monkeypatch.setattr(handlers.shutil, "which", lambda name: None)  # no exiftool in tests
    return downloads


@pytest.fixture
def config(tmp_path: Path) -> Config:
    return make_config(archive_dir=str(tmp_path / "archive"))


@pytest.fixture
def ctx(config: Config) -> ArchiveContext:
    return ArchiveContext(
        root=config.archive_dir, strings=config.strings, documents=config.documents
    )


@pytest.fixture
def notifier() -> RecordingNotifier:
    return RecordingNotifier()
