# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Fixed

- Docs, `SECURITY.md` and CLI help still described Telegram as the only
  notifier; the README roadmap listed SQLite state as pending and showed the
  wrong default archive folder.

## [0.2.0] - 2026-10-04

### Changed

- Notifications go through [apprise](https://github.com/caronc/apprise):
  Telegram, ntfy, email, Discord, Slack, Matrix and a hundred other services
  are configured as URLs in a `notifiers` list, with `media: false` for
  text-only destinations. The old `telegram` section still works;
  `max_age_days` moved to the top level. `--no-telegram` is now `--no-notify`
  (the old flag still works).
- `childdiary check` reads only the newest pages instead of the whole diary.
- State moved from `state.json` to a SQLite database (`state.db`): one
  transaction per entry instead of rewriting the whole file, failures keep
  their error message, and every archived file is recorded with its size and
  SHA-256. An existing `state.json` is imported on the first run and renamed
  to `state.json.migrated`.
- API entries are validated into typed models (pydantic) before processing.
  Unknown fields are kept; an entry that fails validation is recorded as
  failed with the reason, retried on the next run, and never stops the run.

### Added

- `mode: digest` on a notifier: one message (and one batch of files) at the
  end of the run instead of a message per entry; long digests are split
  between entries.
- `childdiary status`: entries processed, failures pending retry, archived
  files and bytes.
- `childdiary run --since YYYY-MM-DD`: process entries from a date again
  (files already on disk are reused, not downloaded twice).
- `childdiary verify [--hash]`: compare the archive with the recorded sizes
  and SHA-256 hashes; reports missing and changed files.

## [0.1.0] - 2026-10-04

First public release.

### Added

- Archive of photos, videos and PDFs from every ChildDiary entry, organised
  as `<Child>/<Year>/<Date>/`, with EXIF/QuickTime dates, captions and file
  mtimes set to the entry date (via exiftool, optional).
- Routing of room and school posts to the right child's folder, with an
  explicit map plus automatic discovery; `child_since` cut-off per child.
- Readable copies of child-addressed PDFs in `<Child>/Documentos/` (or
  `Documents/`), with keyword subfolders (menus by default).
- Telegram notifications: daily routine, posts with albums, events, failure
  alerts. Entries older than `max_age_days` are archived silently.
- Portuguese and English strings and folder names (`language`), school
  timezone (`timezone`).
- Workaround for the API's offset pagination dropping an entry at each page
  boundary; early stop on incremental runs; retries with backoff.
- Honest User-Agent and a configurable pause between requests.
- File mtimes computed in the school's timezone, so a container running in
  UTC produces the same dates as a run on a laptop.
- `childdiary setup` wizard, `childdiary check`, `childdiary list-groups`,
  `childdiary discover`, `childdiary run --no-telegram --dry-run`.
- `childdiary daemon` with cron schedule and heartbeat, `childdiary health`;
  Docker image (amd64/arm64) on GHCR with exiftool and a non-root user;
  `compose.yaml` example; install guides for Docker, NAS, launchd, systemd
  and cron.
- Test suite with fictional fixtures (113 tests), ruff, mypy, pre-commit with
  gitleaks, GitHub Actions CI and release workflow.

[Unreleased]: https://github.com/fredericofernandes/child-diary-downloader/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/fredericofernandes/child-diary-downloader/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/fredericofernandes/child-diary-downloader/releases/tag/v0.1.0
