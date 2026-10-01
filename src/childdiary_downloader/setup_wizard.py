"""Interactive first-run setup: log in, discover children and rooms, propose
the routing map and write config.yaml + .env.

The discovery logic is pure (``discover_account``) so it can be unit tested;
the prompts live in ``run_wizard`` and go through click, which the test
runner can feed from a string.
"""

from __future__ import annotations

import os
import re
import stat
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import click
from rich.console import Console
from rich.table import Table

from childdiary_downloader.api import fetch_entries, login
from childdiary_downloader.i18n import SUPPORTED_LANGUAGES

console = Console()

TIMEZONE_BY_LANGUAGE = {"pt": "Europe/Lisbon", "en": "Europe/Dublin"}


@dataclass
class Discovered:
    """What one account's entries reveal."""

    school: str = ""  # most common InstanceName
    schools: dict[str, int] = field(default_factory=dict)  # every InstanceName seen -> count
    own_children: dict[str, str] = field(default_factory=dict)  # id -> name
    other_children: dict[str, str] = field(default_factory=dict)
    groups: dict[str, str] = field(default_factory=dict)  # id -> name
    child_groups: dict[str, set[str]] = field(default_factory=dict)  # child id -> group ids
    entries: int = 0

    def group_targets(self, group_id: str) -> list[str]:
        """Own children who belong (or belonged) to this group."""
        return [
            name
            for cid, name in self.own_children.items()
            if group_id in self.child_groups.get(cid, set())
        ]

    def suggest_targets(self, group_id: str, folder_names: dict[str, str]) -> list[str]:
        """Best guess for a group's routing, as folder names.

        1. Children who are members of the group (their room).
        2. Otherwise, activity groups such as "Judo Papoilas + Tulipas" usually
           name the rooms they draw from: match the children whose room name
           shares a distinctive word with the group name.
        3. Otherwise, every child.
        """
        members = [
            folder_names[c]
            for c in self.own_children
            if group_id in self.child_groups.get(c, set())
        ]
        if members:
            return members
        group_words = _words(self.groups.get(group_id, ""))
        by_room = [
            folder_names[cid]
            for cid in self.own_children
            if any(
                _words(self.groups.get(room, "")) & group_words
                for room in self.child_groups.get(cid, set())
            )
        ]
        if by_room:
            return list(dict.fromkeys(by_room))
        return list(dict.fromkeys(folder_names.values()))


_GENERIC_WORDS = {
    "sala",
    "room",
    "class",
    "grupo",
    "group",
    "turma",
    "de",
    "da",
    "do",
    "the",
    "and",
}


def _words(name: str) -> set[str]:
    """Distinctive words of a group name: 'Sala Girassóis' -> {'girassóis'}."""
    tokens = re.findall(r"[^\W\d_]+", name.lower())
    return {t for t in tokens if len(t) > 2 and t not in _GENERIC_WORDS}


def discover_account(entries: list[dict[str, Any]]) -> Discovered:
    """Own children are the ones with daily-routine entries (type 2): those
    are private to each family, unlike class posts that list the whole room."""
    d = Discovered(entries=len(entries))
    seen_children: dict[str, str] = {}
    for entry in entries:
        if entry.get("InstanceName"):
            name = str(entry["InstanceName"])
            d.schools[name] = d.schools.get(name, 0) + 1
        for item in entry.get("For", []) or []:
            kind, item_id = item.get("Type"), item.get("Id")
            if not item_id:
                continue
            if kind == "Child":
                seen_children[item_id] = item.get("Description") or item_id
                if item.get("GroupId"):
                    d.child_groups.setdefault(item_id, set()).add(item["GroupId"])
                if entry.get("Type") == 2:
                    d.own_children[item_id] = seen_children[item_id]
            elif kind == "Group":
                d.groups[item_id] = item.get("Description") or item_id
    d.other_children = {k: v for k, v in seen_children.items() if k not in d.own_children}
    if d.schools:
        d.school = max(d.schools, key=lambda k: d.schools[k])
    return d


def env_var_name(account_name: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", account_name).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^A-Za-z0-9]+", "_", ascii_name).strip("_").upper() or "ACCOUNT"
    return f"CDD_PASSWORD_{slug}"


def _yaml_str(value: str) -> str:
    """Quote a scalar for YAML output (always quoted: names can contain ': ')."""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def render_config(
    *,
    language: str,
    timezone: str,
    archive_dir: str,
    accounts: list[dict[str, Any]],
    routing_groups: dict[str, list[str]],
    routing_instances: dict[str, list[str]],
    telegram: bool,
) -> str:
    """Hand-written YAML so the file keeps helpful comments."""
    lines = [
        "# Generated by `childdiary setup`. Edit freely; see config.example.yaml for every option.",
        f"archive_dir: {_yaml_str(archive_dir)}",
        f"language: {language}",
        f"timezone: {timezone}",
        "",
    ]
    if telegram:
        lines += [
            "telegram:",
            "  token: ${CDD_TELEGRAM_TOKEN}",
            "  chat_id: ${CDD_TELEGRAM_CHAT_ID}",
            "  max_age_days: 3",
            "",
        ]
    lines.append("accounts:")
    for acc in accounts:
        lines += [
            f"  - name: {_yaml_str(acc['name'])}",
            f"    username: {_yaml_str(acc['username'])}",
            f"    password: ${{{acc['env_var']}}}",
            "    children:",
        ]
        for cid, name in acc["children"].items():
            lines.append(f"      {_yaml_str(cid)}: {_yaml_str(name)}")
    lines += ["", "routing:", "  groups:"]
    for group, targets in routing_groups.items():
        lines.append(f"    {_yaml_str(group)}: [{', '.join(_yaml_str(t) for t in targets)}]")
    lines.append("  instances:")
    for school, targets in routing_instances.items():
        lines.append(f"    {_yaml_str(school)}: [{', '.join(_yaml_str(t) for t in targets)}]")
    lines += ["  child_since: {}", ""]
    return "\n".join(lines)


