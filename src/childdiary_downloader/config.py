"""Leitura e validação do config.yaml.

Segredos não vivem no YAML: qualquer valor no formato ``${NOME}`` é
substituído pela variável de ambiente correspondente, carregada também de um
ficheiro ``.env`` ao lado do config.yaml.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

_ENV_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")

DEFAULT_ARCHIVE_DIR = "~/Pictures/Child-Diary"
DEFAULT_MAX_AGE_DAYS = 3


class ConfigError(Exception):
    """Configuração em falta ou inválida. A mensagem é para o utilizador."""


@dataclass(frozen=True)
class Account:
    name: str
    username: str
    password: str
    children: dict[str, str]

    def auth_payload(self) -> dict[str, Any]:
        return {"Username": self.username, "Password": self.password, "RememberMe": True}


@dataclass(frozen=True)
class TelegramConfig:
    token: str
    chat_id: str
    max_age_days: int = DEFAULT_MAX_AGE_DAYS


@dataclass(frozen=True)
class Routing:
    groups: dict[str, list[str]] = field(default_factory=dict)
    instances: dict[str, list[str]] = field(default_factory=dict)
    child_since: dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"groups": self.groups, "instances": self.instances, "child_since": self.child_since}


@dataclass(frozen=True)
class Config:
    archive_dir: Path
    accounts: list[Account]
    telegram: TelegramConfig | None
    routing: Routing
    source: Path | None = None


# ---------------------------------------------------------------------------
# Interpolação de variáveis de ambiente
# ---------------------------------------------------------------------------


def _interpolate(value: Any, missing: set[str]) -> Any:
    if isinstance(value, str):

        def repl(m: re.Match[str]) -> str:
            name = m.group(1)
            env = os.environ.get(name)
            if env is None:
                missing.add(name)
                return ""
            return env

        return _ENV_RE.sub(repl, value)
    if isinstance(value, dict):
        return {k: _interpolate(v, missing) for k, v in value.items()}
    if isinstance(value, list):
        return [_interpolate(v, missing) for v in value]
    return value


# ---------------------------------------------------------------------------
# Validação
# ---------------------------------------------------------------------------


def _require(mapping: dict[str, Any], key: str, where: str) -> Any:
    if key not in mapping or mapping[key] in (None, ""):
        raise ConfigError(f"Falta o campo '{key}' em {where}.")
    return mapping[key]


def _str_list(value: Any, where: str) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list) and all(isinstance(v, str) for v in value):
        return list(value)
    raise ConfigError(f"{where} deve ser um nome ou uma lista de nomes.")


def _parse_routing(raw: Any) -> Routing:
    if raw is None:
        return Routing()
    if not isinstance(raw, dict):
        raise ConfigError("'routing' deve ser um mapa.")
    groups = {
        str(k): _str_list(v, f"routing.groups['{k}']") for k, v in (raw.get("groups") or {}).items()
    }
    instances = {
        str(k): _str_list(v, f"routing.instances['{k}']")
        for k, v in (raw.get("instances") or {}).items()
    }
    child_since: dict[str, str] = {}
    for k, v in (raw.get("child_since") or {}).items():
        text = v.isoformat() if hasattr(v, "isoformat") else str(v)
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            raise ConfigError(f"routing.child_since['{k}'] deve ser uma data AAAA-MM-DD.")
        child_since[str(k)] = text
    return Routing(groups=groups, instances=instances, child_since=child_since)


def _parse_accounts(raw: Any) -> list[Account]:
    if not isinstance(raw, list) or not raw:
        raise ConfigError("'accounts' deve ser uma lista com pelo menos uma conta.")
    accounts: list[Account] = []
    for i, item in enumerate(raw, start=1):
        where = f"accounts[{i}]"
        if not isinstance(item, dict):
            raise ConfigError(f"{where} deve ser um mapa.")
        name = str(item.get("name") or f"Conta {i}")
        username = str(_require(item, "username", where))
        password = str(_require(item, "password", where))
        children_raw = item.get("children") or {}
        if not isinstance(children_raw, dict):
            raise ConfigError(f"{where}.children deve ser um mapa id -> nome.")
        children = {str(k): str(v) for k, v in children_raw.items()}
        accounts.append(Account(name=name, username=username, password=password, children=children))
    return accounts


def _parse_telegram(raw: Any) -> TelegramConfig | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ConfigError("'telegram' deve ser um mapa.")
    token = str(_require(raw, "token", "telegram"))
    chat_id = str(_require(raw, "chat_id", "telegram"))
    max_age = raw.get("max_age_days", DEFAULT_MAX_AGE_DAYS)
    if not isinstance(max_age, int) or max_age < 0:
        raise ConfigError("telegram.max_age_days deve ser um inteiro >= 0.")
    return TelegramConfig(token=token, chat_id=chat_id, max_age_days=max_age)


def parse_config(data: Any, source: Path | None = None) -> Config:
    """Constrói um Config a partir do YAML já lido e já interpolado."""
    if not isinstance(data, dict):
        raise ConfigError("O ficheiro de configuração deve ser um mapa YAML.")
    archive_dir = Path(str(data.get("archive_dir") or DEFAULT_ARCHIVE_DIR)).expanduser()
    return Config(
        archive_dir=archive_dir,
        accounts=_parse_accounts(data.get("accounts")),
        telegram=_parse_telegram(data.get("telegram")),
        routing=_parse_routing(data.get("routing")),
        source=source,
    )


def load_config(path: Path) -> Config:
    """Lê o config.yaml, carrega o .env ao lado e resolve ``${VAR}``."""
    if not path.is_file():
        raise ConfigError(
            f"Ficheiro de configuração não encontrado: {path}\n"
            "Copia o config.example.yaml para esse caminho (ou usa --config)."
        )
    load_dotenv(path.parent / ".env", override=False)
    with path.open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    missing: set[str] = set()
    data = _interpolate(raw, missing)
    if missing:
        names = ", ".join(sorted(missing))
        raise ConfigError(
            f"Variáveis de ambiente em falta: {names}\n"
            f"Define-as no ambiente ou em {path.parent / '.env'}."
        )
    return parse_config(data, source=path)
