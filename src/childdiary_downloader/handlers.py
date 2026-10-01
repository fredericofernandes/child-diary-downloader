"""Per-entry-type processing: text to the notifier, files to the archive.

Entry types seen in the API: 1 = post with photos/text, 2 = daily routine,
3 = "magazine" post made of ordered Boxes, 5 = event/invitation.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
from contextlib import ExitStack
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

from childdiary_downloader.api import download_file
from childdiary_downloader.config import DocumentsConfig, Routing
from childdiary_downloader.i18n import Strings
from childdiary_downloader.notify import MediaItem, Notifier

log = logging.getLogger(__name__)

Entry = dict[str, Any]

PHOTO_EXTS = {".jpg", ".jpeg", ".png"}
VIDEO_EXTS = {".mp4"}
UNKNOWN_FOLDER = "__unknown__"

# Telegram Bot API upload limits: 10 MB photos, 50 MB videos/documents.
TG_MAX_PHOTO = 10 * 1024 * 1024
TG_MAX_FILE = 45 * 1024 * 1024  # margin below the hard 50 MB limit
ALBUM_SIZE = 10


@dataclass(frozen=True)
class ArchiveContext:
    """Everything a handler needs besides the entry itself."""

    root: Path
    strings: Strings
    documents: DocumentsConfig


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------


def strip_html(text: str) -> str:
    """Drop HTML tags and decode the handful of entities the app emits."""
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<p[^>]*>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"</p>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&nbsp;", " ").replace("&#39;", "'")
    return text.strip()


def summarize_for_filename(text: str, greeting_pattern: str) -> str:
    """First substantive line of a message, used to name title-less PDFs.

    Skips greeting lines ("Dear families,", "Olá Pais! 💕"): short lines, or
    lines ending in a comma/colon, or matching the locale's greeting pattern.
    Falls back to the first non-empty line.
    """
    greeting = re.compile(greeting_pattern, re.IGNORECASE)
    lines = [line.strip() for line in text.splitlines()]
    for line in lines:
        if len(line) >= 15 and not line.endswith((",", ":")) and not greeting.match(line):
            return line[:60].strip()
    for line in lines:
        if line:
            return line[:60]
    return ""


def parse_dt(s: str) -> datetime:
    """ISO 8601 with or without fractional seconds. API timestamps carry a
    "Z" but are actually the school's local time, so they stay naive."""
    for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    raise ValueError(f"Cannot parse datetime: {s!r}")


# ---------------------------------------------------------------------------
# Recipients and routing
# ---------------------------------------------------------------------------


def _route_to_children(targets: list[str], entry: Entry, routing: Routing) -> list[str]:
    """Drop children who were not enrolled yet on the entry's date (child_since)."""
    date = (entry.get("CreatedOn") or "")[:10]
    since = routing.child_since
    kept = [c for c in targets if not since.get(c) or date >= since[c]]
    return kept or targets


def get_entry_info(
    entry: Entry,
    children: dict[str, str],
    group_to_child: dict[str, str] | None = None,
    routing: Routing | None = None,
    strings: Strings | None = None,
) -> tuple[list[str], str, list[str]]:
    """Return (our_children_names, message_prefix, archive_folders).

    Group/school posts are routed into the children's own folders: first via
    the explicit ``routing`` map (wins, it is stable across runs), then via
    the group->child map discovered from the children's own entries. Unmapped
    groups fall back to a folder named after the group, with a warning.
    """
    group_to_child = group_to_child or {}
    routing = routing or Routing()
    group_fallback = strings.group_fallback if strings else "Group"
    school_fallback = strings.school_fallback if strings else "School"

    names = [
        children[str(item.get("Id"))]
        for item in entry.get("For", [])
        if item.get("Type") == "Child" and item.get("Id") in children
    ]
    if names:
        unique = list(dict.fromkeys(names))
        prefix = "[" + " & ".join(unique) + "] "
        return names, prefix, unique  # one folder per child

    for item in entry.get("For", []):
        if item.get("Type") == "Group":
            gid = item.get("Id")
            desc = item.get("Description", group_fallback)
            targets = routing.groups.get(desc)
            if targets:
                return [], f"[{desc}] ", _route_to_children(targets, entry, routing)
            child_name = group_to_child.get(str(gid)) if gid else None
            if child_name:
                return [], f"[{desc}] ", [child_name]
            log.warning(
                "Unmapped group %r: archiving in its own folder; add it to routing.groups.", desc
            )
            return [], f"[{desc}] ", [desc]
        if item.get("Type") == "Instance":
            instance_name = entry.get("InstanceName", school_fallback)
            targets = routing.instances.get(instance_name)
            if targets:
                return [], f"[{instance_name}] ", _route_to_children(targets, entry, routing)
            log.warning(
                "Unmapped school %r: archiving in its own folder; add it to routing.instances.",
                instance_name,
            )
            return [], f"[{instance_name}] ", [instance_name]

    return [], "", [UNKNOWN_FOLDER]


