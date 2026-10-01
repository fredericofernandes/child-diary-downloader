"""The server drops ~1 entry at each page boundary; two passes with different
page sizes must recover it, and known-ID early stopping must stay correct."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest
import responses

from childdiary_downloader import api


def make_entries(n: int) -> list[dict[str, Any]]:
    return [
        {"Id": f"id-{i:04d}", "CreatedOn": f"2026-01-{(i % 28) + 1:02d}T10:00:00Z"}
        for i in range(n)
    ]


class FlakyServer:
    """Offset pagination that loses the first entry of every page after the first."""

    def __init__(self, entries: list[dict[str, Any]], drop_at_boundaries: bool = True) -> None:
        self.entries = entries
        self.drop = drop_at_boundaries
        self.requests: list[tuple[int, int]] = []

    def __call__(self, request: Any) -> tuple[int, dict[str, str], str]:
        qs = parse_qs(urlparse(request.url).query)
        count, page = int(qs["count"][0]), int(qs["page"][0])
        self.requests.append((count, page))
        start = page * count
        chunk = self.entries[start : start + count]
        if self.drop and page > 0 and chunk:
            chunk = chunk[1:]
        return 200, {}, json.dumps({"Entries": chunk})


@pytest.fixture
def mocked() -> Any:
    with responses.RequestsMock() as rsps:
        yield rsps


def test_union_of_two_passes_recovers_dropped_entries(mocked: Any) -> None:
    entries = make_entries(250)
    server = FlakyServer(entries)
    mocked.add_callback(responses.GET, api.ENTRIES_URL, callback=server)
    session = api._make_retry_session()
    got = api.fetch_entries(session)
    assert {e["Id"] for e in got} == {e["Id"] for e in entries}
    # A single pass of 100 would have lost id-0100 and id-0200.
    assert (100, 1) in server.requests and (90, 1) in server.requests


def test_single_pass_really_loses_entries(mocked: Any) -> None:
    entries = make_entries(250)
    mocked.add_callback(responses.GET, api.ENTRIES_URL, callback=FlakyServer(entries))
    got = api._fetch_pass(api._make_retry_session(), 100, None)
    assert len(got) == 248


def test_early_stop_after_two_known_pages(mocked: Any) -> None:
    entries = make_entries(1000)
    server = FlakyServer(entries, drop_at_boundaries=False)
    mocked.add_callback(responses.GET, api.ENTRIES_URL, callback=server)
    known = {e["Id"] for e in entries[5:]}  # only the 5 newest are new
    got = api.fetch_entries(api._make_retry_session(), known)
    assert {e["Id"] for e in got} >= {e["Id"] for e in entries[:5]}
    pages_100 = [p for c, p in server.requests if c == 100]
    assert pages_100 == [0, 1, 2]  # page 0 has new ones, then two fully-known pages


def test_known_streak_resets_on_new_entry(mocked: Any) -> None:
    entries = make_entries(500)
    server = FlakyServer(entries, drop_at_boundaries=False)
    mocked.add_callback(responses.GET, api.ENTRIES_URL, callback=server)
    known = {e["Id"] for e in entries} - {"id-0150"}  # one old entry still unknown
    got = api.fetch_entries(api._make_retry_session(), known)
    assert "id-0150" in {e["Id"] for e in got}


def test_sends_user_agent(mocked: Any) -> None:
    mocked.add(responses.GET, api.ENTRIES_URL, json={"Entries": []})
    api.fetch_entries(api._make_retry_session())
    assert mocked.calls[0].request.headers["user-agent"].startswith("child-diary-downloader/")
    assert "github.com" in mocked.calls[0].request.headers["user-agent"]


def test_login_sends_json_with_boolean_remember_me(mocked: Any) -> None:
    mocked.add(responses.POST, api.LOGIN_URL, json={}, status=200)
    api.login({"Username": "u", "Password": "p", "RememberMe": "true"})
    assert json.loads(mocked.calls[0].request.body) == {
        "Username": "u",
        "Password": "p",
        "RememberMe": True,
    }


def test_throttle_spaces_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps: list[float] = []
    clock = {"t": 100.0}
    monkeypatch.setattr(api.time, "monotonic", lambda: clock["t"])
    monkeypatch.setattr(api.time, "sleep", lambda s: sleeps.append(s))
    throttle = api.Throttle(0.5)
    throttle.wait()  # first call never sleeps
    clock["t"] += 0.1
    throttle.wait()
    assert sleeps == [pytest.approx(0.4)]
