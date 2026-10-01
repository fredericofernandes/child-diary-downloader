import io
import json
from typing import Any
from urllib.parse import unquote_plus

import pytest
import responses

from childdiary_downloader.notify.telegram import MAX_CAPTION, MAX_TEXT, Telegram

BOT = "https://api.telegram.org/bottok/"


@pytest.fixture
def rsps() -> Any:
    with responses.RequestsMock() as r:
        yield r


def test_send_message_truncates(rsps: Any) -> None:
    rsps.add(responses.POST, BOT + "sendMessage", json={"ok": True})
    Telegram("tok", "42").send_message("x" * (MAX_TEXT + 10))
    body = unquote_plus(rsps.calls[0].request.body)
    assert body.startswith("chat_id=42&text=")
    assert body.endswith("[…]")
    assert len(body.split("text=", 1)[1]) == MAX_TEXT


def test_send_photo_with_caption_limit(rsps: Any) -> None:
    rsps.add(responses.POST, BOT + "sendPhoto", json={"ok": True})
    Telegram("tok", "42").send_photo(io.BytesIO(b"img"), caption="c" * (MAX_CAPTION + 5))
    body = rsps.calls[0].request.body
    assert b'name="photo"' in body
    assert b"c" * MAX_CAPTION in body and b"c" * (MAX_CAPTION + 1) not in body


def test_send_media_group_payload(rsps: Any) -> None:
    rsps.add(responses.POST, BOT + "sendMediaGroup", json={"ok": True})
    items = [(io.BytesIO(b"a"), ".jpg", "first"), (io.BytesIO(b"b"), ".mp4", "")]
    Telegram("tok", "42").send_media_group(items)
    body = rsps.calls[0].request.body.decode("utf-8", "ignore")
    media = json.loads(body.split('name="media"')[1].split("\r\n\r\n")[1].split("\r\n")[0])
    assert media == [
        {"type": "photo", "media": "attach://file0", "caption": "first"},
        {"type": "video", "media": "attach://file1"},
    ]
    assert 'name="file0"' in body and 'name="file1"' in body


def test_http_errors_raise(rsps: Any) -> None:
    rsps.add(responses.POST, BOT + "sendDocument", status=400, json={"ok": False})
    with pytest.raises(Exception, match="400"):
        Telegram("tok", "42").send_document(io.BytesIO(b"pdf"))


def test_send_video(rsps: Any) -> None:
    rsps.add(responses.POST, BOT + "sendVideo", json={"ok": True})
    Telegram("tok", "42").send_video(io.BytesIO(b"v"), caption="clip")
    assert b'name="video"' in rsps.calls[0].request.body
