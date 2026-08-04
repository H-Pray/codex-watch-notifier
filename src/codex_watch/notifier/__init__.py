"""Notification providers and provider construction."""

from __future__ import annotations

from collections.abc import Iterable

from codex_watch.config import Settings
from codex_watch.notifier.base import NotificationProvider
from codex_watch.notifier.desktop import DesktopNotifier
from codex_watch.notifier.ntfy import NtfyNotifier
from codex_watch.notifier.telegram import TelegramNotifier


def build_providers(settings: Settings, names: Iterable[str]) -> list[NotificationProvider]:
    """Build configured notification providers.

    New providers only need an implementation of NotificationProvider and a
    construction branch here (or a future plugin registry).
    """

    providers: list[NotificationProvider] = []
    for name in names:
        settings.validate_provider(name)
        if name == "desktop":
            providers.append(DesktopNotifier())
        elif name == "ntfy":
            providers.append(
                NtfyNotifier(
                    server_url=settings.ntfy_server_url,
                    topic=settings.ntfy_topic or "",
                    token=settings.ntfy_token,
                    priority=settings.ntfy_priority,
                )
            )
        elif name == "telegram":
            # validate_provider guarantees that these values are present.
            providers.append(
                TelegramNotifier(
                    bot_token=settings.telegram_bot_token or "",
                    chat_id=settings.telegram_chat_id or "",
                )
            )
    return providers


__all__ = ["build_providers"]
