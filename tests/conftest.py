from __future__ import annotations

from pathlib import Path
from typing import IO, Any

import pytest

from childdiary_downloader import handlers
from childdiary_downloader.api import set_request_delay
from childdiary_downloader.config import Config, parse_config
from childdiary_downloader.handlers import ArchiveContext
from childdiary_downloader.notify import MediaItem
from tests.factories import CHILDREN

FAKE_BYTES = {
    ".jpg": b"\xff\xd8\xff\xe0JFIF-fake-photo",
    ".png": b"\x89PNG-fake-photo",
    ".mp4": b"\x00\x00\x00\x18ftypmp42-fake-video",
    ".pdf": b"%PDF-1.4 fake document",
}


class RecordingNotifier:
    """Records every call; file handles are read so sizes can be asserted."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []

    @property
    def messages(self) -> list[str]:
        return [payload for kind, payload in self.calls if kind == "message"]

    def send_message(self, text: str) -> None:
        self.calls.append(("message", text))

    def send_photo(self, fh: IO[bytes], caption: str = "") -> None:
        self.calls.append(("photo", (fh.name, caption)))

    def send_video(self, fh: IO[bytes], caption: str = "") -> None:
        self.calls.append(("video", (fh.name, caption)))

    def send_document(self, fh: IO[bytes], caption: str = "") -> None:
        self.calls.append(("document", (fh.name, caption)))

    def send_media_group(self, items: list[MediaItem]) -> None:
        self.calls.append(("album", [(fh.name, ext, cap) for fh, ext, cap in items]))


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
    return parse_config(data)


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    """Replace media downloads and exiftool; count downloads per URL."""
    downloads: dict[str, int] = {}
    set_request_delay(0)

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
