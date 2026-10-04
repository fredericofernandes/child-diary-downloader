# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.0] - 2026-10-01

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

[Unreleased]: https://github.com/fredericofernandes/child-diary-downloader/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/fredericofernandes/child-diary-downloader/releases/tag/v0.1.0
