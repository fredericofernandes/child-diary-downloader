"""Command line: ``childdiary run | discover | list-groups``."""

from __future__ import annotations

import fcntl
import logging
import os
import re
import sys
from dataclasses import replace
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from childdiary_downloader import __version__
from childdiary_downloader.api import set_request_delay
from childdiary_downloader.checks import run_checks
from childdiary_downloader.config import DEFAULT_ARCHIVE_DIR, Config, ConfigError, load_config
from childdiary_downloader.logging_setup import setup_logging
from childdiary_downloader.notify import Notifier, NullNotifier, build_notifier
from childdiary_downloader.paths import RuntimePaths, default_config_file, default_data_dir
from childdiary_downloader.runner import list_groups, run_account, run_discover
from childdiary_downloader.scheduler import (
    DEFAULT_SCHEDULE,
    DaemonFiles,
    check_health,
    run_daemon,
    validate_schedule,
)
from childdiary_downloader.setup_wizard import run_wizard
from childdiary_downloader.state import State

log = logging.getLogger(__name__)
console = Console()


class App:
    """Context shared by the subcommands."""

    def __init__(self, config_file: Path, data_dir: Path, verbose: bool) -> None:
        self.config_file = config_file
        self.paths = RuntimePaths(data_dir)
        self.verbose = verbose
        self._config: Config | None = None

    @property
    def config(self) -> Config:
        if self._config is None:
            try:
                self._config = load_config(self.config_file)
            except ConfigError as e:
                raise click.ClickException(str(e)) from e
            set_request_delay(self._config.network.request_delay_seconds)
        return self._config


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, prog_name="childdiary")
@click.option(
    "--config",
    "config_file",
    type=click.Path(path_type=Path),
    default=None,
    help="config.yaml to use (default: the OS config folder, or $CDD_CONFIG).",
)
@click.option(
    "--data-dir",
    type=click.Path(path_type=Path),
    default=None,
    help="Folder for state, lock and logs (default: the OS data folder, or $CDD_DATA_DIR).",
)
@click.option("-v", "--verbose", is_flag=True, help="Debug-level logs.")
@click.pass_context
def main(
    ctx: click.Context, config_file: Path | None, data_dir: Path | None, verbose: bool
) -> None:
    """Unofficial ChildDiary backup: archives photos, videos and PDFs and
    sends the daily summaries to Telegram."""
    app = App(
        config_file=(config_file or default_config_file()).expanduser(),
        data_dir=(data_dir or default_data_dir()).expanduser(),
        verbose=verbose,
    )
    app.paths.ensure()
    setup_logging(app.paths.log_dir, verbose)
    ctx.obj = app


