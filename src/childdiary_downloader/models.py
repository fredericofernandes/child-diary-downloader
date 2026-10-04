"""Typed view of the ChildDiary API payloads.

Only the fields the archiver uses are declared; everything else is kept as
extra data (``extra="allow"``) so a dump still round-trips and a new field
from the school never breaks a run. Field names follow Python conventions,
aliases follow the API's PascalCase (and the few camelCase it has).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

Raw = dict[str, Any]


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)


class ForItem(ApiModel):
    """Who an entry is for: a child, a room/group or the whole school."""

    type: str = Field(alias="Type")
    id: str = Field(alias="Id")
    description: str | None = Field(default=None, alias="Description")
    group_id: str | None = Field(default=None, alias="GroupId")


class Media(ApiModel):
    id: str = Field(alias="Id")
    url: str = Field(alias="Url")
    extension: str = Field(default="", alias="Extension")
    display_order: int | None = Field(default=None, alias="DisplayOrder")


class Box(ApiModel):
    """Block of a "magazine" post (type 3): Title, Text or Media."""

    order: int = Field(default=0, alias="Order")
    type: str | None = Field(default=None, alias="Type")
    text: str | None = Field(default=None, alias="Text")
    medias: list[str] | None = Field(default=None, alias="Medias")


class Times(ApiModel):
    time_in: str | None = Field(default=None, alias="TimeIn")
    time_in_family_member: str | None = Field(default=None, alias="TimeInFamilyMember")
    time_out: str | None = Field(default=None, alias="TimeOut")
    time_out_family_member: str | None = Field(default=None, alias="TimeOutFamilyMember")


class Meal(ApiModel):
    title: str = Field(default="", alias="Title")
    description: str = Field(default="", alias="Description")
    meal_status: str | None = Field(default=None, alias="MealStatus")
    drink: str | None = Field(default=None, alias="Drink")


class SleepTime(ApiModel):
    begin: str | None = None
    end: str | None = None


class ToiletTime(ApiModel):
    type: str = ""


class Activity(ApiModel):
    description: str = Field(default="", alias="Description")


class Entry(ApiModel):
    """One diary entry of any type. ``type`` 1 = post, 2 = routine, 3 = magazine, 5 = event."""

    id: str = Field(alias="Id")
    type: int | None = Field(default=None, alias="Type")
    created_on: str = Field(default="", alias="CreatedOn")
    display_date: str | None = Field(default=None, alias="DisplayDate")
    instance_name: str | None = Field(default=None, alias="InstanceName")
    for_: list[ForItem] = Field(default_factory=list, alias="For")
    medias: list[Media] = Field(default_factory=list, alias="Medias")
    # type 1 and 5
    title: str | None = Field(default=None, alias="Title")
    text: str | None = Field(default=None, alias="Text")
    description: str | None = Field(default=None, alias="Description")
    # type 2
    times: list[Times] = Field(default_factory=list, alias="Times")
    meals: list[Meal] = Field(default_factory=list, alias="Meals")
    sleep_times: list[SleepTime] = Field(default_factory=list, alias="SleepTimes")
    toilet_times: list[ToiletTime] = Field(default_factory=list, alias="ToiletTimes")
    activities: list[Activity] = Field(default_factory=list, alias="Activities")
    occurrences: list[Any] = Field(default_factory=list, alias="Occurrences")
    # type 3
    boxes: list[Box] = Field(default_factory=list, alias="Boxes")
    # type 5
    start_date_time: str | None = Field(default=None, alias="StartDateTime")
    end_date_time: str | None = Field(default=None, alias="EndDateTime")
    requires_answer: bool = Field(default=False, alias="RequiresAnswer")
    video_call_id: str | None = Field(default=None, alias="VideoCallId")

    @property
    def date_source(self) -> str:
        """The day an entry belongs to: DisplayDate, else CreatedOn."""
        return self.display_date or self.created_on or ""

    def children(self, known: dict[str, str]) -> list[str]:
        """Folder names of the known children this entry is addressed to."""
        return [known[item.id] for item in self.for_ if item.type == "Child" and item.id in known]

    def raw(self) -> Raw:
        """The payload as the API sent it (for dumps and logs)."""
        return self.model_dump(by_alias=True)


class EntryParseError(ValueError):
    def __init__(self, entry_id: str, error: ValidationError) -> None:
        super().__init__(f"entry {entry_id}: {error.error_count()} invalid field(s)")
        self.entry_id = entry_id
        self.error = error


def parse_entry(raw: Raw) -> Entry:
    """Validate one payload. Raises EntryParseError with the entry id when it
    can; lists in the payload that are ``null`` are treated as empty."""
    cleaned = {k: ([] if v is None and k in _LIST_FIELDS else v) for k, v in raw.items()}
    try:
        return Entry.model_validate(cleaned)
    except ValidationError as e:
        raise EntryParseError(str(raw.get("Id", "?")), e) from e


_LIST_FIELDS = {
    "For",
    "Medias",
    "Times",
    "Meals",
    "SleepTimes",
    "ToiletTimes",
    "Activities",
    "Occurrences",
    "Boxes",
}
