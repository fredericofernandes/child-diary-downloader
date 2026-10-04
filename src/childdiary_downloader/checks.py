"""`childdiary check`: verify a configuration end to end without archiving."""

from __future__ import annotations

import os
import shutil
from collections.abc import Callable
from dataclasses import dataclass

from childdiary_downloader.api import fetch_entries, login
from childdiary_downloader.config import Config
from childdiary_downloader.notify import AppriseNotifier

CHECK_PAGES = 2


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
            # The newest pages are enough to prove the login and the children IDs.
            entries = fetch_entries(session, max_pages=CHECK_PAGES)
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
            return f"logged in, {len(entries)} recent entries, {known} mention your children"

        check(f"account '{account.name}'", account_login)

    if config.notifiers:
        for n in config.notifiers:

            def notifier_check(n=n) -> str:  # type: ignore[no-untyped-def]
                notifier = AppriseNotifier([(n.url, n.media)])
                if send_test_message:
                    notifier.send_message("child-diary-downloader: test message ✅")
                    return "test message sent"
                return "URL accepted (use --send-test to send a message)"

            check(f"notifier '{n.name}'", notifier_check)
    else:
        results.append(CheckResult("notifiers", True, "none configured: archive only"))
    return results
