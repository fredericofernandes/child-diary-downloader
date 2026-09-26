"""Notificadores. Na Fase 1 existe apenas o Telegram e o NullNotifier."""

from childdiary_downloader.notify.telegram import NullTelegram, Telegram

__all__ = ["NullTelegram", "Telegram"]
