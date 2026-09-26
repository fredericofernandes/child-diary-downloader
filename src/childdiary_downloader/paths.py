"""Localização dos ficheiros de configuração e de runtime.

Ordem de precedência: opção da linha de comandos > variável de ambiente >
default do sistema operativo (via platformdirs). Em Docker as variáveis
CDD_CONFIG_DIR e CDD_DATA_DIR apontam para os volumes montados.
"""

from __future__ import annotations

import os
from pathlib import Path

from platformdirs import user_config_dir, user_data_dir

APP_NAME = "childdiary-downloader"
CONFIG_FILENAME = "config.yaml"


def default_config_dir() -> Path:
    env = os.environ.get("CDD_CONFIG_DIR")
    return Path(env).expanduser() if env else Path(user_config_dir(APP_NAME))


def default_config_file() -> Path:
    env = os.environ.get("CDD_CONFIG")
    return Path(env).expanduser() if env else default_config_dir() / CONFIG_FILENAME


def default_data_dir() -> Path:
    env = os.environ.get("CDD_DATA_DIR")
    return Path(env).expanduser() if env else Path(user_data_dir(APP_NAME))


class RuntimePaths:
    """Ficheiros de runtime dentro do directório de dados."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.state_file = data_dir / "state.json"
        self.lock_file = data_dir / ".lock"
        self.log_dir = data_dir / "logs"
        self.discovery_file = data_dir / "discovery_dump.json"

    def ensure(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)
