"""Command line: ``childdiary run | discover | list-groups``."""

from __future__ import annotations

import fcntl
import logging
import sys
from dataclasses import replace
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from childdiary_downloader import __version__
from childdiary_downloader.api import set_request_delay
from childdiary_downloader.config import Config, ConfigError, load_config
from childdiary_downloader.logging_setup import setup_logging
from childdiary_downloader.notify import Notifier, NullNotifier, Telegram
from childdiary_downloader.paths import RuntimePaths, default_config_file, default_data_dir
from childdiary_downloader.runner import list_groups, run_account, run_discover
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


@main.command()
@click.option("--no-telegram", is_flag=True, help="Archive to disk only (backfill, reprocessing).")
@click.option(
    "--archive-dir",
    type=click.Path(path_type=Path),
    default=None,
    help="Archive root (overrides archive_dir from the config).",
)
@click.pass_obj
def run(app: App, no_telegram: bool, archive_dir: Path | None) -> None:
    """Download new entries, archive them and notify."""
    # Prevent overlapping runs (manual + scheduled).
    lock_fh = app.paths.lock_file.open("w")
    try:
        fcntl.flock(lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        log.warning("Another run is already in progress; exiting.")
        sys.exit(0)

    config = app.config
    if archive_dir is not None:
        config = replace(config, archive_dir=archive_dir.expanduser())
    strings = config.strings

    real_notifier = (
        Telegram(config.telegram.token, config.telegram.chat_id) if config.telegram else None
    )
    notifier: Notifier = NullNotifier() if (no_telegram or real_notifier is None) else real_notifier

    state = State.load(app.paths.state_file)
    total_failed = 0
    errors: list[str] = []
    for account in config.accounts:
        try:
            _, failed = run_account(account, config, state, app.paths.state_file, notifier)
            total_failed += failed
        except Exception as e:
            log.exception("[%s] Run failed: %s", account.name, e)
            errors.append(f"{account.name}: {e}")

    # The failure alert always goes through the real bot, even with --no-telegram.
    if errors or total_failed:
        summary = []
        if errors:
            summary.append(strings.failure_accounts + "\n" + "\n".join(errors))
        if total_failed:
            summary.append(strings.failure_entries.format(count=total_failed))
        if real_notifier is not None:
            try:
                real_notifier.send_message(strings.failure_header + "\n" + "\n".join(summary))
            except Exception:
                log.exception("Could not send the failure alert to Telegram.")
        sys.exit(1)


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
