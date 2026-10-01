"""Builders for fictional API entries, mirroring the real payload shapes.

All names, IDs and URLs are invented. Child and group IDs are stable so tests
can route against them.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

FIXTURES = Path(__file__).parent / "fixtures"

SCHOOL = "Creche Exemplo"
SCHOOL_ID = "10000000-0000-0000-0000-000000000001"
MARIA_ID = "00000000-0000-0000-0000-000000000001"
TOMAS_ID = "00000000-0000-0000-0000-000000000002"
OTHER_CHILD_ID = "00000000-0000-0000-0000-000000000099"
ROOM_A_ID = "20000000-0000-0000-0000-000000000001"  # Sala Girassóis (Maria)
ROOM_B_ID = "20000000-0000-0000-0000-000000000002"  # Sala Papoilas (Tomás)
CHILDREN = {MARIA_ID: "Maria", TOMAS_ID: "Tomás"}

CDN = "https://cdn.example.test/entries"


def creator() -> dict[str, Any]:
    return {
        "Deleted": False,
        "Type": "User",
        "Id": "30000000-0000-0000-0000-000000000001",
        "AvatarMediaUrl": f"{CDN}/avatar.jpg",
        "GroupId": None,
        "Description": "Educadora Exemplo",
    }


def child(child_id: str, name: str, group_id: str) -> dict[str, Any]:
    return {
        "Deleted": False,
        "Type": "Child",
        "Id": child_id,
        "AvatarMediaUrl": f"{CDN}/{child_id}.jpg",
        "GroupId": group_id,
        "Description": name,
    }


def group(group_id: str, name: str) -> dict[str, Any]:
    return {
        "Deleted": False,
        "Type": "Group",
        "Id": group_id,
        "AvatarMediaUrl": None,
        "GroupId": None,
        "Description": name,
    }


def instance() -> dict[str, Any]:
    return {
        "Deleted": False,
        "Type": "Instance",
        "Id": SCHOOL_ID,
        "AvatarMediaUrl": None,
        "GroupId": None,
        "Description": SCHOOL,
    }


def media(media_id: str, ext: str, order: int = 1) -> dict[str, Any]:
    mime = {
        ".jpg": "image/jpeg",
        ".png": "image/png",
        ".mp4": "video/mp4",
        ".pdf": "application/pdf",
    }
    return {
        "CreatedOn": "2026-03-10T10:00:00.000Z",
        "Id": media_id,
        "DisplayOrder": order,
        "Encoded": None,
        "Extension": ext,
        "Type": mime.get(ext, "application/octet-stream"),
        "Url": f"{CDN}/{media_id}{ext}?sig=fake",
    }


def _base(
    entry_id: str, entry_type: int, created: str, display: str | None = None
) -> dict[str, Any]:
    return {
        "InstanceId": SCHOOL_ID,
        "InstanceName": SCHOOL,
        "GroupName": None,
        "CanUpdateRestricted": False,
        "CanUpdate": False,
        "Creator": creator(),
        "Comments": [],
        "Reactions": [],
        "Categories": [],
        "SharedWith": "Everyone",
        "ShareSeparately": None,
        "CommentsEnabled": True,
        "Type": entry_type,
        "Id": entry_id,
        "CreatedOn": created,
        "DisplayDate": display or created,
    }


def post(
    entry_id: str = "e1000000-0000-0000-0000-000000000001",
    *,
    created: str = "2026-03-10T10:15:30.000Z",
    display: str | None = None,
    for_items: list[dict[str, Any]] | None = None,
    text: str = "<p>Hoje fizemos pinturas com os dedos.</p><p>Foi divertido!</p>",
    title: str | None = None,
    medias: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Type 1: photo/text post."""
    entry = _base(entry_id, 1, created, display)
    entry.update(
        {
            "For": for_items if for_items is not None else [child(MARIA_ID, "Maria", ROOM_A_ID)],
            "Medias": medias
            if medias is not None
            else [media("m1000000-0000-0000-0000-000000000001", ".jpg")],
            "Text": text,
            "Title": title,
        }
    )
    return entry


