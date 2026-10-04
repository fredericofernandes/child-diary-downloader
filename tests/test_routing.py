import logging

import pytest

from childdiary_downloader.config import Routing
from childdiary_downloader.handlers import UNKNOWN_FOLDER, get_entry_info
from childdiary_downloader.i18n import get_strings
from tests import factories as f
from tests.conftest import make_config

PT = get_strings("pt")
ROUTING = make_config().routing


def test_single_child() -> None:
    entry = f.post(for_items=[f.child(f.MARIA_ID, "Maria", f.ROOM_A_ID)])
    assert get_entry_info(f.E(entry), f.CHILDREN, {}, ROUTING, PT) == (
        ["Maria"],
        "[Maria] ",
        ["Maria"],
    )


def test_two_children_get_one_folder_each() -> None:
    entry = f.event()
    names, prefix, folders = get_entry_info(f.E(entry), f.CHILDREN, {}, ROUTING, PT)
    assert names == ["Maria", "Tomás"]
    assert prefix == "[Maria & Tomás] "
    assert folders == ["Maria", "Tomás"]


def test_other_peoples_children_are_ignored() -> None:
    entry = f.post(for_items=[f.child(f.OTHER_CHILD_ID, "Outra", f.ROOM_A_ID)])
    assert get_entry_info(f.E(entry), f.CHILDREN, {}, ROUTING, PT) == ([], "", [UNKNOWN_FOLDER])


def test_group_mapped_in_config_wins_over_discovery() -> None:
    entry = f.magazine(for_items=[f.group(f.ROOM_A_ID, "Sala Girassóis")])
    discovered = {f.ROOM_A_ID: "Tomás"}  # wrong on purpose
    assert get_entry_info(f.E(entry), f.CHILDREN, discovered, ROUTING, PT) == (
        [],
        "[Sala Girassóis] ",
        ["Maria"],
    )


def test_group_falls_back_to_discovered_mapping() -> None:
    entry = f.magazine(for_items=[f.group("20000000-0000-0000-0000-000000000007", "Sala Nova")])
    discovered = {"20000000-0000-0000-0000-000000000007": "Tomás"}
    assert get_entry_info(f.E(entry), f.CHILDREN, discovered, ROUTING, PT) == (
        [],
        "[Sala Nova] ",
        ["Tomás"],
    )


def test_unmapped_group_gets_own_folder_and_warning(caplog: pytest.LogCaptureFixture) -> None:
    entry = f.magazine(for_items=[f.group("20000000-0000-0000-0000-000000000008", "Yoga")])
    with caplog.at_level(logging.WARNING):
        result = get_entry_info(f.E(entry), f.CHILDREN, {}, ROUTING, PT)
    assert result == ([], "[Yoga] ", ["Yoga"])
    assert "Unmapped group 'Yoga'" in caplog.text


def test_group_for_both_children() -> None:
    entry = f.magazine(for_items=[f.group("20000000-0000-0000-0000-000000000009", "Música")])
    assert get_entry_info(f.E(entry), f.CHILDREN, {}, ROUTING, PT)[2] == ["Maria", "Tomás"]


def test_school_wide_post_respects_child_since() -> None:
    before = f.post(created="2025-06-01T10:00:00.000Z", for_items=[f.instance()])
    after = f.post(created="2025-10-01T10:00:00.000Z", for_items=[f.instance()])
    assert get_entry_info(f.E(before), f.CHILDREN, {}, ROUTING, PT) == (
        [],
        "[Creche Exemplo] ",
        ["Maria"],
    )
    assert get_entry_info(f.E(after), f.CHILDREN, {}, ROUTING, PT) == (
        [],
        "[Creche Exemplo] ",
        ["Maria", "Tomás"],
    )


def test_child_since_never_empties_the_target_list() -> None:
    routing = Routing(instances={"Creche Exemplo": ["Tomás"]}, child_since={"Tomás": "2025-09-01"})
    entry = f.post(created="2025-06-01T10:00:00.000Z", for_items=[f.instance()])
    assert get_entry_info(f.E(entry), f.CHILDREN, {}, routing, PT)[2] == ["Tomás"]


def test_unmapped_school_gets_own_folder(caplog: pytest.LogCaptureFixture) -> None:
    entry = f.post(for_items=[f.instance()])
    entry["InstanceName"] = "Outra Escola"
    with caplog.at_level(logging.WARNING):
        assert get_entry_info(f.E(entry), f.CHILDREN, {}, ROUTING, PT) == (
            [],
            "[Outra Escola] ",
            ["Outra Escola"],
        )
    assert "Unmapped school" in caplog.text


def test_defaults_without_routing_or_strings() -> None:
    entry = f.magazine(for_items=[f.group(f.ROOM_A_ID, "Sala Girassóis")])
    assert get_entry_info(f.E(entry), f.CHILDREN) == ([], "[Sala Girassóis] ", ["Sala Girassóis"])
