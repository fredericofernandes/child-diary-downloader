# Contributing

Thanks for helping other families keep their children's memories. This page is
in English so that contributors who do not read Portuguese can follow it.

## Ground rules

- **No real data in the repository.** No children's names, school names, room
  names, IDs, URLs with signatures, screenshots or log excerpts from a real
  account. Fixtures use the fictional "Creche Exemplo" with Maria and Tomás;
  extend `tests/factories.py` if you need more shapes.
- **No secrets, ever.** `gitleaks` runs in pre-commit and in CI. If you commit
  a secret by accident, rotate it first, then open an issue.
- Be kind. See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## Development setup

```sh
git clone https://github.com/fredericofernandes/child-diary-downloader
cd child-diary-downloader
uv sync                      # installs the package and dev tools in .venv
uv run pre-commit install    # ruff, mypy, gitleaks on every commit
uv run pytest                # all tests run offline
uv run childdiary --help
```

Python 3.12+ and [uv](https://docs.astral.sh/uv/). `exiftool` is optional for
running, not needed for tests.

## Making changes

1. Open an issue first for anything beyond a small fix, especially new
   notifiers or changes to the archive layout (people rely on it).
2. Branch from `main`, keep commits focused, write the commit message in
   English.
3. Add or update tests. `uv run pytest --cov=childdiary_downloader` should
   not drop below the current coverage.
4. `uv run ruff check . && uv run ruff format . && uv run mypy` must pass
   (pre-commit does it for you).
5. Add a line to `CHANGELOG.md` under *Unreleased*.
6. Open the pull request; CI runs lint, type check, tests on 3.12 and 3.13,
   a secret scan and a Docker build.

## Where things live

| Path | What |
|---|---|
| `src/childdiary_downloader/api.py` | login, pagination (with the boundary workaround), throttling |
| `models.py` | typed view of the API payloads (pydantic), `parse_entry` |
| `handlers.py` | one function per entry type; media download, EXIF, albums |
| `runner.py` | a run over one account: parsing, routing, old-entry cut-off, state |
| `state.py` | SQLite state: entries, failures, archived files with hashes |
| `config.py` | config.yaml schema and `${ENV}` interpolation |
| `i18n/` | every string a family reads; add a language here |
| `notify/` | `Notifier` protocol; apprise (Telegram, ntfy, email…) and digest mode |
| `scheduler.py` | `childdiary daemon` loop and health check |
| `setup_wizard.py`, `checks.py` | first-run wizard and `childdiary check` |
| `tests/factories.py` | builders for fictional API entries |

## Adding a language

Copy `src/childdiary_downloader/i18n/en.py` to `<code>.py`, translate, add
the code to `SUPPORTED_LANGUAGES`, and add a test in `tests/test_handlers.py`
that renders a daily routine in the new language.

## Reporting an API change

ChildDiary may change its payloads. `childdiary discover` writes one example
entry per type to `discovery_dump.json` in the data folder. **Before pasting
anything from it into an issue, replace names, IDs and URLs**; the structure
is what matters.

## Releases

Maintainers: bump `version` in `pyproject.toml`, move the *Unreleased* section
of `CHANGELOG.md` to the new version, commit, tag `vX.Y.Z` and push the tag.
The release workflow builds the multi-arch image, publishes it to GHCR and
creates the GitHub release with the changelog section as notes.
