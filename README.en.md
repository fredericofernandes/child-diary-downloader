# child-diary-downloader

[![CI](https://github.com/fredericofernandes/child-diary-downloader/actions/workflows/ci.yml/badge.svg)](https://github.com/fredericofernandes/child-diary-downloader/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/fredericofernandes/child-diary-downloader?display_name=tag)](https://github.com/fredericofernandes/child-diary-downloader/releases)
[![Docker](https://img.shields.io/badge/ghcr.io-child--diary--downloader-blue?logo=docker)](https://github.com/fredericofernandes/child-diary-downloader/pkgs/container/child-diary-downloader)
[![Python](https://img.shields.io/badge/python-3.12%20%7C%203.13-blue?logo=python&logoColor=white)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

**Automatic backup of your children's [ChildDiary](https://childdiary.net)
diary, with daily summaries on Telegram.** An unofficial tool, built by a
parent, for families in Portugal and Ireland.

🇵🇹 [Versão em português](README.md)

<p align="center">
  <img src="docs/images/telegram-demo.svg" alt="Example daily summary on Telegram (fictional data)" width="380">
</p>

## Why

Crèches and preschools on ChildDiary post photos, videos, reports and each
child's daily routine: what they ate, how long they napped, what they did.
Those are the memories of our children's first years, and **they live in a
service we do not control**. When a child changes school or finishes
preschool, access can end, and years of photos with it.

This project downloads everything to a folder of your own, organised by child
and by day, with the dates written into the photos themselves so Apple
Photos, Google Photos or Immich place them correctly on the timeline. As a
bonus, it sends the day's routine to Telegram as soon as the teacher posts it.

ChildDiary's terms of service acknowledge that the children's data belongs to
their guardians (GDPR) and do not forbid automated access to your own
account. Use it on your own account only.

## What it does

- **Archives everything**: photos, videos and PDFs from every entry on your
  account, as `<archive>/<Child>/<Year>/<YYYY-MM-DD>/YYYY-MM-DD_HHMMSS_NN.jpg`.
- **Correct dates**: entry date written to EXIF (photos), QuickTime metadata
  (videos) and file `mtime`, plus the post's caption as the photo description.
- **Routes room and school posts** to the right child's folder, with a
  routing map that `childdiary setup` proposes for you.
- **Readable document names**: development reports, adapted menus and letters
  addressed to your child get a copy as
  `<Child>/Documents/YYYY-MM-DD — Title.pdf`.
- **Telegram summaries**: daily routine (drop-off and pick-up, meals, naps,
  nappies, activities), posts with photo albums, events with dates and RSVP.
  In English or Portuguese.
- **Runs by itself every day**: Docker with a built-in schedule and health
  check, or launchd, systemd and cron. Remembers what it processed, retries
  what failed and alerts you on Telegram if something breaks.
- **Good neighbour**: honest User-Agent, pauses between requests, respects
  the server's back-off. Works around an API pagination bug that drops one
  entry at every page boundary.

Several accounts (one per crèche), several children per account, siblings in
different schools: one configuration.

```
~/Pictures/childdiary/
├── Maria/
│   ├── 2025/
│   │   └── 2025-09-15/
│   │       ├── 2025-09-15_101530_01.jpg
│   │       ├── 2025-09-15_101530_02.jpg
│   │       └── 2025-09-15_143012_01.mp4
│   └── Documents/
│       ├── 2025-12-19 — Autumn term development report.pdf
│       └── Menus/
│           └── 2026-01-05 — Dairy-free menu.pdf
└── Tomás/
    └── 2026/
        └── 2026-03-10/
            └── 2026-03-10_091500_01.jpg
```

## 5-minute install (Docker)

You need Docker on a machine that stays on (a NAS, a Raspberry Pi, a mini PC)
and a Telegram bot (optional: without one it only archives).

```sh
mkdir -p childdiary/{config,data,archive} && cd childdiary
curl -O https://raw.githubusercontent.com/fredericofernandes/child-diary-downloader/main/compose.yaml
docker compose run --rm childdiary setup     # logs in, discovers children and rooms, writes the config
docker compose run --rm childdiary check     # verifies logins, Telegram and the archive folder
docker compose run --rm childdiary run --no-telegram   # first full download, no notifications
docker compose up -d                          # from now on, every day at 19:00
```

Full guide, including Synology/QNAP/Unraid NAS and Raspberry Pi:
[docs/install-docker.md](docs/install-docker.md) and
[docs/install-nas.md](docs/install-nas.md) (Portuguese).

Without Docker (Mac or Linux with `uv`/`pipx`, scheduled with launchd,
systemd or cron): [docs/install-python.md](docs/install-python.md).

## Configuration

`childdiary setup` writes two files:

- `config.yaml`: children, rooms, language, folders. No secrets.
- `.env`: passwords and the Telegram token, referenced from the YAML as `${NAME}`.

A commented example with every option is in
[`config.example.yaml`](config.example.yaml); the full reference in
[docs/configuration.md](docs/configuration.md).

```yaml
language: en
timezone: Europe/Dublin
accounts:
  - name: Example Crèche
    username: example.family@example.com
    password: ${CDD_PASSWORD_CRECHE}
    children:
      "00000000-0000-0000-0000-000000000001": Maria
routing:
  groups:
    "Sunflower Room": [Maria]
telegram:
  token: ${CDD_TELEGRAM_TOKEN}
  chat_id: ${CDD_TELEGRAM_CHAT_ID}
```

### Commands

| Command | Purpose |
|---|---|
| `childdiary setup` | first-run wizard |
| `childdiary check [--send-test]` | verifies logins, children IDs, Telegram, exiftool |
| `childdiary run` | downloads what is new, archives and notifies |
| `childdiary run --no-telegram` | archive only (first load, reprocessing) |
| `childdiary run --dry-run` | shows what it would do, touches nothing |
| `childdiary list-groups` | lists children and rooms per account, with IDs |
| `childdiary status` | processed entries, pending failures, archived files |
| `childdiary daemon` | stays running and executes on schedule (Docker) |
| `childdiary health` | daemon status, for the Docker health check |

## FAQ

**Is this official?** No. It is an independent project that uses the same API
as the ChildDiary web app. It may stop working if the API changes; open an
issue if it does.

**Is it safe to give it my password?** The password stays on your machine, in
a `.env` file with restricted permissions, and is only used to log in to
`app.childdiary.net`. The code is public and small: read it.

**Why not run it on GitHub Actions, for free, every day?** Because that would
put your credentials and your children's photos on third-party servers, with
no persistent state and no guaranteed time. Children's photos stay at home: a
NAS, a Raspberry Pi or your laptop.

**A new room appeared and its photos went to a folder named after the room.**
That is by design: add the room to `routing.groups` in `config.yaml` and move
the folder. The log warns every time it happens.

**Can I download everything again?** Delete `state.db` from the data folder
and run `childdiary run --no-telegram`. Files that already exist are not
downloaded again. `childdiary status` shows what the state knows.

**What about photos the school deleted?** If the file is gone from the server
(404) it is logged and the entry is marked done. Whatever was already in your
archive stays.

**Do I need exiftool?** No, but without it photos only get the right `mtime`
and photo apps fall back to the import date. The Docker image includes it.

## Roadmap

- [ ] More notifiers: email, ntfy, Discord, Slack (via apprise)
- [ ] One daily digest instead of a message per entry
- [ ] SQLite state and typed data model for entries
- [ ] Direct export to Immich and Apple Photos
- [ ] A yearly PDF per child (the "yearbook")
- [ ] Minimal web UI to browse the archive

Ideas and requests in the [issues](https://github.com/fredericofernandes/child-diary-downloader/issues).

## Contributing

Fixes, translations and reports from schools with different structures are
welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md): the project has tests with
fictional data, `ruff`, `mypy` and `pre-commit`, and accepts no real
children's data in the repository.

## Disclaimer

Independent project, not affiliated with ChildDiary. Intended solely for
backing up the data of your own account, for which you are responsible as the
child's guardian. Do not redistribute what you download: it is personal data
of children, yours and the other families' in the room.

## License

[MIT](LICENSE) © Frederico Fernandes