def execute_run(
    app: App,
    no_notify: bool = False,
    archive_dir: Path | None = None,
    dry_run: bool = False,
    since: str | None = None,
) -> int:
    """One full run over every account. Returns the process exit code."""
    # Prevent overlapping runs (manual + scheduled).
    lock_fh = app.paths.lock_file.open("w")
    try:
        fcntl.flock(lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        log.warning("Another run is already in progress; exiting.")
        return 0

    try:
        config = app.config
        if archive_dir is not None:
            config = replace(config, archive_dir=archive_dir.expanduser())
        strings = config.strings

        try:
            real_notifier = build_notifier(config.notifiers, strings)
        except ValueError as e:
            raise click.ClickException(str(e)) from e
        notifier: Notifier = NullNotifier() if (no_notify or dry_run) else real_notifier
        if dry_run:
            log.info("Dry run: nothing will be downloaded, written or sent.")

        total_failed = 0
        errors: list[str] = []
        with State.open(app.paths.state_db, app.paths.legacy_state_file) as state:
            if since and not dry_run:
                forgotten = state.forget_since(since)
                log.info(
                    "Forgot %d entries since %s; they will be processed again.", forgotten, since
                )
            for account in config.accounts:
                try:
                    _, failed = run_account(account, config, state, notifier, dry_run=dry_run)
                    total_failed += failed
                except Exception as e:
                    log.exception("[%s] Run failed: %s", account.name, e)
                    errors.append(f"{account.name}: {e}")
        try:
            notifier.flush()  # digests deliver here
        except Exception as e:
            log.exception("Could not deliver the digest: %s", e)
            errors.append(f"digest: {e}")

        # The failure alert always goes through the real services, even with --no-notify.
        if (errors or total_failed) and not dry_run:
            summary = []
            if errors:
                summary.append(strings.failure_accounts + "\n" + "\n".join(errors))
            if total_failed:
                summary.append(strings.failure_entries.format(count=total_failed))
            try:
                real_notifier.send_message(strings.failure_header + "\n" + "\n".join(summary))
            except Exception:
                log.exception("Could not send the failure alert.")
            return 1
        return 0
    finally:
        fcntl.flock(lock_fh, fcntl.LOCK_UN)
        lock_fh.close()


@main.command()
@click.option(
    "--no-notify",
    "--no-telegram",
    "no_notify",
    is_flag=True,
    help="Archive to disk only, no notifications (backfill, reprocessing).",
)
@click.option(
    "--archive-dir",
    type=click.Path(path_type=Path),
    default=None,
    help="Archive root (overrides archive_dir from the config).",
)
@click.option("--dry-run", is_flag=True, help="Only log what would be processed; touch nothing.")
@click.option(
    "--since",
    metavar="YYYY-MM-DD",
    default=None,
    help="Process entries from this date again (existing files are kept).",
)
@click.pass_obj
def run(
    app: App, no_notify: bool, archive_dir: Path | None, dry_run: bool, since: str | None
) -> None:
    """Download new entries, archive them and notify."""
    if since and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", since):
        raise click.BadParameter("expected YYYY-MM-DD", param_hint="--since")
    sys.exit(execute_run(app, no_notify, archive_dir, dry_run, since))


@main.command()
@click.option(
    "--schedule",
    default=None,
    help=(
        "Cron expression in the school's timezone "
        f"(default: $CDD_SCHEDULE or '{DEFAULT_SCHEDULE}')."
    ),
)
@click.option("--run-on-start", is_flag=True, help="Also run immediately when the daemon starts.")
@click.pass_obj
def daemon(app: App, schedule: str | None, run_on_start: bool) -> None:
    """Stay running and execute `run` on a schedule (Docker, NAS)."""
    expression = schedule or os.environ.get("CDD_SCHEDULE") or DEFAULT_SCHEDULE
    try:
        validate_schedule(expression)
    except ValueError as e:
        raise click.ClickException(str(e)) from e
    config = app.config  # fail fast on a broken config
    log.info("Daemon started: schedule %r in %s.", expression, config.timezone)
    run_daemon(
        expression,
        config.tzinfo,
        DaemonFiles.in_dir(app.paths.data_dir),
        lambda: execute_run(app),
        run_on_start=run_on_start,
    )


@main.command()
@click.pass_obj
def health(app: App) -> None:
    """Exit 0 if the daemon is alive and its last run succeeded (Docker HEALTHCHECK)."""
    ok, detail = check_health(DaemonFiles.in_dir(app.paths.data_dir))
    click.echo(detail)
    sys.exit(0 if ok else 1)


@main.command()
@click.pass_obj
def status(app: App) -> None:
    """Show what the state knows: entries, failures, archived files."""
    with State.open(app.paths.state_db, app.paths.legacy_state_file) as state:
        st = state.stats()
        failed = state.failed_ids
    console.print(f"State: [bold]{app.paths.state_db}[/bold]")
    span = f"from {(st.first_entry or '-')[:10]} to {(st.last_entry or '-')[:10]}"
    console.print(f"Entries processed: {st.done}  ({span})")
    console.print(f"Entries pending retry: {st.failed}")
    console.print(f"Archived files recorded: {st.media_files}  ({st.media_bytes / 1e9:.2f} GB)")
    console.print(f"Last activity: {st.last_run or '-'}")
    for eid in failed[:10]:
        console.print(f"  failed: {eid}")


@main.command()
@click.option("--hash", "check_hash", is_flag=True, help="Also compare SHA-256 (slower).")
@click.pass_obj
def verify(app: App, check_hash: bool) -> None:
    """Check the archive against the state: missing or changed files."""
    from childdiary_downloader.state import sha256_of

    missing: list[Path] = []
    changed: list[Path] = []
    with State.open(app.paths.state_db, app.paths.legacy_state_file) as state:
        records = state.all_media()
    for _entry_id, m in records:
        if not m.path.exists():
            missing.append(m.path)
        elif m.path.stat().st_size != m.size or (check_hash and sha256_of(m.path) != m.sha256):
            changed.append(m.path)
    for path in missing:
        console.print(f"[red]missing[/red] {path}")
    for path in changed:
        console.print(f"[yellow]changed[/yellow] {path}")
    console.print(
        f"{len(records)} files recorded, {len(missing)} missing, {len(changed)} changed"
        + ("" if records else " (entries archived before 0.2 have no records)")
    )
    sys.exit(1 if missing or changed else 0)


@main.command()
@click.pass_obj
def setup(app: App) -> None:
    """Interactive first-run setup: discovers your children and rooms, writes the config."""
    run_wizard(app.config_file, DEFAULT_ARCHIVE_DIR)


@main.command()
@click.option("--send-test", is_flag=True, help="Also send a test message to Telegram.")
@click.pass_obj
def check(app: App, send_test: bool) -> None:
    """Verify the configuration: logins, children IDs, Telegram, exiftool, archive folder."""
    results = run_checks(app.config, send_test_message=send_test)
    for r in results:
        mark = "[green]OK[/green] " if r.ok else "[red]FAIL[/red]"
        console.print(f"{mark} {r.name}: {r.detail}")
    sys.exit(0 if all(r.ok for r in results if r.name != "exiftool") else 1)


@main.command()
@click.pass_obj
def discover(app: App) -> None:
    """Save one example entry of each type to discovery_dump.json."""
    run_discover(app.config.accounts, app.paths.discovery_file)
    console.print(f"Dump written to [bold]{app.paths.discovery_file}[/bold]")


@main.command("list-groups")
@click.pass_obj
def list_groups_cmd(app: App) -> None:
    """List the rooms and children of each account (to fill in config.yaml)."""
    strings = app.config.strings
    for account_name, info in list_groups(app.config.accounts, strings.unnamed).items():
        console.rule(f"[bold]{account_name}[/bold] ({info['total']['entries']} entries)")
        for kind, title in (("children", "Children"), ("groups", "Rooms / groups")):
            table = Table(title=title, show_lines=False)
            table.add_column("Name")
            table.add_column("ID")
            for gid, name in sorted(info[kind].items(), key=lambda x: x[1]):
                table.add_row(name, gid)
            console.print(table)


if __name__ == "__main__":  # pragma: no cover
    main()
