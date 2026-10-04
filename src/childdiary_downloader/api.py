"""Minimal client for the unofficial app.childdiary.net API (the one the web app uses).

Good-neighbour policy: an honest User-Agent, a configurable pause between
requests, automatic retries with backoff, and respect for Retry-After.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from childdiary_downloader import __version__

log = logging.getLogger(__name__)

BASE_URL = "https://app.childdiary.net"
LOGIN_URL = f"{BASE_URL}/api/Account/login"
ENTRIES_URL = f"{BASE_URL}/api/Entries"
PROJECT_URL = "https://github.com/fredericofernandes/child-diary-downloader"
USER_AGENT = f"child-diary-downloader/{__version__} (+{PROJECT_URL})"
HEADERS = {"accept": "application/json, text/plain, */*", "user-agent": USER_AGENT}
MAX_PAGES = 20000
MAX_RETRIES = 3
RETRY_BACKOFF = 2  # seconds
REQUEST_TIMEOUT = 60
# Stop paginating after this many consecutive pages with no new entries.
# 2 (not 1) so a previously-failed entry sitting just below a fully-known
# page still gets picked up.
KNOWN_PAGES_TO_STOP = 2
# Page sizes for the two passes (see fetch_entries).
PAGE_SIZES = (100, 90)

Entry = dict[str, Any]


class Throttle:
    """Sleeps so that consecutive requests are at least ``delay`` seconds apart."""

    def __init__(self, delay: float) -> None:
        self.delay = delay
        self._last = 0.0

    def wait(self) -> None:
        if self.delay <= 0:
            return
        now = time.monotonic()
        remaining = self._last + self.delay - now
        if remaining > 0:
            time.sleep(remaining)
        self._last = time.monotonic()


_throttle = Throttle(0.0)


def set_request_delay(seconds: float) -> None:
    """Global pause between requests to childdiary.net (API and media CDN)."""
    _throttle.delay = seconds


def _make_retry_session() -> requests.Session:
    """Session with automatic retries on transient errors (honours Retry-After)."""
    session = requests.Session()
    session.headers.update(HEADERS)
    retry = Retry(
        total=MAX_RETRIES,
        backoff_factor=RETRY_BACKOFF,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"],
        respect_retry_after_header=True,
    )
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


# Shared session for media downloads (signed URLs, no auth cookies needed).
_download_session = _make_retry_session()


def download_file(url: str) -> bytes:
    """Download a URL through the retrying session. Returns the raw bytes."""
    _throttle.wait()
    resp = _download_session.get(url, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return resp.content


def login(auth_data: dict[str, Any]) -> requests.Session:
    """Authenticate and return a session carrying the auth cookie."""
    # The API wants RememberMe as a boolean, not a string.
    if isinstance(auth_data.get("RememberMe"), str):
        auth_data = {**auth_data, "RememberMe": auth_data["RememberMe"].lower() == "true"}
    session = _make_retry_session()
    _throttle.wait()
    resp = session.post(LOGIN_URL, json=auth_data, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return session


def fetch_entries(
    session: requests.Session,
    known_ids: set[str] | None = None,
    max_pages: int = MAX_PAGES,
) -> list[Entry]:
    """Fetch entries, newest first, deduplicated by Id.

    The server's offset pagination drops about one entry at each page
    boundary (verified: page0+page1 of 100 vs. a single page of 200 each miss
    an entry the other returns). Two passes with different page sizes put the
    boundaries in different places, so the union recovers the dropped entries.
    """
    merged: dict[str, Entry] = {}
    for count in PAGE_SIZES:
        for entry in _fetch_pass(session, count, known_ids, max_pages):
            eid = str(entry.get("Id"))
            if eid not in merged:
                merged[eid] = entry
    return list(merged.values())


def _fetch_pass(
    session: requests.Session, count: int, known_ids: set[str] | None, max_pages: int = MAX_PAGES
) -> list[Entry]:
    """One pagination sweep. Stops at an empty page or, when ``known_ids`` is
    given, after KNOWN_PAGES_TO_STOP consecutive pages of already-processed
    entries, so incremental runs stay fast."""
    entries: list[Entry] = []
    known_ids = known_ids or set()
    known_streak = 0
    for page in range(max_pages):
        params: dict[str, str | int] = {"count": count, "page": page, "type": "All"}
        _throttle.wait()
        resp = session.get(ENTRIES_URL, params=params, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        page_entries = resp.json().get("Entries", [])
        if not page_entries:
            break
        entries.extend(page_entries)

        if known_ids:
            if all(e.get("Id") in known_ids for e in page_entries):
                known_streak += 1
                if known_streak >= KNOWN_PAGES_TO_STOP:
                    log.info("Stopping pagination at page %d (all entries already known).", page)
                    break
            else:
                known_streak = 0
    else:
        if max_pages == MAX_PAGES:
            log.warning("Reached MAX_PAGES (%d): some entries may have been skipped.", MAX_PAGES)
    return entries