def routine(
    entry_id: str = "e2000000-0000-0000-0000-000000000001",
    *,
    created: str = "2026-03-10T08:22:36.807Z",
    for_items: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Type 2: daily routine."""
    entry = _base(entry_id, 2, created, "2026-03-10T00:00:00Z")
    entry.update(
        {
            "Date": "2026-03-10T00:00:00Z",
            "For": for_items if for_items is not None else [child(MARIA_ID, "Maria", ROOM_A_ID)],
            "Medias": [],
            "Categories": None,
            "Times": [
                {
                    "TimeIn": "2026-03-10T08:22:32.390Z",
                    "TimeInFamilyMember": "Mãe",
                    "TimeInUserId": "x",
                    "TimeOut": "2026-03-10T16:58:33.571Z",
                    "TimeOutFamilyMember": "Pai",
                    "TimeOutUserId": "x",
                }
            ],
            "Meals": [
                {
                    "Title": "MorningBreak",
                    "Description": "Fruta",
                    "MealStatus": "All",
                    "Drink": "Water",
                    "Notes": None,
                },
                {
                    "Title": "Lunch",
                    "Description": "Sopa e peixe",
                    "MealStatus": "Most",
                    "Drink": None,
                    "Notes": None,
                },
                {
                    "Title": "Dinner",
                    "Description": "Iogurte",
                    "MealStatus": "Half",
                    "Drink": "Milk",
                    "Notes": None,
                },
            ],
            "SleepTimes": [
                {
                    "begin": "2026-03-10T12:15:22.322Z",
                    "end": "2026-03-10T14:24:35.724Z",
                    "Checks": None,
                    "BeginUserId": "x",
                    "EndUserId": "x",
                }
            ],
            "ToiletTimes": [{"type": "Xixi"}, {"type": "Cocó"}],
            "Activities": [{"Description": "Música"}, {"Description": "Jogo livre"}],
            "Bottles": [],
            "Occurrences": [],
            "Confirmed": True,
            "Version": None,
        }
    )
    return entry


def magazine(
    entry_id: str = "e3000000-0000-0000-0000-000000000001",
    *,
    created: str = "2026-03-11T13:21:27.783Z",
    for_items: list[dict[str, Any]] | None = None,
    medias: list[dict[str, Any]] | None = None,
    boxes: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Type 3: "magazine" post made of ordered Boxes."""
    if medias is None:
        medias = [
            media("m3000000-0000-0000-0000-000000000001", ".jpg", 1),
            media("m3000000-0000-0000-0000-000000000002", ".jpg", 2),
            media("m3000000-0000-0000-0000-000000000003", ".mp4", 3),
        ]
    if boxes is None:
        boxes = [
            {"Order": 1, "Type": "Title", "Text": "Dia da Primavera 🌸", "Medias": None},
            # Deliberately out of order and listing the medias reversed: the
            # handler must sort by Order and follow the box's media order.
            {
                "Order": 3,
                "Type": "Media",
                "Text": None,
                "Medias": [m["Id"] for m in reversed(medias)],
            },
            {
                "Order": 2,
                "Type": "Text",
                "Text": "<p>Queridas Famílias,</p><p>Plantámos sementes no jardim.</p>",
                "Medias": None,
            },
        ]
    entry = _base(entry_id, 3, created)
    entry.update(
        {
            "Date": created,
            "For": for_items if for_items is not None else [group(ROOM_A_ID, "Sala Girassóis")],
            "Medias": medias,
            "Boxes": boxes,
            "Tags": [],
            "HideCurriculumTags": False,
            "Title": None,
            "Version": None,
            "Next": None,
            "Event": None,
        }
    )
    return entry


def event(
    entry_id: str = "e5000000-0000-0000-0000-000000000001",
    *,
    created: str = "2026-03-12T15:27:10.887Z",
    for_items: list[dict[str, Any]] | None = None,
    medias: list[dict[str, Any]] | None = None,
    title: str = "Festa da Primavera",
    description: str = "Traga um chapéu de sol.",
) -> dict[str, Any]:
    """Type 5: event / invitation."""
    entry = _base(entry_id, 5, created)
    entry.update(
        {
            "For": for_items
            if for_items is not None
            else [child(MARIA_ID, "Maria", ROOM_A_ID), child(TOMAS_ID, "Tomás", ROOM_B_ID)],
            "Medias": medias
            if medias is not None
            else [media("m5000000-0000-0000-0000-000000000001", ".pdf")],
            "Title": title,
            "Description": description,
            "StartDateTime": "2026-03-20T17:30:00.199Z",
            "EndDateTime": "2026-03-20T18:30:00.199Z",
            "RequiresAnswer": True,
            "VideoCallId": None,
            "Responses": [],
            "Version": 1,
        }
    )
    return entry


def unknown(entry_id: str = "e9000000-0000-0000-0000-000000000001") -> dict[str, Any]:
    entry = _base(entry_id, 9, "2026-03-13T09:00:00.000Z")
    entry.update({"For": [child(MARIA_ID, "Maria", ROOM_A_ID)], "Medias": []})
    return entry


def write_fixture_files() -> None:
    """Regenerate tests/fixtures/*.json from the builders (run by hand)."""
    FIXTURES.mkdir(exist_ok=True)
    for name, entry in {
        "type1_post": post(),
        "type2_routine": routine(),
        "type3_magazine": magazine(),
        "type5_event": event(),
        "type9_unknown": unknown(),
    }.items():
        (FIXTURES / f"{name}.json").write_text(
            json.dumps(entry, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )


def load_fixture(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    return data


if __name__ == "__main__":
    write_fixture_files()
