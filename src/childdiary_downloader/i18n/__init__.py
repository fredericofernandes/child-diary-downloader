"""User-facing strings for notifications and archive folder names.

The ChildDiary API returns enum-like values in English ("Lunch", "All",
"Water"); everything the family reads is produced here, in the language
chosen with ``language:`` in config.yaml. Adding a language is a new module
exposing a ``STRINGS`` instance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib import import_module

SUPPORTED_LANGUAGES = ("pt", "en")
DEFAULT_LANGUAGE = "pt"


@dataclass(frozen=True)
class Strings:
    code: str
    # Daily routine (entry type 2)
    daily_routine: str
    schedule: str
    check_in: str
    check_out: str
    meals: str
    drink: str
    meal_titles: dict[str, str]
    meal_status: dict[str, str]
    drink_names: dict[str, str]
    naps: str
    hygiene: str
    activities: str
    occurrences: str
    # Events (entry type 5)
    event: str
    event_start: str
    event_end: str
    event_requires_answer: str
    video_call: str
    # Misc notifications
    unknown_entry_type: str  # {type}
    failure_header: str
    failure_accounts: str
    failure_entries: str  # {count}
    # Archive layout defaults (overridable in config.yaml -> documents:)
    documents_folder: str
    document_subfolders: dict[str, list[str]]
    # Fallback labels when the API gives no name
    group_fallback: str
    school_fallback: str
    # Date shown in captions, strftime format
    caption_date_format: str
    # Lines that look like greetings are skipped when naming title-less PDFs
    greeting_pattern: str
    # Shown by `childdiary list-groups`
    unnamed: str = "?"
    extra: dict[str, str] = field(default_factory=dict)


def get_strings(language: str) -> Strings:
    if language not in SUPPORTED_LANGUAGES:
        raise ValueError(f"Unsupported language {language!r}; choose one of {SUPPORTED_LANGUAGES}")
    module = import_module(f"{__name__}.{language}")
    strings: Strings = module.STRINGS
    return strings


__all__ = ["DEFAULT_LANGUAGE", "SUPPORTED_LANGUAGES", "Strings", "get_strings"]
