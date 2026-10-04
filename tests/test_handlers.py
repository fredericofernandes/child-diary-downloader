import os
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import requests

from childdiary_downloader import handlers
from childdiary_downloader.config import Config
from childdiary_downloader.handlers import (
    ArchiveContext,
    document_subfolder,
    process_medias,
    process_type1,
    process_type2,
    process_type3,
    process_type5,
    process_unknown,
)
from tests import factories as f
from tests.conftest import RecordingNotifier, make_config


def files_under(root: Path) -> list[str]:
    return sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file())


# --- type 1 -----------------------------------------------------------------


def test_type1_message_and_photo(ctx: ArchiveContext, notifier: RecordingNotifier) -> None:
    process_type1(ctx, f.load_fixture("type1_post"), notifier, "[Maria] ", ["Maria"])
    assert notifier.messages == ["[Maria] Hoje fizemos pinturas com os dedos.\nFoi divertido!"]
    kind, (_path, caption) = notifier.calls[1]
    assert kind == "photo"
    assert caption.startswith("10/03/2026 — Hoje fizemos")
    assert files_under(ctx.root) == ["Maria/2026/2026-03-10/2026-03-10_101530_01.jpg"]


def test_type1_title_only_still_notifies(ctx: ArchiveContext, notifier: RecordingNotifier) -> None:
    entry = f.post(text="", title="Aviso", medias=[])
    process_type1(ctx, entry, notifier, "", ["Maria"])
    assert notifier.messages == ["Aviso"]


def test_file_mtime_is_entry_datetime(ctx: ArchiveContext, notifier: RecordingNotifier) -> None:
    process_type1(ctx, f.post(), notifier, "", ["Maria"])
    path = ctx.root / "Maria/2026/2026-03-10/2026-03-10_101530_01.jpg"
    assert datetime.fromtimestamp(os.path.getmtime(path)) == datetime(2026, 3, 10, 10, 15, 30)


