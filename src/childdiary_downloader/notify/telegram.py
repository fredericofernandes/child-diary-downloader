"""Envio de mensagens, fotos, vídeos e documentos via Bot API do Telegram."""

from __future__ import annotations

import json
import logging
from typing import IO, Any

import requests

log = logging.getLogger(__name__)

MAX_TEXT = 4096
MAX_CAPTION = 1024
UPLOAD_TIMEOUT = 300

MediaItem = tuple[IO[bytes], str, str]  # (ficheiro aberto, extensão, legenda)


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

    def send_document(self, fh: IO[bytes], caption: str = "") -> None:
        self._send_file("sendDocument", "document", fh, caption)

    def send_photo(self, fh: IO[bytes], caption: str = "") -> None:
        self._send_file("sendPhoto", "photo", fh, caption)

    def send_video(self, fh: IO[bytes], caption: str = "") -> None:
        self._send_file("sendVideo", "video", fh, caption)

    def send_message(self, text: str) -> None:
        if len(text) > MAX_TEXT:
            text = text[: MAX_TEXT - 3] + "[…]"
        self._post("sendMessage", {"chat_id": self.chat_id, "text": text})

    def send_media_group(self, items: list[MediaItem]) -> None:
        """Envia até 10 fotos/vídeos como álbum. A legenda só conta no primeiro."""
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
        self._post(
            "sendMediaGroup", {"chat_id": self.chat_id, "media": json.dumps(media_json)}, files
        )


class NullTelegram:
    """Substituto do Telegram que só regista no log (modo --no-telegram)."""

    def send_document(self, fh: IO[bytes], caption: str = "") -> None:
        log.info("NullTelegram.send_document caption=%r", (caption or "")[:80])

    def send_photo(self, fh: IO[bytes], caption: str = "") -> None:
        log.info("NullTelegram.send_photo caption=%r", (caption or "")[:80])

    def send_video(self, fh: IO[bytes], caption: str = "") -> None:
        log.info("NullTelegram.send_video caption=%r", (caption or "")[:80])

    def send_message(self, text: str) -> None:
        log.info("NullTelegram.send_message: %s", text[:120])

    def send_media_group(self, items: list[MediaItem]) -> None:
        log.info("NullTelegram.send_media_group %d items", len(items))
