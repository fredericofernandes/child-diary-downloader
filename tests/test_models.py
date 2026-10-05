import pytest

from childdiary_downloader.models import EntryParseError, parse_entry
from tests import factories as f


def test_parse_each_fixture_keeps_extra_fields() -> None:
    for name in ("type1_post", "type2_routine", "type3_magazine", "type5_event", "type9_unknown"):
        raw = f.load_fixture(name)
        entry = parse_entry(raw)
        assert entry.id == raw["Id"] and entry.type == raw["Type"]
        assert entry.raw()["Creator"] == raw["Creator"]  # not declared, still carried


def test_routine_fields() -> None:
    entry = parse_entry(f.routine())
    assert entry.meals[1].title == "Lunch" and entry.meals[1].drink is None
    assert entry.sleep_times[0].begin == "2026-03-10T12:15:22.322Z"
    assert entry.toilet_times[1].type == "Cocó"
    assert [a.description for a in entry.activities] == ["Música", "Jogo livre"]
    assert entry.date_source == "2026-03-10T00:00:00Z"


def test_null_lists_become_empty_and_children_lookup() -> None:
    raw = f.post()
    raw["Medias"] = None
    raw["Boxes"] = None
    entry = parse_entry(raw)
    assert entry.medias == [] and entry.boxes == []
    assert entry.children(f.CHILDREN) == ["Maria"]
    assert entry.children({}) == []


def test_missing_id_is_a_parse_error() -> None:
    raw = f.post()
    del raw["Id"]
    with pytest.raises(EntryParseError, match="entry \\?"):
        parse_entry(raw)


def test_wrong_types_are_reported_with_the_id() -> None:
    raw = f.post()
    raw["Medias"] = [{"Id": "m", "Url": None}]
    with pytest.raises(EntryParseError) as exc:
        parse_entry(raw)
    assert exc.value.entry_id == raw["Id"]
    assert exc.value.error.error_count() == 1


def test_null_texts_become_empty_strings() -> None:
    """Old routines have meals with "Description": null (seen in real data)."""
    raw = f.routine()
    raw["Meals"][0]["Description"] = None
    raw["Meals"][1]["Title"] = None
    raw["Activities"][0]["Description"] = None
    raw["ToiletTimes"][0]["type"] = None
    raw["Medias"] = [{"Id": "m", "Url": "https://x.test/a", "Extension": None}]
    entry = parse_entry(raw)
    assert entry.meals[0].description == "" and entry.meals[1].title == ""
    assert entry.activities[0].description == "" and entry.toilet_times[0].type == ""
    assert entry.medias[0].extension == ""
