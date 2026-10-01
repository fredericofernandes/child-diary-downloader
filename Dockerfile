# syntax=docker/dockerfile:1.7
#
# child-diary-downloader: runs `childdiary daemon` on an internal schedule.
#   /config  -> config.yaml + .env   (read-only is fine)
#   /data    -> state, logs, heartbeat
#   /archive -> photos, videos, PDFs
#
# Build:  docker build -t child-diary-downloader .
# Run:    see compose.yaml

FROM python:3.13-slim-bookworm AS builder

COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /uvx /bin/

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never

# Dependencies first, so source edits do not invalidate this layer.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project --no-dev

COPY README.md LICENSE ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev


FROM python:3.13-slim-bookworm

LABEL org.opencontainers.image.source="https://github.com/fredericofernandes/child-diary-downloader" \
      org.opencontainers.image.description="Unofficial ChildDiary backup: archives photos, videos and PDFs and sends daily summaries to Telegram." \
      org.opencontainers.image.licenses="MIT"

# exiftool writes EXIF/QuickTime dates into the archived files.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libimage-exiftool-perl tzdata \
    && rm -rf /var/lib/apt/lists/*

# Run as an unprivileged user; override UID/GID at build time to match the
# owner of the archive volume (see compose.yaml).
ARG UID=1000
ARG GID=1000
RUN groupadd --gid "$GID" childdiary \
    && useradd --uid "$UID" --gid "$GID" --create-home --shell /usr/sbin/nologin childdiary \
    && mkdir -p /config /data /archive \
    && chown childdiary:childdiary /config /data /archive

COPY --from=builder --chown=childdiary:childdiary /app /app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    CDD_CONFIG_DIR=/config \
    CDD_DATA_DIR=/data \
    CDD_ARCHIVE_DIR=/archive \
    CDD_SCHEDULE="0 19 * * *"

USER childdiary
WORKDIR /data
VOLUME ["/config", "/data", "/archive"]

HEALTHCHECK --interval=2m --timeout=10s --start-period=30s --retries=3 \
    CMD childdiary health || exit 1

ENTRYPOINT ["childdiary"]
CMD ["daemon"]
