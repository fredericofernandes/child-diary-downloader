"""child-diary-downloader: backup não oficial do ChildDiary."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("child-diary-downloader")
except PackageNotFoundError:  # pragma: no cover - só acontece sem instalação
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
