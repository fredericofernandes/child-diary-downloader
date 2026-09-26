"""Processamento de cada tipo de entrada: texto para o notificador, ficheiros
para o arquivo em disco.

Tipos conhecidos da API: 1 = post com fotos/texto, 2 = rotina diária,
3 = post "revista" com Boxes, 5 = evento/convite.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
from contextlib import ExitStack
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

import requests

from childdiary_downloader.api import download_file

log = logging.getLogger(__name__)

Entry = dict[str, Any]

MEAL_TITLES = {
    "MorningBreak": "Lanche da Manhã",
    "Lunch": "Almoço",
    "Dinner": "Lanche da Tarde",
    "Breakfast": "Pequeno-Almoço",
}
MEAL_STATUS = {
    "All": "Comeu tudo",
    "Most": "Comeu quase tudo",
    "Half": "Comeu metade",
    "Some": "Comeu pouco",
    "None": "Não comeu",
}
DRINK_NAMES = {
    "Water": "Água",
    "Milk": "Leite",
    "Tea": "Chá",
}

PHOTO_EXTS = {".jpg", ".jpeg", ".png"}
VIDEO_EXTS = {".mp4"}

DOCUMENTS_FOLDER = "Documentos"
MENUS_FOLDER = "Ementas"
MENU_KEYWORD = "ementa"
UNKNOWN_FOLDER = "__unknown__"


class Notifier(Protocol):
    def send_document(self, fh: Any, caption: str = "") -> None: ...
    def send_photo(self, fh: Any, caption: str = "") -> None: ...
    def send_video(self, fh: Any, caption: str = "") -> None: ...
    def send_message(self, text: str) -> None: ...
    def send_media_group(self, items: list[Any]) -> None: ...


# ---------------------------------------------------------------------------
# Texto
# ---------------------------------------------------------------------------


def strip_html(text: str) -> str:
    """Remove tags HTML e descodifica entidades básicas."""
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<p[^>]*>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"</p>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&nbsp;", " ").replace("&#39;", "'")
    return text.strip()


def summarize_for_filename(text: str) -> str:
    """Primeira linha com substância de uma mensagem, para dar nome a
    documentos sem título. Salta saudações ("Querida Família,", "Olá Pais! 💕"),
    linhas curtas ou que acabam em vírgula/dois pontos.
    """
    greeting = re.compile(r"^(olá|ola|querid|car[oa]s?\b|bom dia|boa tarde)", re.IGNORECASE)
    lines = [line.strip() for line in text.splitlines()]
    for line in lines:
        if len(line) >= 15 and not line.endswith((",", ":")) and not greeting.match(line):
            return line[:60].strip()
    for line in lines:
        if line:
            return line[:60]
    return ""


def parse_dt(s: str) -> datetime:
    """ISO 8601 com ou sem fracções de segundo. Os timestamps da API trazem
    um "Z" mas são hora local de Portugal, por isso ficam naive."""
    for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    raise ValueError(f"Cannot parse datetime: {s!r}")


# ---------------------------------------------------------------------------
# Destinatários e routing
# ---------------------------------------------------------------------------


def _route_to_children(targets: list[str], entry: Entry, routing: dict[str, Any]) -> list[str]:
    """Remove crianças que ainda não tinham entrado na data da entrada (child_since)."""
    date = (entry.get("CreatedOn") or "")[:10]
    since = routing.get("child_since", {})
    kept = [c for c in targets if not since.get(c) or date >= since[c]]
    return kept or targets


def get_entry_info(
    entry: Entry,
    children: dict[str, str],
    group_to_child: dict[str, str] | None = None,
    routing: dict[str, Any] | None = None,
) -> tuple[list[str], str, list[str]]:
    """Devolve (nomes_das_nossas_crianças, prefixo_da_mensagem, pastas_de_arquivo).

    Posts de sala/escola são encaminhados para as pastas das crianças: primeiro
    pelo mapa ``routing`` explícito (ganha, é estável), depois pelo mapa
    grupo->criança descoberto nas próprias entradas. Grupos sem mapeamento
    caem numa pasta com o nome do grupo, com aviso para classificar.
    """
    if group_to_child is None:
        group_to_child = {}
    if routing is None:
        routing = {}

    names = [
        children[str(item.get("Id"))]
        for item in entry.get("For", [])
        if item.get("Type") == "Child" and item.get("Id") in children
    ]
    if names:
        unique = list(dict.fromkeys(names))
        prefix = "[" + " & ".join(unique) + "] "
        return names, prefix, unique  # cada criança tem a sua pasta

    for item in entry.get("For", []):
        if item.get("Type") == "Group":
            gid = item.get("Id")
            desc = item.get("Description", "Grupo")
            targets = routing.get("groups", {}).get(desc)
            if targets:
                return [], f"[{desc}] ", _route_to_children(targets, entry, routing)
            child_name = group_to_child.get(str(gid)) if gid else None
            if child_name:
                return [], f"[{desc}] ", [child_name]
            log.warning(
                "Grupo não mapeado %r: a arquivar em pasta própria; "
                "adiciona-o a routing.groups no config.yaml.",
                desc,
            )
            return [], f"[{desc}] ", [desc]
        if item.get("Type") == "Instance":
            instance_name = entry.get("InstanceName", "Escola")
            targets = routing.get("instances", {}).get(instance_name)
            if targets:
                return [], f"[{instance_name}] ", _route_to_children(targets, entry, routing)
            log.warning(
                "Escola não mapeada %r: a arquivar em pasta própria; "
                "adiciona-a a routing.instances no config.yaml.",
                instance_name,
            )
            return [], f"[{instance_name}] ", [instance_name]

    return [], "", [UNKNOWN_FOLDER]


def _entry_date_str(entry: Entry) -> str:
    raw = str(entry.get("DisplayDate") or entry.get("CreatedOn") or "")
    try:
        return datetime.strptime(raw[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
    except (ValueError, TypeError):
        return ""


def _archive_date(entry: Entry) -> str:
    """AAAA-MM-DD para a pasta de arquivo."""
    raw = str(entry.get("DisplayDate") or entry.get("CreatedOn") or "")
    try:
        return datetime.strptime(raw[:10], "%Y-%m-%d").strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return "unknown-date"


# ---------------------------------------------------------------------------
# Handlers por tipo
# ---------------------------------------------------------------------------


def process_type1(
    archive_root: Path,
    entry: Entry,
    tg: Notifier,
    prefix: str,
    folders: list[str],
    doc_folders: list[str] | None = None,
) -> None:
    """Post de fotos/texto."""
    title = entry.get("Title") or ""
    body = strip_html(entry.get("Text", "") or "")
    text = "\n\n".join(filter(None, [title, body]))
    if text:
        tg.send_message(prefix + text)

    date_str = _entry_date_str(entry)
    caption = f"{date_str} — {text[:200]}" if text else date_str
    process_medias(
        archive_root,
        entry,
        entry.get("Medias", []),
        tg,
        folders,
        caption,
        doc_folders=doc_folders,
        doc_title=title or summarize_for_filename(body),
    )


def process_type2(
    archive_root: Path,
    entry: Entry,
    tg: Notifier,
    prefix: str,
    folders: list[str],
    doc_folders: list[str] | None = None,
) -> None:
    """Rotina diária."""
    parts = [prefix + "Rotina Diária:"]

    if entry.get("Times"):
        times_lines = ["", "🕐 Horário:"]
        for t in entry["Times"]:
            if t.get("TimeIn"):
                who = t.get("TimeInFamilyMember", "")
                line = f"  Entrada: {parse_dt(t['TimeIn']).strftime('%H:%M')}"
                if who:
                    line += f" ({who})"
                times_lines.append(line)
            if t.get("TimeOut"):
                who = t.get("TimeOutFamilyMember", "")
                line = f"  Saída: {parse_dt(t['TimeOut']).strftime('%H:%M')}"
                if who:
                    line += f" ({who})"
                times_lines.append(line)
        parts.append("\n".join(times_lines))

    if entry.get("Meals"):
        meal_lines = ["", "🍴 Refeições:"]
        for m in entry["Meals"]:
            title_pt = MEAL_TITLES.get(m.get("Title", ""), m.get("Title", ""))
            status_pt = MEAL_STATUS.get(m.get("MealStatus", ""), m.get("MealStatus", ""))
            drink_pt = DRINK_NAMES.get(m.get("Drink", ""), m.get("Drink", ""))
            desc = m.get("Description", "")
            line = f"  {title_pt}: {desc}"
            if status_pt:
                line += f" — {status_pt}"
            if drink_pt:
                line += f"\n  Bebida: {drink_pt}"
            meal_lines.append(line)
        parts.append("\n".join(meal_lines))

    if entry.get("SleepTimes"):
        sleep_lines = ["", "🌙 Sestas:"]
        for s in entry["SleepTimes"]:
            begin = parse_dt(s["begin"]).strftime("%H:%M") if s.get("begin") else "?"
            end = parse_dt(s["end"]).strftime("%H:%M") if s.get("end") else "?"
            sleep_lines.append(f"  {begin} — {end}")
        parts.append("\n".join(sleep_lines))

    if entry.get("ToiletTimes"):
        toilet_lines = ["", "🚽 Higiene:"]
        for t in entry["ToiletTimes"]:
            toilet_lines.append("  " + t.get("type", ""))
        parts.append("\n".join(toilet_lines))

    if entry.get("Activities"):
        act_lines = ["", "🧩 Actividades:"]
        for a in entry["Activities"]:
            act_lines.append("  " + a.get("Description", ""))
        parts.append("\n".join(act_lines))

    if entry.get("Occurrences"):
        occ_lines = ["", "⚠️ Ocorrências:"]
        for o in entry["Occurrences"]:
            occ_lines.append("  " + str(o))
        parts.append("\n".join(occ_lines))

    tg.send_message("\n".join(parts))
    process_medias(
        archive_root, entry, entry.get("Medias", []), tg, folders, doc_folders=doc_folders
    )


def process_type3(
    archive_root: Path,
    entry: Entry,
    tg: Notifier,
    prefix: str,
    folders: list[str],
    doc_folders: list[str] | None = None,
) -> None:
    """Post "revista" com Boxes ordenadas."""
    boxes = sorted(entry.get("Boxes", []), key=lambda b: b.get("Order", 0))

    parts = [
        strip_html(box.get("Text") or "")
        for box in boxes
        if box.get("Type") in ("Title", "Text") and box.get("Text")
    ]
    message = "\n\n".join(filter(None, parts))
    if message:
        tg.send_message(prefix + message)

    # Lista de medias pela ordem de apresentação das Boxes.
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

    date_str = _entry_date_str(entry)
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
        archive_root,
        entry,
        ordered_medias,
        tg,
        folders,
        caption,
        doc_folders=doc_folders,
        doc_title=title or summarize_for_filename(message),
    )


def process_type5(
    archive_root: Path,
    entry: Entry,
    tg: Notifier,
    prefix: str,
    folders: list[str],
    doc_folders: list[str] | None = None,
) -> None:
    """Evento / convite."""
    title = entry.get("Title") or ""
    description = entry.get("Description") or ""
    start = entry.get("StartDateTime") or ""
    end = entry.get("EndDateTime") or ""

    lines = ["📅 Evento: " + title] if title else ["📅 Evento"]
    if description:
        lines.append(description)
    if start:
        lines.append("Início: " + parse_dt(start).strftime("%d/%m/%Y %H:%M"))
    if end:
        lines.append("Fim: " + parse_dt(end).strftime("%d/%m/%Y %H:%M"))
    if entry.get("RequiresAnswer"):
        lines.append("⚠️ Este evento requer confirmação de presença")
    if entry.get("VideoCallId"):
        lines.append(f"🎥 Videochamada: {entry['VideoCallId']}")

    tg.send_message(prefix + "\n".join(lines))

    date_str = _entry_date_str(entry)
    caption = f"{date_str} — {title}" if title else date_str
    process_medias(
        archive_root,
        entry,
        entry.get("Medias", []),
        tg,
        folders,
        caption,
        doc_folders=doc_folders,
        doc_title=title or summarize_for_filename(description),
    )


def process_unknown(
    archive_root: Path,
    entry: Entry,
    tg: Notifier,
    prefix: str,
    folders: list[str],
    doc_folders: list[str] | None = None,
) -> None:
    entry_type = entry.get("Type", "?")
    log.warning(
        "Tipo de entrada desconhecido %s: %s",
        entry_type,
        json.dumps(entry, indent=2, ensure_ascii=False),
    )
    tg.send_message(
        prefix + f"[Aviso] Entrada de tipo desconhecido ({entry_type}). Verifica os logs."
    )


HANDLERS = {1: process_type1, 2: process_type2, 3: process_type3, 5: process_type5}


# ---------------------------------------------------------------------------
# Medias
# ---------------------------------------------------------------------------


def _entry_datetime(entry: Entry) -> datetime:
    """Timestamp para nomes de ficheiro/EXIF: dia do DisplayDate + hora do CreatedOn."""
    try:
        created = parse_dt(entry.get("CreatedOn", ""))
    except ValueError:
        created = datetime(2000, 1, 1)
    date_part = _archive_date(entry)
    try:
        day = datetime.strptime(date_part, "%Y-%m-%d")
        return created.replace(year=day.year, month=day.month, day=day.day)
    except ValueError:
        return created


def _same_file(a: str, b: str) -> bool:
    try:
        return os.path.getsize(a) == os.path.getsize(b)
    except OSError:
        return False


def _save_document_copy(
    archive_root: Path, pdf_path: str, doc_folders: list[str], date_str: str, title: str
) -> None:
    """Copia um PDF dirigido à criança para <Criança>/Documentos/ com nome legível."""
    title = re.sub(r"[/\\:]", "-", strip_html(title)).strip()[:80]
    base = f"{date_str} — {title}" if title else date_str
    for child in doc_folders:
        docs_dir = os.path.join(archive_root, child, DOCUMENTS_FOLDER)
        if MENU_KEYWORD in base.lower():
            docs_dir = os.path.join(docs_dir, MENUS_FOLDER)
        os.makedirs(docs_dir, exist_ok=True)
        dest = os.path.join(docs_dir, base + ".pdf")
        n = 2
        while os.path.exists(dest) and not _same_file(pdf_path, dest):
            dest = os.path.join(docs_dir, f"{base} ({n}).pdf")
            n += 1
        if not os.path.exists(dest):
            shutil.copy2(pdf_path, dest)
            log.info("Documento guardado: %s", dest)


# Limites da Bot API do Telegram: 10 MB fotos, 50 MB vídeos/documentos.
TG_MAX_PHOTO = 10 * 1024 * 1024
TG_MAX_FILE = 45 * 1024 * 1024  # margem abaixo do limite duro de 50 MB


def _too_big_for_telegram(path: str, ext: str) -> bool:
    limit = TG_MAX_PHOTO if ext.lower() in PHOTO_EXTS else TG_MAX_FILE
    try:
        return os.path.getsize(path) > limit
    except OSError:
        return False


def _embed_metadata(paths: list[str], dt: datetime, description: str) -> None:
    """Escreve datas EXIF (e descrição, em fotos) via exiftool. Best-effort:
    sem exiftool instalado fica só o mtime."""
    if not paths:
        return
    if shutil.which("exiftool") is None:
        log.warning("exiftool não encontrado: ficheiros guardados sem metadados EXIF.")
        return
    stamp = dt.strftime("%Y:%m:%d %H:%M:%S")
    args = ["exiftool", "-overwrite_original", "-q", f"-AllDates={stamp}"]
    if description and os.path.splitext(paths[0])[1].lower() in PHOTO_EXTS:
        args.append(f"-ImageDescription={description[:500]}")
    result = subprocess.run(args + paths, capture_output=True, text=True)
    if result.returncode != 0:
        log.warning("exiftool falhou em %d ficheiro(s): %s", len(paths), result.stderr.strip())


def process_medias(
    archive_root: Path,
    entry: Entry,
    medias: list[dict[str, Any]],
    tg: Notifier,
    folders: list[str],
    caption: str = "",
    doc_folders: list[str] | None = None,
    doc_title: str = "",
) -> None:
    """Descarrega, arquiva em disco e envia as medias para o notificador.

    Ficheiros chamam-se <data>_<hora>_<NN><ext> (NN = posição no post) e vão
    para <pasta>/<ano>/<data>/. Datas EXIF, descrição e mtime ficam com a data
    da entrada para as apps de fotos ordenarem bem. Cada ficheiro é guardado
    em todas as pastas de ``folders`` (um download, depois cópias).
    Fotos e vídeos vão em álbuns de até 10. PDFs e outros vão como documento.

    PDFs de entradas dirigidas só às nossas crianças (``doc_folders``) ganham
    também uma cópia com nome legível em <Criança>/Documentos/.
    """
    photos_videos: list[tuple[str, str]] = []  # (primary_path, ext)

    entry_dt = _entry_datetime(entry)
    date_str = _archive_date(entry)
    year = date_str[:4]
    primary_dir = os.path.join(archive_root, folders[0], year, date_str)

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
                    # Ficheiro apagado no CDN da escola: não falha a entrada toda.
                    log.warning("Media desaparecida do servidor (404): %s%s", media["Id"], ext)
                    continue
                raise
            with open(primary_path, "wb") as out:
                out.write(content)
            log.info("Guardado %s", primary_path)
            if ext.lower() in PHOTO_EXTS:
                new_photos.append(primary_path)
            elif ext.lower() in VIDEO_EXTS:
                new_videos.append(primary_path)
        else:
            log.debug("Já existe: %s", primary_path)

        all_paths.append(primary_path)

        if ext.lower() == ".pdf" and doc_folders and os.path.exists(primary_path):
            _save_document_copy(archive_root, primary_path, doc_folders, date_str, doc_title)

        if ext in PHOTO_EXTS or ext in VIDEO_EXTS:
            if _too_big_for_telegram(primary_path, ext):
                log.warning("Demasiado grande para o Telegram, só arquivado: %s", primary_path)
            else:
                photos_videos.append((primary_path, ext))

    # EXIF nos ficheiros novos, depois mtime e cópias para as outras pastas.
    _embed_metadata(new_photos, entry_dt, caption)
    _embed_metadata(new_videos, entry_dt, "")
    mtime = entry_dt.timestamp()
    for primary_path in all_paths:
        os.utime(primary_path, (mtime, mtime))
        file_name = os.path.basename(primary_path)
        for extra_folder in folders[1:]:
            extra_dir = os.path.join(archive_root, extra_folder, year, date_str)
            os.makedirs(extra_dir, exist_ok=True)
            extra_path = os.path.join(extra_dir, file_name)
            if not os.path.exists(extra_path):
                shutil.copy2(primary_path, extra_path)
                log.info("Copiado para %s", extra_path)

    # Ficheiros que não são foto/vídeo (PDFs etc.) vão como documento.
    for primary_path in all_paths:
        ext = os.path.splitext(primary_path)[1]
        if ext not in PHOTO_EXTS and ext not in VIDEO_EXTS:
            if _too_big_for_telegram(primary_path, ext):
                log.warning("Demasiado grande para o Telegram, só arquivado: %s", primary_path)
                continue
            with open(primary_path, "rb") as doc:
                tg.send_document(doc)

    # Fotos/vídeos em álbuns de até 10.
    for i in range(0, len(photos_videos), 10):
        batch = photos_videos[i : i + 10]
        batch_caption = caption if i == 0 else ""

        if len(batch) == 1:
            dest_path, ext = batch[0]
            with open(dest_path, "rb") as single:
                if ext in PHOTO_EXTS:
                    tg.send_photo(single, caption=batch_caption)
                else:
                    tg.send_video(single, caption=batch_caption)
        else:
            with ExitStack() as stack:
                handles = [stack.enter_context(open(p, "rb")) for p, _ in batch]
                items = [
                    (handle, ext, batch_caption if idx == 0 else "")
                    for idx, ((_, ext), handle) in enumerate(zip(batch, handles, strict=True))
                ]
                tg.send_media_group(items)
