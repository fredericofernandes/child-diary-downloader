from __future__ import annotations

import stat
from pathlib import Path
from typing import Any

import pytest
import responses
import yaml
from click.testing import CliRunner

from childdiary_downloader import api
from childdiary_downloader.cli import main
from childdiary_downloader.config import load_config
from childdiary_downloader.setup_wizard import (
    discover_account,
    env_var_name,
    render_config,
    write_env,
)
from tests import factories as f
from tests.test_runner import mock_api


def test_discover_account_separates_own_children_by_routines() -> None:
    entries = [
        f.routine(for_items=[f.child(f.MARIA_ID, "Maria", f.ROOM_A_ID)]),
        f.magazine(
            for_items=[
                f.child(f.MARIA_ID, "Maria", f.ROOM_A_ID),
                f.child(f.OTHER_CHILD_ID, "Outra", f.ROOM_A_ID),
            ]
        ),
        f.magazine(
            entry_id="e3000000-0000-0000-0000-000000000002",
            for_items=[f.group(f.ROOM_A_ID, "Sala Girassóis")],
        ),
        f.post(for_items=[f.group(f.ROOM_B_ID, "Sala Papoilas")]),
    ]
    entries[0]["InstanceName"] = "Creche Antiga"  # the child moved school at some point
    d = discover_account(entries)
    assert d.school == "Creche Exemplo"
    assert d.schools == {"Creche Exemplo": 3, "Creche Antiga": 1}
    assert d.own_children == {f.MARIA_ID: "Maria"}
    assert d.other_children == {f.OTHER_CHILD_ID: "Outra"}
    assert d.groups == {f.ROOM_A_ID: "Sala Girassóis", f.ROOM_B_ID: "Sala Papoilas"}
    assert d.group_targets(f.ROOM_A_ID) == ["Maria"]
    assert d.group_targets(f.ROOM_B_ID) == []


def test_env_var_name_slugs_accents() -> None:
    assert env_var_name("Creche São João (Bebés)") == "CDD_PASSWORD_CRECHE_SAO_JOAO_BEBES"
    assert env_var_name("***") == "CDD_PASSWORD_ACCOUNT"


def test_render_config_is_valid_yaml_and_loads() -> None:
    text = render_config(
        language="en",
        timezone="Europe/Dublin",
        archive_dir="/archive",
        accounts=[
            {
                "name": 'Crèche "A"',
                "username": "u@x",
                "env_var": "CDD_PASSWORD_A",
                "children": {"id1": "Maria: filha"},
            }
        ],
        routing_groups={"Room: Sun": ["Maria: filha"]},
        routing_instances={'Crèche "A"': ["Maria: filha"]},
        notifiers=[
            {"type": "telegram"},
            {"type": "apprise", "env_var": "CDD_NOTIFIER_1_URL", "media": False},
        ],
    )
    data = yaml.safe_load(text)
    assert data["accounts"][0]["name"] == 'Crèche "A"'
    assert data["routing"]["groups"] == {"Room: Sun": ["Maria: filha"]}
    assert data["max_age_days"] == 3
    assert data["notifiers"] == [
        {
            "type": "telegram",
            "token": "${CDD_TELEGRAM_TOKEN}",
            "chat_id": "${CDD_TELEGRAM_CHAT_ID}",
        },
        {"type": "apprise", "url": "${CDD_NOTIFIER_1_URL}", "media": False},
    ]
    assert (
        yaml.safe_load(
            render_config(
                language="pt",
                timezone="Europe/Lisbon",
                archive_dir="/a",
                accounts=[],
                routing_groups={},
                routing_instances={},
                notifiers=[],
            )
        )["notifiers"]
        == []
    )


