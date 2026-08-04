"""Telegram Bot API notification provider."""

from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from codex_watch.notifier.base import Notification, NotificationError, NotificationProvider


class TelegramNotifier(NotificationProvider):
    """Send a message through Telegram's HTTPS Bot API."""

    def __init__(self, bot_token: str, chat_id: str, timeout: float = 10.0) -> None:
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.timeout = timeout

    @property
    def name(self) -> str:
        return "telegram"

    def send(self, notification: Notification) -> None:
        endpoint = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        body = urlencode(
            {
                "chat_id": self.chat_id,
                "text": f"{notification.title}\n{notification.message}",
                "disable_web_page_preview": "true",
            }
        ).encode("utf-8")
        request = Request(endpoint, data=body, method="POST")
        request.add_header("Content-Type", "application/x-www-form-urlencoded")

        try:
            with urlopen(request, timeout=self.timeout) as response:  # noqa: S310 (HTTPS URL)
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise NotificationError(f"Telegram returned HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise NotificationError(f"Could not reach Telegram: {exc.reason}") from exc
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise NotificationError(f"Invalid response from Telegram: {exc}") from exc

        if not payload.get("ok"):
            description = payload.get("description", "unknown Telegram API error")
            raise NotificationError(str(description))