def _raw_date(entry: Entry) -> str:
    return str(entry.get("DisplayDate") or entry.get("CreatedOn") or "")


def _caption_date(entry: Entry, strings: Strings) -> str:
    try:
        return datetime.strptime(_raw_date(entry)[:10], "%Y-%m-%d").strftime(
            strings.caption_date_format
        )
    except ValueError:
        return ""


def _archive_date(entry: Entry) -> str:
    """YYYY-MM-DD for the archive folder."""
    try:
        return datetime.strptime(_raw_date(entry)[:10], "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        return "unknown-date"


# ---------------------------------------------------------------------------
# Handlers per entry type
# ---------------------------------------------------------------------------


def process_type1(
    ctx: ArchiveContext,
    entry: Entry,
    notifier: Notifier,
    prefix: str,
    folders: list[str],
    doc_folders: list[str] | None = None,
) -> None:
    """Photo/text post."""
    title = entry.get("Title") or ""
    body = strip_html(entry.get("Text", "") or "")
    text = "\n\n".join(filter(None, [title, body]))
    if text:
        notifier.send_message(prefix + text)

    date_str = _caption_date(entry, ctx.strings)
    caption = f"{date_str} — {text[:200]}" if text else date_str
    process_medias(
        ctx,
        entry,
        entry.get("Medias", []),
        notifier,
        folders,
        caption,
        doc_folders=doc_folders,
        doc_title=title or summarize_for_filename(body, ctx.strings.greeting_pattern),
    )


def process_type2(
    ctx: ArchiveContext,
    entry: Entry,
    notifier: Notifier,
    prefix: str,
    folders: list[str],
    doc_folders: list[str] | None = None,
) -> None:
    """Daily routine."""
    s = ctx.strings
    parts = [prefix + s.daily_routine]

    if entry.get("Times"):
        lines = ["", s.schedule]
        for t in entry["Times"]:
            for key, label in (("TimeIn", s.check_in), ("TimeOut", s.check_out)):
                if t.get(key):
                    who = t.get(f"{key}FamilyMember", "")
                    line = f"  {label}: {parse_dt(t[key]).strftime('%H:%M')}"
                    if who:
                        line += f" ({who})"
                    lines.append(line)
        parts.append("\n".join(lines))

    if entry.get("Meals"):
        lines = ["", s.meals]
        for m in entry["Meals"]:
            title = s.meal_titles.get(m.get("Title", ""), m.get("Title", ""))
            status = s.meal_status.get(m.get("MealStatus", ""), m.get("MealStatus", ""))
            drink = s.drink_names.get(m.get("Drink", ""), m.get("Drink", ""))
            line = f"  {title}: {m.get('Description', '')}"
            if status:
                line += f" — {status}"
            if drink:
                line += f"\n  {s.drink}: {drink}"
            lines.append(line)
        parts.append("\n".join(lines))

    if entry.get("SleepTimes"):
        lines = ["", s.naps]
        for nap in entry["SleepTimes"]:
            begin = parse_dt(nap["begin"]).strftime("%H:%M") if nap.get("begin") else "?"
            end = parse_dt(nap["end"]).strftime("%H:%M") if nap.get("end") else "?"
            lines.append(f"  {begin} — {end}")
        parts.append("\n".join(lines))

    if entry.get("ToiletTimes"):
        parts.append(
            "\n".join(["", s.hygiene] + ["  " + t.get("type", "") for t in entry["ToiletTimes"]])
        )

    if entry.get("Activities"):
        parts.append(
            "\n".join(
                ["", s.activities] + ["  " + a.get("Description", "") for a in entry["Activities"]]
            )
        )

    if entry.get("Occurrences"):
        parts.append("\n".join(["", s.occurrences] + ["  " + str(o) for o in entry["Occurrences"]]))

    notifier.send_message("\n".join(parts))
    process_medias(ctx, entry, entry.get("Medias", []), notifier, folders, doc_folders=doc_folders)


def process_type3(
    ctx: ArchiveContext,
    entry: Entry,
    notifier: Notifier,
    prefix: str,
    folders: list[str],
    doc_folders: list[str] | None = None,
) -> None:
    """ "Magazine" post made of ordered Boxes."""
    boxes = sorted(entry.get("Boxes", []), key=lambda b: b.get("Order", 0))

    parts = [
        strip_html(box.get("Text") or "")
        for box in boxes
        if box.get("Type") in ("Title", "Text") and box.get("Text")
    ]
    message = "\n\n".join(filter(None, parts))
    if message:
        notifier.send_message(prefix + message)

    # Media list in display order (Boxes), falling back to the flat list.
    media_lookup = {m["Id"]: m for m in entry.get("Medias", [])}
    seen_ids: set[str] = set()
    ordered_medias = []
    for box in boxes:
        if box.get("Type") == "Media" and box.get("Medias"):
            for mid in box["Medias"]:
                if mid in media_lookup and mid not in seen_ids:
                    ordered_medias.append(media_lookup[mid])
                    seen_ids.add(mid)
    if not ordered_medias:
        ordered_medias = entry.get("Medias", [])

    date_str = _caption_date(entry, ctx.strings)
    title = next(
        (
            strip_html(b.get("Text") or "")
            for b in boxes
            if b.get("Type") == "Title" and b.get("Text")
        ),
        "",
    )
    caption = f"{date_str} — {title}" if title else date_str
    process_medias(
        ctx,
        entry,
        ordered_medias,
        notifier,
        folders,
        caption,
        doc_folders=doc_folders,
        doc_title=title or summarize_for_filename(message, ctx.strings.greeting_pattern),
    )


def process_type5(
    ctx: ArchiveContext,
    entry: Entry,
    notifier: Notifier,
    prefix: str,
    folders: list[str],
    doc_folders: list[str] | None = None,
) -> None:
    """Event / invitation."""
    s = ctx.strings
    title = entry.get("Title") or ""
    description = entry.get("Description") or ""
    start = entry.get("StartDateTime") or ""
    end = entry.get("EndDateTime") or ""
    date_fmt = f"{s.caption_date_format} %H:%M"

    lines = [f"{s.event}: {title}" if title else s.event]
    if description:
        lines.append(description)
    if start:
        lines.append(f"{s.event_start}: {parse_dt(start).strftime(date_fmt)}")
    if end:
        lines.append(f"{s.event_end}: {parse_dt(end).strftime(date_fmt)}")
    if entry.get("RequiresAnswer"):
        lines.append(s.event_requires_answer)
    if entry.get("VideoCallId"):
        lines.append(f"{s.video_call}: {entry['VideoCallId']}")

    notifier.send_message(prefix + "\n".join(lines))

    date_str = _caption_date(entry, s)
    caption = f"{date_str} — {title}" if title else date_str
    process_medias(
        ctx,
        entry,
        entry.get("Medias", []),
        notifier,
        folders,
        caption,
        doc_folders=doc_folders,
        doc_title=title or summarize_for_filename(description, s.greeting_pattern),
    )


def process_unknown(
    ctx: ArchiveContext,
    entry: Entry,
    notifier: Notifier,
    prefix: str,
    folders: list[str],
    doc_folders: list[str] | None = None,
) -> None:
    entry_type = entry.get("Type", "?")
    log.warning(
        "Unknown entry type %s: %s", entry_type, json.dumps(entry, indent=2, ensure_ascii=False)
    )
    notifier.send_message(prefix + ctx.strings.unknown_entry_type.format(type=entry_type))


HANDLERS = {1: process_type1, 2: process_type2, 3: process_type3, 5: process_type5}


# ---------------------------------------------------------------------------
# Media
# ---------------------------------------------------------------------------


def _entry_datetime(entry: Entry) -> datetime:
    """Timestamp for file names/EXIF: DisplayDate's day with CreatedOn's time."""
    try:
        created = parse_dt(entry.get("CreatedOn", ""))
    except ValueError:
        created = datetime(2000, 1, 1)
    try:
        day = datetime.strptime(_archive_date(entry), "%Y-%m-%d")
        return created.replace(year=day.year, month=day.month, day=day.day)
    except ValueError:
        return created


def _same_file(a: str, b: str) -> bool:
    try:
        return os.path.getsize(a) == os.path.getsize(b)
    except OSError:
        return False


def document_subfolder(title: str, documents: DocumentsConfig) -> str | None:
    """Subfolder of the documents folder whose keywords match the title, if any."""
    lowered = title.lower()
    for folder, keywords in documents.subfolders.items():
        if any(kw in lowered for kw in keywords):
            return folder
    return None


def _save_document_copy(
    ctx: ArchiveContext, pdf_path: str, doc_folders: list[str], date_str: str, title: str
) -> None:
    """Copy a child-addressed PDF into <Child>/<Documents>/ with a readable name."""
    title = re.sub(r"[/\\:]", "-", strip_html(title)).strip()[:80]
    base = f"{date_str} — {title}" if title else date_str
    subfolder = document_subfolder(base, ctx.documents)
    for child in doc_folders:
        docs_dir = os.path.join(ctx.root, child, ctx.documents.folder)
        if subfolder:
            docs_dir = os.path.join(docs_dir, subfolder)
        os.makedirs(docs_dir, exist_ok=True)
        dest = os.path.join(docs_dir, base + ".pdf")
        n = 2
        while os.path.exists(dest) and not _same_file(pdf_path, dest):
            dest = os.path.join(docs_dir, f"{base} ({n}).pdf")
            n += 1
        if not os.path.exists(dest):
            shutil.copy2(pdf_path, dest)
            log.info("Document saved: %s", dest)


def _too_big_for_telegram(path: str, ext: str) -> bool:
    limit = TG_MAX_PHOTO if ext.lower() in PHOTO_EXTS else TG_MAX_FILE
    try:
        return os.path.getsize(path) > limit
    except OSError:
        return False


def _embed_metadata(paths: list[str], dt: datetime, description: str) -> None:
    """Write EXIF dates (and the description, for photos) with exiftool.
    Best effort: without exiftool only the file mtime carries the date."""
    if not paths:
        return
    if shutil.which("exiftool") is None:
        log.warning("exiftool not found: files saved without EXIF metadata.")
        return
    stamp = dt.strftime("%Y:%m:%d %H:%M:%S")
    args = ["exiftool", "-overwrite_original", "-q", f"-AllDates={stamp}"]
    if description and os.path.splitext(paths[0])[1].lower() in PHOTO_EXTS:
        args.append(f"-ImageDescription={description[:500]}")
    result = subprocess.run(args + paths, capture_output=True, text=True)
    if result.returncode != 0:
        log.warning("exiftool failed for %d file(s): %s", len(paths), result.stderr.strip())


def process_medias(
    ctx: ArchiveContext,
    entry: Entry,
    medias: list[dict[str, Any]],
    notifier: Notifier,
    folders: list[str],
    caption: str = "",
    doc_folders: list[str] | None = None,
    doc_title: str = "",
) -> None:
    """Download, archive on disk and hand the media to the notifier.

    Files are named <date>_<time>_<NN><ext> (NN = position in the post) and
    saved under <folder>/<year>/<date>/. EXIF dates, description and mtime
    are set to the entry date so photo apps sort the archive correctly. Each
    file is saved to every folder in ``folders`` (one download, then copies).
    Photos and videos go out in albums of up to ALBUM_SIZE; PDFs and unknown
    formats as documents.

    PDFs from entries addressed exclusively to our children (``doc_folders``)
    also get a readable-named copy in <Child>/<Documents>/, where development
    reports, adapted menus and the like are easy to find later.
    """
    photos_videos: list[tuple[str, str]] = []  # (primary_path, ext)

    entry_dt = _entry_datetime(entry)
    date_str = _archive_date(entry)
    year = date_str[:4]
    primary_dir = os.path.join(ctx.root, folders[0], year, date_str)

    new_photos: list[str] = []
    new_videos: list[str] = []
    all_paths: list[str] = []

    for idx, media in enumerate(medias, start=1):
        ext = media.get("Extension", "")
        file_name = f"{date_str}_{entry_dt.strftime('%H%M%S')}_{idx:02d}{ext}"
        os.makedirs(primary_dir, exist_ok=True)
        primary_path = os.path.join(primary_dir, file_name)

        if not os.path.exists(primary_path):
            try:
                content = download_file(media["Url"])
            except requests.HTTPError as e:
                if e.response is not None and e.response.status_code == 404:
                    # Blob deleted on the school's CDN: gone for good, keep the entry.
                    log.warning("Media gone from server (404), skipping: %s%s", media["Id"], ext)
                    continue
                raise
            with open(primary_path, "wb") as out:
                out.write(content)
            log.info("Saved %s", primary_path)
            if ext.lower() in PHOTO_EXTS:
                new_photos.append(primary_path)
            elif ext.lower() in VIDEO_EXTS:
                new_videos.append(primary_path)
        else:
            log.debug("Already exists: %s", primary_path)

        all_paths.append(primary_path)

        if ext.lower() == ".pdf" and doc_folders and os.path.exists(primary_path):
            _save_document_copy(ctx, primary_path, doc_folders, date_str, doc_title)

        if ext in PHOTO_EXTS or ext in VIDEO_EXTS:
            if _too_big_for_telegram(primary_path, ext):
                log.warning("Too big for Telegram, archived only: %s", primary_path)
            else:
                photos_videos.append((primary_path, ext))

    # EXIF on freshly downloaded files, then mtimes and copies to the other folders.
    _embed_metadata(new_photos, entry_dt, caption)
    _embed_metadata(new_videos, entry_dt, "")
    mtime = entry_dt.timestamp()
    for primary_path in all_paths:
        os.utime(primary_path, (mtime, mtime))
        file_name = os.path.basename(primary_path)
        for extra_folder in folders[1:]:
            extra_dir = os.path.join(ctx.root, extra_folder, year, date_str)
            os.makedirs(extra_dir, exist_ok=True)
            extra_path = os.path.join(extra_dir, file_name)
            if not os.path.exists(extra_path):
                shutil.copy2(primary_path, extra_path)
                log.info("Copied to %s", extra_path)

    # Non photo/video files (PDFs etc.) go as documents.
    for primary_path in all_paths:
        ext = os.path.splitext(primary_path)[1]
        if ext not in PHOTO_EXTS and ext not in VIDEO_EXTS:
            if _too_big_for_telegram(primary_path, ext):
                log.warning("Too big for Telegram, archived only: %s", primary_path)
                continue
            with open(primary_path, "rb") as doc:
                notifier.send_document(doc)

    # Photos/videos in albums.
    for i in range(0, len(photos_videos), ALBUM_SIZE):
        batch = photos_videos[i : i + ALBUM_SIZE]
        batch_caption = caption if i == 0 else ""

        if len(batch) == 1:
            dest_path, ext = batch[0]
            with open(dest_path, "rb") as single:
                if ext in PHOTO_EXTS:
                    notifier.send_photo(single, caption=batch_caption)
                else:
                    notifier.send_video(single, caption=batch_caption)
        else:
            with ExitStack() as stack:
                handles = [stack.enter_context(open(p, "rb")) for p, _ in batch]
                items: list[MediaItem] = [
                    (handle, ext, batch_caption if idx == 0 else "")
                    for idx, ((_, ext), handle) in enumerate(zip(batch, handles, strict=True))
                ]
                notifier.send_media_group(items)