def test_write_env_merges_and_sets_mode(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("KEEP=1\nCDD_TELEGRAM_TOKEN=old\n")
    write_env(env, {"CDD_TELEGRAM_TOKEN": "new", "CDD_PASSWORD_X": "pw"})
    assert env.read_text() == "KEEP=1\nCDD_TELEGRAM_TOKEN=new\nCDD_PASSWORD_X=pw\n"
    assert stat.S_IMODE(env.stat().st_mode) == 0o600


@pytest.fixture
def rsps() -> Any:
    with responses.RequestsMock(assert_all_requests_are_fired=False) as r:
        yield r


def test_setup_wizard_end_to_end(
    tmp_path: Path, rsps: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    for var in (
        "CDD_PASSWORD_CRECHE_EXEMPLO",
        "CDD_TELEGRAM_TOKEN",
        "CDD_TELEGRAM_CHAT_ID",
        "CDD_NOTIFIER_1_URL",
    ):
        monkeypatch.delenv(var, raising=False)
    entries = [
        f.routine(for_items=[f.child(f.MARIA_ID, "Maria", f.ROOM_A_ID)]),
        f.routine(
            entry_id="e2000000-0000-0000-0000-000000000002",
            for_items=[f.child(f.TOMAS_ID, "Tomás", f.ROOM_B_ID)],
        ),
        f.magazine(for_items=[f.group(f.ROOM_A_ID, "Sala Girassóis")]),
        f.post(for_items=[f.group("20000000-0000-0000-0000-000000000003", "Yoga")]),
    ]
    mock_api(rsps, entries)
    config_file = tmp_path / "cfg" / "config.yaml"
    answers = "\n".join(
        [
            "pt",  # language
            "",  # timezone default
            str(tmp_path / "archive"),  # archive dir
            "familia@example.test",  # username
            "pw",  # password
            "",  # folder for Maria: defaults to the first name
            "",  # folder for Tomás
            "",  # account name default (school)
            "",  # Sala Girassóis -> suggested Maria
            "-",  # Yoga -> keep in its own folder
            "n",  # another account?
            "y",  # telegram?
            "123456:ABCdefGHI",  # token
            "42",  # chat id
            "y",  # another service?
            "ntfy://ntfy.sh/creche-exemplo",  # url
            "n",  # no media for it
            "n",  # no more services
        ]
    )
    result = CliRunner().invoke(
        main,
        ["--config", str(config_file), "--data-dir", str(tmp_path), "setup"],
        input=answers + "\n",
    )
    assert result.exit_code == 0, result.output
    assert stat.S_IMODE(config_file.stat().st_mode) == 0o600
    cfg = load_config(config_file)
    assert cfg.language == "pt" and cfg.timezone == "Europe/Lisbon"
    assert cfg.accounts[0].name == "Creche Exemplo"
    assert cfg.accounts[0].password == "pw"
    assert cfg.accounts[0].children == {f.MARIA_ID: "Maria", f.TOMAS_ID: "Tomás"}
    assert cfg.routing.groups == {"Sala Girassóis": ["Maria"]}
    assert cfg.routing.instances == {"Creche Exemplo": ["Maria", "Tomás"]}
    assert [(n.url, n.media) for n in cfg.notifiers] == [
        ("tgram://123456:ABCdefGHI/42/", True),
        ("ntfy://ntfy.sh/creche-exemplo", False),
    ]
    assert "childdiary check" in result.output


def test_setup_wizard_login_failure_then_abort(tmp_path: Path, rsps: Any) -> None:
    rsps.add(responses.POST, api.LOGIN_URL, status=401)
    config_file = tmp_path / "config.yaml"
    answers = "\n".join(["pt", "", "/a", "u@x", "pw", "n"])
    result = CliRunner().invoke(
        main,
        ["--config", str(config_file), "--data-dir", str(tmp_path), "setup"],
        input=answers + "\n",
    )
    assert result.exit_code == 1
    assert "Login or download failed" in result.output
    assert not config_file.exists()


def test_setup_refuses_to_overwrite_without_consent(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text("x: 1\n")
    result = CliRunner().invoke(
        main, ["--config", str(config_file), "--data-dir", str(tmp_path), "setup"], input="n\n"
    )
    assert result.exit_code == 1
    assert config_file.read_text() == "x: 1\n"


def test_suggest_targets_uses_membership_then_room_words_then_everyone() -> None:
    judo = "20000000-0000-0000-0000-000000000010"
    yoga = "20000000-0000-0000-0000-000000000011"
    entries = [
        f.routine(for_items=[f.child(f.MARIA_ID, "Maria", f.ROOM_A_ID)]),
        f.routine(
            entry_id="e2000000-0000-0000-0000-000000000002",
            for_items=[f.child(f.TOMAS_ID, "Tomás", f.ROOM_B_ID)],
        ),
        f.magazine(for_items=[f.group(f.ROOM_A_ID, "Sala Girassóis")]),
        f.magazine(
            entry_id="e3000000-0000-0000-0000-000000000002",
            for_items=[f.group(f.ROOM_B_ID, "Sala Papoilas")],
        ),
        f.magazine(
            entry_id="e3000000-0000-0000-0000-000000000003",
            for_items=[f.group(judo, "Judo Papoilas + Tulipas")],
        ),
        f.magazine(
            entry_id="e3000000-0000-0000-0000-000000000004",
            for_items=[f.group(yoga, "Yoga da Sala")],
        ),
    ]
    d = discover_account(entries)
    folders = {f.MARIA_ID: "Maria", f.TOMAS_ID: "Tomás"}
    assert d.suggest_targets(f.ROOM_A_ID, folders) == ["Maria"]  # member
    assert d.suggest_targets(judo, folders) == ["Tomás"]  # "Papoilas" names Tomás's room
    assert d.suggest_targets(yoga, folders) == ["Maria", "Tomás"]  # nothing to go on
