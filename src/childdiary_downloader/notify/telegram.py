"""Telegram Bot API notifier: messages, photos, videos, documents and albums."""

from __future__ import annotations

import json
import logging
from typing import IO, Any

import requests

from childdiary_downloader.notify.base import MediaItem

log = logging.getLogger(__name__)

MAX_TEXT = 4096
MAX_CAPTION = 1024
UPLOAD_TIMEOUT = 300


class Telegram:
    def __init__(self, token: str, chat_id: str) -> None:
        self.chat_id = chat_id
        self.url = f"https://api.telegram.org/bot{token}/"

    def _post(self, method: str, data: dict[str, Any], files: dict[str, Any] | None = None) -> None:
        resp = requests.post(self.url + method, data=data, files=files, timeout=UPLOAD_TIMEOUT)
        resp.raise_for_status()

    def _send_file(self, method: str, field: str, fh: IO[bytes], caption: str) -> None:
        data: dict[str, Any] = {"chat_id": self.chat_id}
        if caption:
            data["caption"] = caption[:MAX_CAPTION]
        self._post(method, data, files={field: fh})

    def send_message(self, text: str) -> None:
        if len(text) > MAX_TEXT:
            text = text[: MAX_TEXT - 3] + "[…]"
        self._post("sendMessage", {"chat_id": self.chat_id, "text": text})

    def send_photo(self, fh: IO[bytes], caption: str = "") -> None:
        self._send_file("sendPhoto", "photo", fh, caption)

    def send_video(self, fh: IO[bytes], caption: str = "") -> None:
        self._send_file("sendVideo", "video", fh, caption)

    def send_document(self, fh: IO[bytes], caption: str = "") -> None:
        self._send_file("sendDocument", "document", fh, caption)

    def send_media_group(self, items: list[MediaItem]) -> None:
        """Send up to 10 photos/videos as one album. Only the first caption shows."""
        media_json = []
        files: dict[str, IO[bytes]] = {}
        for i, (fh, ext, cap) in enumerate(items):
            key = f"file{i}"
            media_type = "video" if ext == ".mp4" else "photo"
            item: dict[str, str] = {"type": media_type, "media": f"attach://{key}"}
            if cap:
                item["caption"] = cap[:MAX_CAPTION]
            media_json.append(item)
            files[key] = fh
        data = {"chat_id": self.chat_id, "media": json.dumps(media_json)}
        self._post("sendMediaGroup", data, files)
