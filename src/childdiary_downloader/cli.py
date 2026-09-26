"""Linha de comandos: ``childdiary run | discover | list-groups``."""

from __future__ import annotations

import fcntl
import logging
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from childdiary_downloader import __version__
from childdiary_downloader.config import Config, ConfigError, load_config
from childdiary_downloader.logging_setup import setup_logging
from childdiary_downloader.notify import NullTelegram, Telegram
from childdiary_downloader.paths import RuntimePaths, default_config_file, default_data_dir
from childdiary_downloader.runner import list_groups, run_account, run_discover
from childdiary_downloader.state import State

log = logging.getLogger(__name__)
console = Console()


class App:
    """Contexto partilhado pelos subcomandos."""

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
        return self._config


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, prog_name="childdiary")
@click.option(
    "--config",
    "config_file",
    type=click.Path(path_type=Path),
    default=None,
    help="Ficheiro config.yaml (default: pasta de configuração do sistema ou $CDD_CONFIG).",
)
@click.option(
    "--data-dir",
    type=click.Path(path_type=Path),
    default=None,
    help="Pasta para estado, lock e logs (default: pasta de dados do sistema ou $CDD_DATA_DIR).",
)
@click.option("-v", "--verbose", is_flag=True, help="Logs em DEBUG.")
@click.pass_context
def main(
    ctx: click.Context, config_file: Path | None, data_dir: Path | None, verbose: bool
) -> None:
    """Backup não oficial do ChildDiary: arquiva fotos, vídeos e PDFs e envia
    os resumos diários para o Telegram."""
    app = App(
        config_file=(config_file or default_config_file()).expanduser(),
        data_dir=(data_dir or default_data_dir()).expanduser(),
        verbose=verbose,
    )
    app.paths.ensure()
    setup_logging(app.paths.log_dir, verbose)
    ctx.obj = app


@main.command()
@click.option("--no-telegram", is_flag=True, help="Só arquiva em disco (backfill/reprocessamento).")
@click.option(
    "--archive-dir",
    type=click.Path(path_type=Path),
    default=None,
    help="Pasta raiz do arquivo (sobrepõe-se ao archive_dir do config).",
)
@click.pass_obj
def run(app: App, no_telegram: bool, archive_dir: Path | None) -> None:
    """Descarrega as entradas novas, arquiva e notifica."""
    # Evita execuções sobrepostas (manual + agendada).
    lock_fh = app.paths.lock_file.open("w")
    try:
        fcntl.flock(lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        log.warning("Já há uma execução em curso; a sair.")
        sys.exit(0)

    config = app.config
    if archive_dir is not None:
        config = Config(
            archive_dir=archive_dir.expanduser(),
            accounts=config.accounts,
            telegram=config.telegram,
            routing=config.routing,
            source=config.source,
        )

    real_tg = Telegram(config.telegram.token, config.telegram.chat_id) if config.telegram else None
    tg = NullTelegram() if (no_telegram or real_tg is None) else real_tg

    state = State.load(app.paths.state_file)
    total_failed = 0
    errors: list[str] = []
    for account in config.accounts:
        try:
            _, failed = run_account(account, config, state, app.paths.state_file, tg)
            total_failed += failed
        except Exception as e:
            log.exception("[%s] Execução falhou: %s", account.name, e)
            errors.append(f"{account.name}: {e}")

    # O alerta de falha vai sempre pelo bot real, mesmo em --no-telegram.
    if errors or total_failed:
        summary = []
        if errors:
            summary.append("Erro ao correr conta(s):\n" + "\n".join(errors))
        if total_failed:
            summary.append(
                f"{total_failed} entrada(s) falharam (serão retentadas na próxima execução)."
            )
        if real_tg is not None:
            try:
                real_tg.send_message("⚠️ child-diary-downloader:\n" + "\n".join(summary))
            except Exception:
                log.exception("Não foi possível enviar o alerta de falha para o Telegram.")
        sys.exit(1)


@main.command()
@click.pass_obj
def discover(app: App) -> None:
    """Guarda um exemplo de cada tipo de entrada em discovery_dump.json."""
    run_discover(app.config.accounts, app.paths.discovery_file)
    console.print(f"Dump escrito em [bold]{app.paths.discovery_file}[/bold]")


@main.command("list-groups")
@click.pass_obj
def list_groups_cmd(app: App) -> None:
    """Lista as salas e crianças de cada conta (para preencher o config.yaml)."""
    for account_name, info in list_groups(app.config.accounts).items():
        console.rule(f"[bold]{account_name}[/bold] ({info['total']['entries']} entradas)")
        for kind, title in (("children", "Crianças"), ("groups", "Salas / grupos")):
            table = Table(title=title, show_lines=False)
            table.add_column("Nome")
            table.add_column("ID")
            for gid, name in sorted(info[kind].items(), key=lambda x: x[1]):
                table.add_row(name, gid)
            console.print(table)


if __name__ == "__main__":  # pragma: no cover
    main()