def test_file_mtime_uses_school_timezone_not_machine_clock(
    config: Config, notifier: RecordingNotifier, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TZ", "UTC")  # like a container
    time.tzset()
    try:
        lisbon = ZoneInfo("Europe/Lisbon")
        ctx = ArchiveContext(
            root=config.archive_dir,
            strings=config.strings,
            documents=config.documents,
            timezone=lisbon,
        )
        for created, expected in (
            (
                "2026-03-10T10:15:30.000Z",
                datetime(2026, 3, 10, 10, 15, 30, tzinfo=lisbon),
            ),  # winter
            (
                "2026-07-10T10:15:30.000Z",
                datetime(2026, 7, 10, 10, 15, 30, tzinfo=lisbon),
            ),  # summer
        ):
            process_type1(ctx, f.post(created=created), notifier, "", ["Maria"])
            path = ctx.root / f"Maria/{created[:4]}/{created[:10]}/{created[:10]}_101530_01.jpg"
            assert datetime.fromtimestamp(os.path.getmtime(path), tz=lisbon) == expected
    finally:
        monkeypatch.delenv("TZ")
        time.tzset()


def test_display_date_wins_over_created_for_folder(
    ctx: ArchiveContext, notifier: RecordingNotifier
) -> None:
    entry = f.post(created="2026-03-12T09:00:00.000Z", display="2026-03-10T00:00:00Z")
    process_type1(ctx, entry, notifier, "", ["Maria"])
    # Folder/day from DisplayDate, time of day from CreatedOn.
    assert files_under(ctx.root) == ["Maria/2026/2026-03-10/2026-03-10_090000_01.jpg"]


# --- type 2 -----------------------------------------------------------------


def test_type2_routine_in_portuguese(ctx: ArchiveContext, notifier: RecordingNotifier) -> None:
    process_type2(ctx, f.load_fixture("type2_routine"), notifier, "[Maria] ", ["Maria"])
    assert notifier.messages == [
        "[Maria] Rotina Diária:\n"
        "\n🕐 Horário:\n  Entrada: 08:22 (Mãe)\n  Saída: 16:58 (Pai)\n"
        "\n🍴 Refeições:\n"
        "  Lanche da Manhã: Fruta — Comeu tudo\n  Bebida: Água\n"
        "  Almoço: Sopa e peixe — Comeu quase tudo\n"
        "  Lanche da Tarde: Iogurte — Comeu metade\n  Bebida: Leite\n"
        "\n🌙 Sestas:\n  12:15 — 14:24\n"
        "\n🚽 Higiene:\n  Xixi\n  Cocó\n"
        "\n🧩 Actividades:\n  Música\n  Jogo livre"
    ]
    assert files_under(ctx.root) == []


def test_type2_routine_in_english(tmp_path: Path, notifier: RecordingNotifier) -> None:
    cfg = make_config(language="en", archive_dir=str(tmp_path))
    ctx = ArchiveContext(root=cfg.archive_dir, strings=cfg.strings, documents=cfg.documents)
    process_type2(ctx, f.routine(), notifier, "[Maria] ", ["Maria"])
    text = notifier.messages[0]
    assert text.startswith("[Maria] Daily routine:")
    assert "  Morning snack: Fruta — Ate everything\n  Drink: Water" in text
    assert "🌙 Naps:" in text and "🧩 Activities:" in text


def test_type2_unknown_enum_values_pass_through(
    ctx: ArchiveContext, notifier: RecordingNotifier
) -> None:
    entry = f.routine()
    entry["Meals"] = [
        {"Title": "Supper", "Description": "Papa", "MealStatus": "Lots", "Drink": "Juice"}
    ]
    entry["Times"] = []
    entry["SleepTimes"] = [{"begin": None, "end": "2026-03-10T14:00:00Z"}]
    entry["Occurrences"] = ["Caiu no recreio"]
    process_type2(ctx, entry, notifier, "", ["Maria"])
    text = notifier.messages[0]
    assert "  Supper: Papa — Lots\n  Bebida: Juice" in text
    assert "  ? — 14:00" in text
    assert "⚠️ Ocorrências:\n  Caiu no recreio" in text


# --- type 3 -----------------------------------------------------------------


def test_type3_boxes_sorted_and_media_in_box_order(
    ctx: ArchiveContext, notifier: RecordingNotifier
) -> None:
    process_type3(ctx, f.load_fixture("type3_magazine"), notifier, "[Sala Girassóis] ", ["Maria"])
    assert notifier.messages == [
        "[Sala Girassóis] Dia da Primavera 🌸\n\nQueridas Famílias,\nPlantámos sementes no jardim."
    ]
    kind, items = notifier.calls[1]
    assert kind == "album"
    # The Media box lists m3, m2, m1 — that order is kept, and only the first has a caption.
    assert [os.path.basename(p) for p, _, _ in items] == [
        "2026-03-11_132127_01.mp4",
        "2026-03-11_132127_02.jpg",
        "2026-03-11_132127_03.jpg",
    ]
    assert [ext for _, ext, _ in items] == [".mp4", ".jpg", ".jpg"]
    assert [cap for _, _, cap in items] == ["11/03/2026 — Dia da Primavera 🌸", "", ""]


def test_type3_without_media_box_uses_flat_list(
    ctx: ArchiveContext, notifier: RecordingNotifier
) -> None:
    entry = f.magazine(boxes=[{"Order": 1, "Type": "Text", "Text": "Só texto", "Medias": None}])
    process_type3(ctx, entry, notifier, "", ["Maria"])
    assert len(files_under(ctx.root)) == 3


# --- type 5 -----------------------------------------------------------------


def test_type5_event_message_and_pdf_document_copy(
    ctx: ArchiveContext, notifier: RecordingNotifier
) -> None:
    process_type5(
        ctx,
        f.load_fixture("type5_event"),
        notifier,
        "[Maria & Tomás] ",
        ["Maria", "Tomás"],
        ["Maria", "Tomás"],
    )
    assert notifier.messages == [
        "[Maria & Tomás] 📅 Evento: Festa da Primavera\n"
        "Traga um chapéu de sol.\n"
        "Início: 20/03/2026 17:30\n"
        "Fim: 20/03/2026 18:30\n"
        "⚠️ Este evento requer confirmação de presença"
    ]
    assert notifier.calls[1][0] == "document"
    assert files_under(ctx.root) == [
        "Maria/2026/2026-03-12/2026-03-12_152710_01.pdf",
        "Maria/Documentos/2026-03-12 — Festa da Primavera.pdf",
        "Tomás/2026/2026-03-12/2026-03-12_152710_01.pdf",
        "Tomás/Documentos/2026-03-12 — Festa da Primavera.pdf",
    ]


def test_type5_video_call_and_no_rsvp(ctx: ArchiveContext, notifier: RecordingNotifier) -> None:
    entry = f.event(medias=[], description="")
    entry["RequiresAnswer"] = False
    entry["VideoCallId"] = "abc-123"
    process_type5(ctx, entry, notifier, "", ["Maria"])
    assert notifier.messages[0].endswith("🎥 Videochamada: abc-123")
    assert "⚠️" not in notifier.messages[0]


# --- documents --------------------------------------------------------------


def test_pdf_not_copied_to_documents_for_class_wide_entries(
    ctx: ArchiveContext, notifier: RecordingNotifier
) -> None:
    process_type5(ctx, f.event(), notifier, "", ["Maria"], doc_folders=[])
    assert files_under(ctx.root) == ["Maria/2026/2026-03-12/2026-03-12_152710_01.pdf"]


def test_menu_pdf_goes_to_subfolder(ctx: ArchiveContext, notifier: RecordingNotifier) -> None:
    entry = f.event(title="Ementa adaptada - semana 12")
    process_type5(ctx, entry, notifier, "", ["Maria"], ["Maria"])
    assert "Maria/Documentos/Ementas/2026-03-12 — Ementa adaptada - semana 12.pdf" in files_under(
        ctx.root
    )


def test_document_title_sanitised_and_duplicates_numbered(
    ctx: ArchiveContext, notifier: RecordingNotifier
) -> None:
    entry = f.event(title="Relatório 1.º/2.º período: avaliação")
    process_type5(ctx, entry, notifier, "", ["Maria"], ["Maria"])
    # Same title, different content: must not overwrite.
    other = f.event(
        entry_id="e5000000-0000-0000-0000-000000000002",
        title="Relatório 1.º/2.º período: avaliação",
    )
    other["Medias"][0]["Id"] = "m5000000-0000-0000-0000-000000000002"
    other["Medias"][0]["Url"] = f"{f.CDN}/bigger.pdf?sig=fake"
    handlers_download = handlers.download_file
    handlers.download_file = lambda url: b"%PDF-1.4 a different, longer document"  # type: ignore[assignment]
    try:
        other["CreatedOn"] = "2026-03-12T16:00:00.000Z"
        process_type5(ctx, other, notifier, "", ["Maria"], ["Maria"])
    finally:
        handlers.download_file = handlers_download
    docs = [p for p in files_under(ctx.root) if "/Documentos/" in p]
    assert docs == [
        "Maria/Documentos/2026-03-12 — Relatório 1.º-2.º período- avaliação (2).pdf",
        "Maria/Documentos/2026-03-12 — Relatório 1.º-2.º período- avaliação.pdf",
    ]


def test_titleless_pdf_named_from_message_body(
    ctx: ArchiveContext, notifier: RecordingNotifier
) -> None:
    entry = f.post(
        text="<p>Querida Família,</p><p>Segue o relatório de desenvolvimento do 1.º período.</p>",
        medias=[f.media("m1000000-0000-0000-0000-000000000009", ".pdf")],
    )
    process_type1(ctx, entry, notifier, "", ["Maria"], ["Maria"])
    assert (
        "Maria/Documentos/2026-03-10 — Segue o relatório de desenvolvimento do 1.º período..pdf"
        in files_under(ctx.root)
    )


def test_document_subfolder_matching(config: Config) -> None:
    assert document_subfolder("2026-01-01 — EMENTA de Natal", config.documents) == "Ementas"
    assert document_subfolder("2026-01-01 — Relatório", config.documents) is None


# --- media mechanics --------------------------------------------------------


def test_multi_folder_entries_download_once_and_copy(
    ctx: ArchiveContext, notifier: RecordingNotifier, no_network: dict[str, int]
) -> None:
    process_type1(ctx, f.post(), notifier, "", ["Maria", "Tomás"])
    assert files_under(ctx.root) == [
        "Maria/2026/2026-03-10/2026-03-10_101530_01.jpg",
        "Tomás/2026/2026-03-10/2026-03-10_101530_01.jpg",
    ]
    assert list(no_network.values()) == [1]


def test_existing_files_are_not_downloaded_again(
    ctx: ArchiveContext, notifier: RecordingNotifier, no_network: dict[str, int]
) -> None:
    process_type1(ctx, f.post(), notifier, "", ["Maria"])
    process_type1(ctx, f.post(), notifier, "", ["Maria"])
    assert list(no_network.values()) == [1]
    # Still notified both times: idempotency is the caller's job (state).
    assert len([c for c in notifier.calls if c[0] == "photo"]) == 2


def test_albums_split_in_tens(ctx: ArchiveContext, notifier: RecordingNotifier) -> None:
    medias = [
        f.media(f"m1000000-0000-0000-0000-0000000000{i:02d}", ".jpg", i) for i in range(1, 13)
    ]
    process_type1(ctx, f.post(medias=medias, text="Doze fotos"), notifier, "", ["Maria"])
    kinds = [k for k, _ in notifier.calls]
    assert kinds == ["message", "album", "album"]
    assert len(notifier.calls[1][1]) == 10 and len(notifier.calls[2][1]) == 2
    assert notifier.calls[1][1][0][2].startswith("10/03/2026 — Doze fotos")
    assert notifier.calls[2][1][0][2] == ""


def test_single_video_sent_as_video(ctx: ArchiveContext, notifier: RecordingNotifier) -> None:
    process_type1(
        ctx,
        f.post(medias=[f.media("m1000000-0000-0000-0000-000000000005", ".mp4")], text=""),
        notifier,
        "",
        ["Maria"],
    )
    assert notifier.calls[0][0] == "video"


def test_media_404_is_skipped_not_fatal(
    ctx: ArchiveContext, notifier: RecordingNotifier, monkeypatch: pytest.MonkeyPatch
) -> None:
    def gone(url: str) -> bytes:
        resp = requests.Response()
        resp.status_code = 404
        raise requests.HTTPError(response=resp)

    monkeypatch.setattr(handlers, "download_file", gone)
    process_type1(ctx, f.post(), notifier, "", ["Maria"])
    assert files_under(ctx.root) == []
    assert [k for k, _ in notifier.calls] == ["message"]


def test_other_http_errors_propagate(
    ctx: ArchiveContext, notifier: RecordingNotifier, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(url: str) -> bytes:
        resp = requests.Response()
        resp.status_code = 500
        raise requests.HTTPError(response=resp)

    monkeypatch.setattr(handlers, "download_file", boom)
    with pytest.raises(requests.HTTPError):
        process_type1(ctx, f.post(), notifier, "", ["Maria"])


def test_too_big_files_are_archived_only(
    ctx: ArchiveContext, notifier: RecordingNotifier, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(handlers, "TG_MAX_PHOTO", 1)
    monkeypatch.setattr(handlers, "TG_MAX_FILE", 1)
    process_type5(ctx, f.event(), notifier, "", ["Maria"])
    process_type1(ctx, f.post(text=""), notifier, "", ["Maria"])
    assert [k for k, _ in notifier.calls] == ["message"]
    assert len(files_under(ctx.root)) == 2


def test_exiftool_invoked_when_available(
    ctx: ArchiveContext, notifier: RecordingNotifier, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []

    class Result:
        returncode = 0
        stderr = ""

    monkeypatch.setattr(handlers.shutil, "which", lambda name: "/usr/bin/exiftool")
    monkeypatch.setattr(
        handlers.subprocess, "run", lambda args, **kw: calls.append(args) or Result()
    )
    medias = [
        f.media("m1000000-0000-0000-0000-000000000001", ".jpg"),
        f.media("m1000000-0000-0000-0000-000000000002", ".mp4", 2),
    ]
    process_type1(ctx, f.post(medias=medias, text="Legenda"), notifier, "", ["Maria"])
    assert len(calls) == 2  # photos batch, videos batch
    photo_args, video_args = calls
    assert "-AllDates=2026:03:10 10:15:30" in photo_args
    assert any(a.startswith("-ImageDescription=10/03/2026 — Legenda") for a in photo_args)
    assert not any(a.startswith("-ImageDescription") for a in video_args)


def test_unknown_type_warns_and_notifies(
    ctx: ArchiveContext, notifier: RecordingNotifier, caplog: pytest.LogCaptureFixture
) -> None:
    process_unknown(ctx, f.load_fixture("type9_unknown"), notifier, "[Maria] ", ["Maria"])
    assert notifier.messages == [
        "[Maria] [Aviso] Entrada de tipo desconhecido (9). Verifica os logs."
    ]
    assert "Unknown entry type 9" in caplog.text


def test_process_medias_with_unparseable_dates(
    ctx: ArchiveContext, notifier: RecordingNotifier
) -> None:
    entry = f.post(created="garbage", display="garbage")
    process_medias(ctx, entry, entry["Medias"], notifier, ["Maria"])
    assert files_under(ctx.root) == ["Maria/unkn/unknown-date/unknown-date_000000_01.jpg"]
