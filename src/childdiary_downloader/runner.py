"""Orquestração de uma execução: login, paginação, routing e processamento."""

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
    Notifier,
    get_entry_info,
    parse_dt,
    process_unknown,
)
from childdiary_downloader.notify import NullTelegram
from childdiary_downloader.state import State

log = logging.getLogger(__name__)


def run_discover(accounts: list[Account], output: Path) -> None:
    """Guarda um exemplo de cada tipo de entrada, para estudar a API."""
    by_type: dict[Any, Any] = {}
    for account in accounts:
        log.info("[%s] A ler todas as entradas para discovery…", account.name)
        session = login(account.auth_payload())
        entries = fetch_entries(session)
        log.info("[%s] Total de entradas: %d", account.name, len(entries))
        for entry in entries:
            by_type.setdefault(entry.get("Type"), entry)

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as f:
        json.dump(by_type, f, indent=2, ensure_ascii=False)
    log.info("Discovery completo: %d tipo(s): %s", len(by_type), sorted(by_type.keys()))
    log.info("Dump escrito em %s", output)


def list_groups(accounts: list[Account]) -> dict[str, dict[str, dict[str, str]]]:
    """Por conta: {"groups": {id: nome}, "children": {id: nome}}."""
    result: dict[str, dict[str, dict[str, str]]] = {}
    for account in accounts:
        session = login(account.auth_payload())
        entries = fetch_entries(session)
        groups: dict[str, str] = {}
        children: dict[str, str] = {}
        for entry in entries:
            for item in entry.get("For", []):
                if item.get("Type") == "Group":
                    groups[item["Id"]] = item.get("Description", "Sem nome")
                elif item.get("Type") == "Child":
                    children[item["Id"]] = item.get("Description", "Sem nome")
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
    tg: Notifier,
) -> tuple[int, int]:
    """Processa as entradas novas de uma conta. Devolve (processadas, falhadas)."""
    name = account.name
    children = account.children
    routing = config.routing.as_dict()
    archive_root = config.archive_dir
    known_ids = set(state.processed_ids)
    max_age = timedelta(days=config.telegram.max_age_days if config.telegram else 0)

    log.info("[%s] Login…", name)
    session = login(account.auth_payload())

    # Uma entrada que falhou pode estar bem abaixo do ponto de paragem da
    # paginação: enquanto houver falhas pendentes, lê-se tudo (known_ids
    # continua a evitar reprocessar o que já está feito).
    fetch_known = known_ids
    if state.failed_ids:
        log.info(
            "[%s] %d entrada(s) falhada(s) pendente(s): leitura completa.",
            name,
            len(state.failed_ids),
        )
        fetch_known = set()

    log.info("[%s] A ler entradas…", name)
    entries = fetch_entries(session, fetch_known)
    new_entries = [e for e in entries if e.get("Id") not in known_ids]
    log.info("[%s] %d entradas lidas, %d novas.", name, len(entries), len(new_entries))

    # Mais antigas primeiro, para as mensagens e o estado seguirem a cronologia.
    new_entries.sort(key=lambda e: e.get("CreatedOn", ""))

    # GroupId -> nome da criança, a partir das entradas das próprias crianças.
    group_to_child: dict[str, str] = {}
    for entry in entries:
        for item in entry.get("For", []):
            if item.get("Type") == "Child" and item.get("Id") in children:
                gid = item.get("GroupId")
                if gid:
                    group_to_child[gid] = children[item["Id"]]

    processed = 0
    failed = 0
    null_tg = NullTelegram()
    for entry in new_entries:
        names, prefix, folders = get_entry_info(entry, children, group_to_child, routing)
        entry_type = entry.get("Type")
        created_on = entry.get("CreatedOn", "")

        # PDFs vão para <Criança>/Documentos/ só quando a entrada é dirigida
        # exclusivamente às nossas crianças (relatórios, ementas adaptadas…).
        for_items = entry.get("For", [])
        all_ours = bool(for_items) and all(
            i.get("Type") == "Child" and i.get("Id") in children for i in for_items
        )
        doc_folders = list(dict.fromkeys(names)) if all_ours else []

        entry_tg: Notifier = tg
        try:
            # Timestamps trazem "Z" mas são hora local de Portugal: comparar com now() local.
            if max_age and datetime.now() - parse_dt(created_on) > max_age:
                entry_tg = null_tg
        except ValueError:
            pass
        log.info(
            "[%s] A processar type=%s folders=%s prefix=%r date=%s%s",
            name,
            entry_type,
            folders,
            prefix.strip(),
            created_on[:10],
            " (antiga: só arquivo)" if entry_tg is null_tg else "",
        )

        try:
            handler = (
                HANDLERS.get(entry_type, process_unknown)
                if isinstance(entry_type, int)
                else process_unknown
            )
            handler(archive_root, entry, entry_tg, prefix, folders, doc_folders)
        except Exception as e:
            log.error(
                "[%s] Falhou a entrada %s (type=%s): %s", name, entry.get("Id"), entry_type, e
            )
            if entry.get("Id"):
                state.mark_failed(entry["Id"])
                state.save(state_file)
            failed += 1
            continue

        state.mark_processed(entry["Id"], created_on)
        state.save(state_file)
        processed += 1

    log.info("[%s] Terminado. %d processadas, %d falhadas.", name, processed, failed)
    return processed, failed
