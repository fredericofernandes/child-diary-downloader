from datetime import datetime

import pytest

from childdiary_downloader.handlers import parse_dt, strip_html, summarize_for_filename
from childdiary_downloader.i18n import get_strings

PT = get_strings("pt").greeting_pattern
EN = get_strings("en").greeting_pattern


def test_strip_html_paragraphs_breaks_and_entities() -> None:
    html = "<p>Olá &amp; bem-vindos</p><p>Linha 1<br/>Linha 2</p><b>&nbsp;fim&#39;s</b>"
    assert strip_html(html) == "Olá & bem-vindos\nLinha 1\nLinha 2\n fim's"


def test_strip_html_plain_text_untouched() -> None:
    assert strip_html("  texto simples  ") == "texto simples"


@pytest.mark.parametrize(
    ("text", "pattern", "expected"),
    [
        (
            "Querida Família,\nRelatório de desenvolvimento do 2.º período",
            PT,
            "Relatório de desenvolvimento do 2.º período",
        ),
        (
            "Olá Pais! 💕\nEmenta adaptada para a próxima semana",
            PT,
            "Ementa adaptada para a próxima semana",
        ),
        (
            "Dear families,\nSpring term development report attached",
            EN,
            "Spring term development report attached",
        ),
        ("curto\nainda curto", PT, "curto"),  # fallback: first non-empty line
        ("", PT, ""),
    ],
)
def test_summarize_for_filename(text: str, pattern: str, expected: str) -> None:
    assert summarize_for_filename(text, pattern) == expected


def test_summarize_truncates_to_60_chars() -> None:
    long = "A" * 100
    assert len(summarize_for_filename(long, PT)) == 60


def test_parse_dt_with_and_without_fraction() -> None:
    assert parse_dt("2026-03-10T08:22:32.390Z") == datetime(2026, 3, 10, 8, 22, 32, 390000)
    assert parse_dt("2026-03-10T08:22:32Z") == datetime(2026, 3, 10, 8, 22, 32)


def test_parse_dt_rejects_garbage() -> None:
    with pytest.raises(ValueError):
        parse_dt("10/03/2026")