def write_env(path: Path, values: dict[str, str]) -> None:
    """Add or replace variables in a .env file, keeping other lines, mode 600."""
    existing = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    done: set[str] = set()
    out: list[str] = []
    for line in existing:
        key = line.split("=", 1)[0].strip()
        if key in values:
            out.append(f"{key}={values[key]}")
            done.add(key)
        else:
            out.append(line)
    for key, value in values.items():
        if key not in done:
            out.append(f"{key}={value}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)


def _show_discovery(d: Discovered) -> None:
    table = Table(title=f"{d.school or 'School'} ({d.entries} entries)")
    table.add_column("Kind")
    table.add_column("Name")
    table.add_column("ID", style="dim")
    for cid, name in d.own_children.items():
        table.add_row("child (yours)", name, cid)
    for gid, name in sorted(d.groups.items(), key=lambda x: x[1]):
        table.add_row("room / group", name, gid)
    console.print(table)


def run_wizard(config_file: Path, default_archive: str) -> None:
    """Drive the prompts and write the files. Raises click exceptions on abort."""
    console.print("[bold]child-diary-downloader setup[/bold]")
    console.print(f"Configuration will be written to [bold]{config_file}[/bold]\n")
    if config_file.exists() and not click.confirm(
        "config.yaml already exists. Overwrite?", default=False
    ):
        raise click.Abort()

    language = click.prompt(
        "Language for notifications and folder names",
        type=click.Choice(list(SUPPORTED_LANGUAGES)),
        default="pt",
    )
    timezone = click.prompt("School timezone (IANA name)", default=TIMEZONE_BY_LANGUAGE[language])
    archive_dir = click.prompt("Archive folder", default=default_archive)

    accounts: list[dict[str, Any]] = []
    env_values: dict[str, str] = {}
    routing_groups: dict[str, list[str]] = {}
    routing_instances: dict[str, list[str]] = {}
    while True:
        console.print(f"\n[bold]ChildDiary account {len(accounts) + 1}[/bold]")
        username = click.prompt("Username (email)")
        password = click.prompt("Password", hide_input=True)
        console.print("Logging in and reading the diary…")
        try:
            session = login({"Username": username, "Password": password, "RememberMe": True})
            entries = fetch_entries(session)
        except Exception as e:
            console.print(f"[red]Login or download failed:[/red] {e}")
            if click.confirm("Try again?", default=True):
                continue
            raise click.Abort() from e

        d = discover_account(entries)
        _show_discovery(d)
        if not d.own_children:
            console.print(
                "[yellow]No daily routines found, so your children could not be told apart "
                "from their classmates.[/yellow]"
            )
            d.own_children = d.other_children

        children: dict[str, str] = {}
        for cid, name in d.own_children.items():
            # The app stores full legal names; a first name makes a nicer folder.
            folder = click.prompt(f"Folder name for {name}", default=name.split()[0])
            children[cid] = folder
        if not children:
            console.print("[red]No children found in this account.[/red]")
            raise click.Abort()

        default_name = d.school or f"Account {len(accounts) + 1}"
        name = click.prompt("Name for this account (used in logs)", default=default_name)
        env_var = env_var_name(name)
        accounts.append(
            {"name": name, "username": username, "env_var": env_var, "children": children}
        )
        env_values[env_var] = password

        all_names = list(dict.fromkeys(children.values()))
        for gid, gname in sorted(d.groups.items(), key=lambda x: x[1]):
            suggested = d.suggest_targets(gid, children)
            answer = click.prompt(
                f"Room '{gname}': whose folder(s)? (comma-separated, '-' for its own folder)",
                default=", ".join(suggested),
                show_default=True,
            )
            targets = [t.strip() for t in answer.split(",") if t.strip() and t.strip() != "-"]
            if targets:
                routing_groups[gname] = targets
        for school in d.schools:  # school-wide posts go to every child of the account
            routing_instances.setdefault(school, [])
            routing_instances[school] = list(dict.fromkeys(routing_instances[school] + all_names))

        if not click.confirm("\nAdd another ChildDiary account?", default=False):
            break

    telegram = click.confirm("\nSend daily summaries to Telegram?", default=True)
    if telegram:
        env_values["CDD_TELEGRAM_TOKEN"] = click.prompt(
            "Bot token (from @BotFather)", hide_input=True
        )
        env_values["CDD_TELEGRAM_CHAT_ID"] = click.prompt("Chat ID")

    config_text = render_config(
        language=language,
        timezone=timezone,
        archive_dir=archive_dir,
        accounts=accounts,
        routing_groups=routing_groups,
        routing_instances=routing_instances,
        telegram=telegram,
    )
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(config_text, encoding="utf-8")
    os.chmod(config_file, stat.S_IRUSR | stat.S_IWUSR)
    write_env(config_file.parent / ".env", env_values)

    console.print(f"\n[green]Written[/green] {config_file} and {config_file.parent / '.env'}")
    console.print("Next steps:")
    console.print("  childdiary check                 # verify logins, Telegram and exiftool")
    console.print("  childdiary run --no-telegram     # first full download, without notifications")
    console.print("  childdiary run                   # from then on (schedule it daily)")
