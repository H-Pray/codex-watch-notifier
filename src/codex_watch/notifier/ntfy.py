"""ntfy notification provider for phone and smartwatch delivery."""

from __future__ import annotations

from email.header import Header
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

from codex_watch.notifier.base import Notification, NotificationError, NotificationProvider


class NtfyNotifier(NotificationProvider):
    """Publish notifications through an ntfy server's HTTP API."""

    def __init__(
        self,
        server_url: str,
        topic: str,
        *,
        token: str | None = None,
        priority: str = "default",
        timeout: float = 10.0,
    ) -> None:
        self.server_url = server_url.rstrip("/")
        self.topic = topic
        self.token = token
        self.priority = priority
        self.timeout = timeout

    @property
    def name(self) -> str:
        return "ntfy"

    def send(self, notification: Notification) -> None:
        parsed_url = urlsplit(self.server_url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            raise NotificationError("NTFY_SERVER_URL must be an HTTP or HTTPS URL")
        if not self.topic:
            raise NotificationError("NTFY_TOPIC must not be empty")

        endpoint = f"{self.server_url}/{quote(self.topic, safe='')}"
        request = Request(
            endpoint,
            data=notification.message.encode("utf-8"),
            method="POST",
        )
        request.add_header("Content-Type", "text/plain; charset=utf-8")
        request.add_header("X-Title", Header(notification.title, "utf-8").encode())
        request.add_header("X-Priority", self.priority)
        if notification.actions:
            request.add_header("Actions", self._format_actions(notification))
        if self.token:
            request.add_header("Authorization", f"Bearer {self.token}")

        try:
            with urlopen(request, timeout=self.timeout) as response:  # noqa: S310
                response.read()
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise NotificationError(f"ntfy returned HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise NotificationError(f"Could not reach ntfy: {exc.reason}") from exc
        except OSError as exc:
            raise NotificationError(f"ntfy request failed: {exc}") from exc

    @staticmethod
    def _format_actions(notification: Notification) -> str:
        """Encode ntfy HTTP actions using its ASCII short format."""

        encoded = []
        for action in notification.actions[:3]:
            parts = ["http", action.label, action.url, f"method={action.method}"]
            if action.body:
                parts.append(f"body={action.body}")
            if action.clear:
                parts.append("clear=true")
            encoded.append(", ".join(parts))
        return "; ".join(encoded)
