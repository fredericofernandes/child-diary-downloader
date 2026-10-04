from pathlib import Path

import pytest

from childdiary_downloader.config import ConfigError, load_config, parse_config
from tests.conftest import make_config


def cfg_accounts() -> list[dict[str, object]]:
    return [{"username": "u", "password": "p", "children": {}}]


MINIMAL = """
accounts:
  - name: Creche
    username: familia@example.test
    password: ${CDD_PASSWORD_CRECHE}
    children:
      "00000000-0000-0000-0000-000000000001": Maria
telegram:
  token: ${CDD_TELEGRAM_TOKEN}
  chat_id: "123"
"""


def test_env_interpolation_from_dotenv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CDD_PASSWORD_CRECHE", raising=False)
    monkeypatch.delenv("CDD_TELEGRAM_TOKEN", raising=False)
    (tmp_path / "config.yaml").write_text(MINIMAL)
    (tmp_path / ".env").write_text("CDD_PASSWORD_CRECHE=s3cret\nCDD_TELEGRAM_TOKEN=tok\n")
    cfg = load_config(tmp_path / "config.yaml")
    assert cfg.accounts[0].password == "s3cret"
    assert [n.url for n in cfg.notifiers] == ["tgram://tok/123/"]
    assert cfg.accounts[0].auth_payload() == {
        "Username": "familia@example.test",
        "Password": "s3cret",
        "RememberMe": True,
    }


def test_missing_env_vars_are_reported_together(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("CDD_PASSWORD_CRECHE", raising=False)
    monkeypatch.delenv("CDD_TELEGRAM_TOKEN", raising=False)
    (tmp_path / "config.yaml").write_text(MINIMAL)
    with pytest.raises(ConfigError) as exc:
        load_config(tmp_path / "config.yaml")
    assert "CDD_PASSWORD_CRECHE" in str(exc.value)
    assert "CDD_TELEGRAM_TOKEN" in str(exc.value)


def test_missing_file_is_a_config_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "nope.yaml")


def test_defaults() -> None:
    cfg = make_config()
    assert cfg.language == "pt"
    assert cfg.timezone == "Europe/Lisbon"
    assert cfg.notifiers == []
    assert parse_config({"accounts": cfg_accounts()}).max_age_days == 3
    assert cfg.documents.folder == "Documentos"
    assert cfg.documents.subfolders == {"Ementas": ["ementa"]}
    assert cfg.network.request_delay_seconds == 0.5


def test_english_defaults_follow_language() -> None:
    cfg = make_config(language="en")
    assert cfg.documents.folder == "Documents"
    assert cfg.documents.subfolders == {"Menus": ["menu"]}
    assert cfg.strings.daily_routine == "Daily routine:"


def test_documents_override_keywords_lowercased() -> None:
    cfg = make_config(
        documents={"folder": "Docs", "subfolders": {"Reports": ["Relatório", "REPORT"]}}
    )
    assert cfg.documents.folder == "Docs"
    assert cfg.documents.subfolders == {"Reports": ["relatório", "report"]}


def test_routing_accepts_single_name_and_dates() -> None:
    cfg = make_config(routing={"groups": {"Sala": "Maria"}, "child_since": {"Maria": "2024-09-01"}})
    assert cfg.routing.groups == {"Sala": ["Maria"]}
    assert cfg.routing.child_since == {"Maria": "2024-09-01"}


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"language": "fr"}, "language must be one of"),
        ({"timezone": "Mars/Olympus"}, "not a valid IANA"),
        ({"accounts": []}, "at least one account"),
        ({"accounts": [{"username": "u"}]}, "Missing field 'password'"),
        ({"telegram": {"token": "t"}}, "Missing field 'chat_id'"),
        ({"telegram": {"token": "t", "chat_id": "1", "max_age_days": -1}}, "max_age_days"),
        ({"max_age_days": "soon"}, "max_age_days"),
        ({"notifiers": {"url": "x"}}, "must be a list"),
        ({"notifiers": [{"type": "sms"}]}, "must be 'telegram' or 'apprise'"),
        ({"notifiers": [{"type": "apprise"}]}, "Missing field 'url'"),
        ({"notifiers": [{"url": "ntfy://x", "media": "no"}]}, "media must be"),
        ({"routing": {"child_since": {"Maria": "01/09/2024"}}}, "YYYY-MM-DD"),
        ({"routing": {"groups": {"Sala": 3}}}, "list of names"),
        ({"network": {"request_delay_seconds": "fast"}}, "request_delay_seconds"),
    ],
)
def test_validation_errors(overrides: dict[str, object], message: str) -> None:
    with pytest.raises(ConfigError, match=message):
        make_config(**overrides)


def test_top_level_must_be_mapping() -> None:
    with pytest.raises(ConfigError):
        parse_config(["not", "a", "mapping"])


def test_archive_dir_env_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CDD_ARCHIVE_DIR", str(tmp_path / "vol"))
    assert make_config(archive_dir="/from/file").archive_dir == tmp_path / "vol"
    monkeypatch.delenv("CDD_ARCHIVE_DIR")
    assert make_config(archive_dir="/from/file").archive_dir == Path("/from/file")


def test_notifiers_list_and_legacy_telegram_combine() -> None:
    cfg = make_config(
        telegram={"token": "t", "chat_id": "1", "max_age_days": 7},
        notifiers=[
            {"type": "apprise", "url": "ntfy://ntfy.sh/creche", "media": False, "name": "ntfy"},
            {"type": "telegram", "token": "t2", "chat_id": "2"},
        ],
    )
    assert [(n.url, n.media, n.name) for n in cfg.notifiers] == [
        ("tgram://t/1/", True, "telegram"),
        ("ntfy://ntfy.sh/creche", False, "ntfy"),
        ("tgram://t2/2/", True, "telegram"),
    ]
    assert cfg.max_age_days == 7
    assert make_config(max_age_days=0, telegram={"token": "t", "chat_id": "1"}).max_age_days == 0
