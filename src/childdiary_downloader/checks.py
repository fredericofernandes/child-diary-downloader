"""`childdiary check`: verify a configuration end to end without archiving."""

from __future__ import annotations

import os
import shutil
from collections.abc import Callable
from dataclasses import dataclass

from childdiary_downloader.api import fetch_entries, login
from childdiary_downloader.config import Config
from childdiary_downloader.notify import Telegram


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    detail: str


def run_checks(config: Config, *, send_test_message: bool = False) -> list[CheckResult]:
    results: list[CheckResult] = []

    def check(name: str, fn: Callable[[], str]) -> None:
        try:
            results.append(CheckResult(name, True, fn()))
        except Exception as e:  # report, never crash
            results.append(CheckResult(name, False, str(e)))

    def archive_writable() -> str:
        config.archive_dir.mkdir(parents=True, exist_ok=True)
        if not os.access(config.archive_dir, os.W_OK):
            raise PermissionError(f"{config.archive_dir} is not writable")
        return str(config.archive_dir)

    check("archive folder", archive_writable)
    check(
        "exiftool",
        lambda: (
            shutil.which("exiftool")
            or (_ for _ in ()).throw(
                FileNotFoundError("not found: EXIF dates will not be written (optional)")
            )
        ),
    )

    for account in config.accounts:

        def account_login(account=account) -> str:  # type: ignore[no-untyped-def]
            session = login(account.auth_payload())
            entries = fetch_entries(session)
            known = sum(
                1
                for e in entries
                for i in e.get("For", []) or []
                if i.get("Type") == "Child" and i.get("Id") in account.children
            )
            if entries and not known:
                raise LookupError(
                    f"logged in, {len(entries)} entries, but none mention the configured children "
                    "(check the IDs with `childdiary list-groups`)"
                )
            return f"logged in, {len(entries)} entries, {known} mention your children"

        check(f"account '{account.name}'", account_login)

    if config.telegram:
        tg = config.telegram

        def telegram_check() -> str:
            if send_test_message:
                Telegram(tg.token, tg.chat_id).send_message(
                    "child-diary-downloader: test message ✅"
                )
                return "test message sent"
            return "configured (use --send-test to send a message)"

        check("telegram", telegram_check)
    else:
        results.append(CheckResult("telegram", True, "not configured: archive only"))
    return results
