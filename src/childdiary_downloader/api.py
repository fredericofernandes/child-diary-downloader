"""Cliente mínimo da API não oficial de app.childdiary.net (a mesma da web app)."""

from __future__ import annotations

import logging
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

log = logging.getLogger(__name__)

LOGIN_URL = "https://app.childdiary.net/api/Account/login"
ENTRIES_URL = "https://app.childdiary.net/api/Entries"
HEADERS = {"accept": "application/json, text/plain, */*"}
MAX_PAGES = 20000
MAX_RETRIES = 3
RETRY_BACKOFF = 2  # segundos
REQUEST_TIMEOUT = 60
# Pára a paginação após este número de páginas seguidas sem entradas novas.
# 2 (e não 1) para que uma entrada que falhou anteriormente, logo abaixo de
# uma página totalmente conhecida, ainda seja apanhada.
KNOWN_PAGES_TO_STOP = 2

Entry = dict[str, Any]


def _make_retry_session() -> requests.Session:
    """Sessão com retries automáticos em erros transitórios."""
    session = requests.Session()
    retry = Retry(
        total=MAX_RETRIES,
        backoff_factor=RETRY_BACKOFF,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"],
    )
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


# Sessão partilhada para downloads de media (URLs assinados, sem cookies de auth).
_download_session = _make_retry_session()


def download_file(url: str) -> bytes:
    """Descarrega um URL via sessão com retries. Devolve os bytes."""
    resp = _download_session.get(url, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return resp.content


def login(auth_data: dict[str, Any]) -> requests.Session:
    """Autentica na API e devolve uma sessão com o cookie de sessão."""
    # A API exige RememberMe como booleano, não como string.
    if isinstance(auth_data.get("RememberMe"), str):
        auth_data = {**auth_data, "RememberMe": auth_data["RememberMe"].lower() == "true"}
    session = _make_retry_session()
    resp = session.post(LOGIN_URL, json=auth_data, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return session


def fetch_entries(session: requests.Session, known_ids: set[str] | None = None) -> list[Entry]:
    """Vai buscar as entradas, mais recentes primeiro, sem duplicados por Id.

    A paginação por offset do servidor perde cerca de uma entrada em cada
    fronteira de página (verificado: page0+page1 de 100 vs. uma página de 200
    perdem cada uma entrada que a outra devolve). Duas passagens com tamanhos
    de página diferentes põem as fronteiras em sítios diferentes, e a união
    recupera as entradas perdidas.
    """
    merged: dict[str, Entry] = {}
    for count in (100, 90):
        for entry in _fetch_pass(session, count, known_ids):
            eid = str(entry.get("Id"))
            if eid not in merged:
                merged[eid] = entry
    return list(merged.values())


def _fetch_pass(session: requests.Session, count: int, known_ids: set[str] | None) -> list[Entry]:
    """Uma passagem de paginação. Pára numa página vazia ou, quando
    ``known_ids`` é dado, após KNOWN_PAGES_TO_STOP páginas seguidas só com
    entradas já processadas, para as execuções incrementais serem rápidas.
    """
    entries: list[Entry] = []
    known_ids = known_ids or set()
    known_streak = 0
    for page in range(MAX_PAGES):
        params: dict[str, str | int] = {"count": count, "page": page, "type": "All"}
        resp = session.get(ENTRIES_URL, params=params, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        page_entries = resp.json().get("Entries", [])
        if not page_entries:
            break
        entries.extend(page_entries)

        if known_ids:
            if all(e.get("Id") in known_ids for e in page_entries):
                known_streak += 1
                if known_streak >= KNOWN_PAGES_TO_STOP:
                    log.info("A parar a paginação na página %d (tudo já conhecido).", page)
                    break
            else:
                known_streak = 0
    else:
        log.warning("Atingido MAX_PAGES (%d): podem ter ficado entradas por ler.", MAX_PAGES)
    return entries
