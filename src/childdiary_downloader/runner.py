"""One run: login, pagination, routing and per-entry processing."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from childdiary_downloader.api import fetch_entries, login
from childdiary_downloader.config import Account, Config
from childdiary_downloader.handlers import (
    HANDLERS,
    ArchiveContext,
    get_entry_info,
    parse_dt,
    process_unknown,
)
from childdiary_downloader.notify import Notifier, NullNotifier
from childdiary_downloader.state import State

log = logging.getLogger(__name__)


def run_discover(accounts: list[Account], output: Path) -> None:
    """Save one example entry of each type, to study the API."""
    by_type: dict[Any, Any] = {}
    for account in accounts:
        log.info("[%s] Fetching all entries for discovery…", account.name)
        session = login(account.auth_payload())
        entries = fetch_entries(session)
        log.info("[%s] Total entries: %d", account.name, len(entries))
        for entry in entries:
            by_type.setdefault(entry.get("Type"), entry)

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as f:
        json.dump(by_type, f, indent=2, ensure_ascii=False)
    log.info("Discovery complete: %d type(s): %s", len(by_type), sorted(by_type.keys()))
    log.info("Dump written to %s", output)


def list_groups(
    accounts: list[Account], unnamed: str = "?"
) -> dict[str, dict[str, dict[str, str]]]:
    """Per account: {"groups": {id: name}, "children": {id: name}, "total": {...}}."""
    result: dict[str, dict[str, dict[str, str]]] = {}
    for account in accounts:
        session = login(account.auth_payload())
        entries = fetch_entries(session)
        groups: dict[str, str] = {}
        children: dict[str, str] = {}
        for entry in entries:
            for item in entry.get("For", []):
                if item.get("Type") == "Group":
                    groups[item["Id"]] = item.get("Description", unnamed)
                elif item.get("Type") == "Child":
                    children[item["Id"]] = item.get("Description", unnamed)
        result[account.name] = {
            "groups": groups,
            "children": children,
            "total": {"entries": str(len(entries))},
        }
    return result


def run_account(
    account: Account,
    config: Config,
    state: State,
    state_file: Path,
    notifier: Notifier,
    *,
    dry_run: bool = False,
) -> tuple[int, int]:
    """Process the new entries of one account. Returns (processed, failed).

    With ``dry_run`` nothing is downloaded, written or sent: the log shows what
    would happen and the state is left untouched.
    """
    name = account.name
    children = account.children
    ctx = ArchiveContext(
        root=config.archive_dir,
        strings=config.strings,
        documents=config.documents,
        timezone=config.tzinfo,
    )
    known_ids = set(state.processed_ids)
    max_age = timedelta(days=config.telegram.max_age_days if config.telegram else 0)

    log.info("[%s] Logging in…", name)
    session = login(account.auth_payload())

    # A previously failed entry may sit deep in history, below the pagination
    # early stop: while any failure is pending, fetch everything (known_ids
    # still keeps already-processed entries out of the work list).
    fetch_known = known_ids
    if state.failed_ids:
        log.info("[%s] %d failed entr(ies) pending: full fetch.", name, len(state.failed_ids))
        fetch_known = set()

    log.info("[%s] Fetching entries…", name)
    entries = fetch_entries(session, fetch_known)
    new_entries = [e for e in entries if e.get("Id") not in known_ids]
    log.info("[%s] Fetched %d entries, %d new.", name, len(entries), len(new_entries))

    # Oldest first, so notifications and state updates follow chronology.
    new_entries.sort(key=lambda e: e.get("CreatedOn", ""))

    # GroupId -> child name, learned from the children's own entries.
    group_to_child: dict[str, str] = {}
    for entry in entries:
        for item in entry.get("For", []):
            if item.get("Type") == "Child" and item.get("Id") in children:
                gid = item.get("GroupId")
                if gid:
                    group_to_child[gid] = children[item["Id"]]

    processed = 0
    failed = 0
    silent = NullNotifier()
    for entry in new_entries:
        names, prefix, folders = get_entry_info(
            entry, children, group_to_child, config.routing, config.strings
        )
        entry_type = entry.get("Type")
        created_on = entry.get("CreatedOn", "")

        # PDFs get a copy in <Child>/<Documents>/ only when the entry is addressed
        # exclusively to our children (reports, adapted menus…); class-wide
        # circulars list every child in the room and stay in the date folders.
        for_items = entry.get("For", [])
        all_ours = bool(for_items) and all(
            i.get("Type") == "Child" and i.get("Id") in children for i in for_items
        )
        doc_folders = list(dict.fromkeys(names)) if all_ours else []

        # Old entries are archived silently: they only surface when the school
        # backdates something or the flaky pagination finally yields one.
        # API timestamps are the school's local time, so compare in that zone.
        entry_notifier: Notifier = notifier
        try:
            now_local = datetime.now(config.tzinfo).replace(tzinfo=None)
            if max_age and now_local - parse_dt(created_on) > max_age:
                entry_notifier = silent
        except ValueError:
            pass
        log.info(
            "[%s] %s type=%s folders=%s prefix=%r date=%s%s",
            name,
            "Would process" if dry_run else "Processing",
            entry_type,
            folders,
            prefix.strip(),
            created_on[:10],
            " (old: archive only)" if entry_notifier is silent else "",
        )
        if dry_run:
            processed += 1
            continue

        try:
            handler = (
                HANDLERS.get(entry_type, process_unknown)
                if isinstance(entry_type, int)
                else process_unknown
            )
            handler(ctx, entry, entry_notifier, prefix, folders, doc_folders)
        except Exception as e:
            log.error("[%s] Failed entry %s (type=%s): %s", name, entry.get("Id"), entry_type, e)
            if entry.get("Id"):
                state.mark_failed(entry["Id"])
                state.save(state_file)
            failed += 1
            continue

        state.mark_processed(entry["Id"], created_on)
        state.save(state_file)
        processed += 1

    log.info(
        "[%s] Done. %d %s, %d failed.",
        name,
        processed,
        "would be processed" if dry_run else "processed",
        failed,
    )
    return processed, failed
