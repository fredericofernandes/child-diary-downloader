from pathlib import Path

import pytest

from childdiary_downloader import paths


def test_env_overrides(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CDD_CONFIG_DIR", str(tmp_path / "c"))
    monkeypatch.setenv("CDD_DATA_DIR", str(tmp_path / "d"))
    monkeypatch.delenv("CDD_CONFIG", raising=False)
    assert paths.default_config_file() == tmp_path / "c" / "config.yaml"
    assert paths.default_data_dir() == tmp_path / "d"
    monkeypatch.setenv("CDD_CONFIG", str(tmp_path / "other.yaml"))
    assert paths.default_config_file() == tmp_path / "other.yaml"


def test_os_defaults_are_absolute(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("CDD_CONFIG_DIR", "CDD_DATA_DIR", "CDD_CONFIG"):
        monkeypatch.delenv(var, raising=False)
    assert paths.default_config_file().is_absolute()
    assert paths.default_data_dir().is_absolute()
    assert paths.APP_NAME in str(paths.default_data_dir())


def test_runtime_paths_ensure(tmp_path: Path) -> None:
    rp = paths.RuntimePaths(tmp_path / "data")
    rp.ensure()
    assert rp.log_dir.is_dir() and rp.state_file.parent.is_dir()
