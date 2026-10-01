"""config.yaml loading and validation.

Secrets never live in the YAML: any value of the form ``${NAME}`` is replaced
by the environment variable of that name, which is also loaded from a
``.env`` file next to config.yaml.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml
from dotenv import load_dotenv

from childdiary_downloader.i18n import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES, Strings, get_strings

_ENV_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")

DEFAULT_ARCHIVE_DIR = "~/Pictures/Child-Diary"
DEFAULT_MAX_AGE_DAYS = 3
DEFAULT_TIMEZONE = "Europe/Lisbon"
DEFAULT_REQUEST_DELAY = 0.5


class ConfigError(Exception):
    """Missing or invalid configuration. The message is meant for the user."""


@dataclass(frozen=True)
class Account:
    name: str
    username: str
    password: str
    children: dict[str, str]  # child id in the API -> folder name

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


@dataclass(frozen=True)
class DocumentsConfig:
    """Where child-addressed PDFs get their readable-named copy."""

    folder: str
    subfolders: dict[str, list[str]]  # subfolder name -> keywords matched in the title


@dataclass(frozen=True)
class NetworkConfig:
    request_delay_seconds: float = DEFAULT_REQUEST_DELAY


@dataclass(frozen=True)
class Config:
    archive_dir: Path
    language: str
    timezone: str
    accounts: list[Account]
    telegram: TelegramConfig | None
    routing: Routing
    documents: DocumentsConfig
    network: NetworkConfig
    source: Path | None = None

    @property
    def strings(self) -> Strings:
        return get_strings(self.language)

    @property
    def tzinfo(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)


# ---------------------------------------------------------------------------
# Environment interpolation
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
# Validation
# ---------------------------------------------------------------------------


def _require(mapping: dict[str, Any], key: str, where: str) -> Any:
    if key not in mapping or mapping[key] in (None, ""):
        raise ConfigError(f"Missing field '{key}' in {where}.")
    return mapping[key]


def _str_list(value: Any, where: str) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list) and all(isinstance(v, str) for v in value):
        return list(value)
    raise ConfigError(f"{where} must be a name or a list of names.")


def _mapping(raw: Any, where: str) -> dict[str, Any]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ConfigError(f"'{where}' must be a mapping.")
    return raw


def _parse_routing(raw: Any) -> Routing:
    data = _mapping(raw, "routing")
    groups = {
        str(k): _str_list(v, f"routing.groups['{k}']")
        for k, v in _mapping(data.get("groups"), "routing.groups").items()
    }
    instances = {
        str(k): _str_list(v, f"routing.instances['{k}']")
        for k, v in _mapping(data.get("instances"), "routing.instances").items()
    }
    child_since: dict[str, str] = {}
    for k, v in _mapping(data.get("child_since"), "routing.child_since").items():
        text = v.isoformat() if hasattr(v, "isoformat") else str(v)
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            raise ConfigError(f"routing.child_since['{k}'] must be a YYYY-MM-DD date.")
        child_since[str(k)] = text
    return Routing(groups=groups, instances=instances, child_since=child_since)


def _parse_accounts(raw: Any) -> list[Account]:
    if not isinstance(raw, list) or not raw:
        raise ConfigError("'accounts' must be a list with at least one account.")
    accounts: list[Account] = []
    for i, item in enumerate(raw, start=1):
        where = f"accounts[{i}]"
        if not isinstance(item, dict):
            raise ConfigError(f"{where} must be a mapping.")
        name = str(item.get("name") or f"Account {i}")
        username = str(_require(item, "username", where))
        password = str(_require(item, "password", where))
        children_raw = _mapping(item.get("children"), f"{where}.children")
        children = {str(k): str(v) for k, v in children_raw.items()}
        accounts.append(Account(name=name, username=username, password=password, children=children))
    return accounts


def _parse_telegram(raw: Any) -> TelegramConfig | None:
    if raw is None:
        return None
    data = _mapping(raw, "telegram")
    token = str(_require(data, "token", "telegram"))
    chat_id = str(_require(data, "chat_id", "telegram"))
    max_age = data.get("max_age_days", DEFAULT_MAX_AGE_DAYS)
    if not isinstance(max_age, int) or max_age < 0:
        raise ConfigError("telegram.max_age_days must be an integer >= 0.")
    return TelegramConfig(token=token, chat_id=chat_id, max_age_days=max_age)


def _parse_documents(raw: Any, strings: Strings) -> DocumentsConfig:
    data = _mapping(raw, "documents")
    folder = str(data.get("folder") or strings.documents_folder)
    if "subfolders" in data:
        subfolders = {
            str(k): [kw.lower() for kw in _str_list(v, f"documents.subfolders['{k}']")]
            for k, v in _mapping(data.get("subfolders"), "documents.subfolders").items()
        }
    else:
        subfolders = dict(strings.document_subfolders)
    return DocumentsConfig(folder=folder, subfolders=subfolders)


def _parse_network(raw: Any) -> NetworkConfig:
    data = _mapping(raw, "network")
    delay = data.get("request_delay_seconds", DEFAULT_REQUEST_DELAY)
    if not isinstance(delay, int | float) or delay < 0:
        raise ConfigError("network.request_delay_seconds must be a number >= 0.")
    return NetworkConfig(request_delay_seconds=float(delay))


def parse_config(data: Any, source: Path | None = None) -> Config:
    """Build a Config from already-loaded, already-interpolated YAML data."""
    if not isinstance(data, dict):
        raise ConfigError("The configuration file must be a YAML mapping.")

    language = str(data.get("language") or DEFAULT_LANGUAGE).lower()
    if language not in SUPPORTED_LANGUAGES:
        raise ConfigError(f"language must be one of {', '.join(SUPPORTED_LANGUAGES)}.")
    strings = get_strings(language)

    timezone = str(data.get("timezone") or DEFAULT_TIMEZONE)
    try:
        ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError) as e:
        raise ConfigError(f"timezone {timezone!r} is not a valid IANA zone name.") from e

    # Environment wins over the file so the Docker image can mount /archive
    # without the user editing config.yaml.
    archive_dir = Path(
        os.environ.get("CDD_ARCHIVE_DIR") or str(data.get("archive_dir") or DEFAULT_ARCHIVE_DIR)
    ).expanduser()
    return Config(
        archive_dir=archive_dir,
        language=language,
        timezone=timezone,
        accounts=_parse_accounts(data.get("accounts")),
        telegram=_parse_telegram(data.get("telegram")),
        routing=_parse_routing(data.get("routing")),
        documents=_parse_documents(data.get("documents"), strings),
        network=_parse_network(data.get("network")),
        source=source,
    )


def load_config(path: Path) -> Config:
    """Read config.yaml, load the .env next to it and resolve ``${VAR}``."""
    if not path.is_file():
        raise ConfigError(
            f"Configuration file not found: {path}\n"
            "Copy config.example.yaml to that path (or pass --config)."
        )
    load_dotenv(path.parent / ".env", override=False)
    with path.open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    missing: set[str] = set()
    data = _interpolate(raw, missing)
    if missing:
        names = ", ".join(sorted(missing))
        raise ConfigError(
            f"Missing environment variables: {names}\n"
            f"Set them in the environment or in {path.parent / '.env'}."
        )
    return parse_config(data, source=path)
