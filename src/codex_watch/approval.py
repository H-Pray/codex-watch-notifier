"""One-shot approval response channel carried over ntfy."""

from __future__ import annotations

from dataclasses import dataclass
import json
import secrets
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

from codex_watch.notifier.base import NotificationAction


@dataclass(frozen=True)
class ApprovalRequest:
    """A private, per-request ntfy response topic and its actions."""

    response_topic: str
    actions: tuple[NotificationAction, ...]


@dataclass(frozen=True)
class ApprovalDecision:
    """The decision returned by the watch."""

    behavior: str
    message: str | None = None

    def as_hook_response(self) -> dict[str, object]:
        decision: dict[str, str] = {"behavior": self.behavior}
        if self.message:
            decision["message"] = self.message
        return {
            "hookSpecificOutput": {
                "hookEventName": "PermissionRequest",
                "decision": decision,
            }
        }


def create_approval_request(server_url: str) -> ApprovalRequest:
    """Create a hard-to-guess response topic for one approval request."""

    suffix = secrets.token_urlsafe(18).replace("-", "").replace("_", "")
    topic = f"codex-approval-{suffix}"
    endpoint = f"{server_url.rstrip('/')}/{quote(topic, safe='')}"
    return ApprovalRequest(
        response_topic=topic,
        actions=(
            NotificationAction("ALLOW", endpoint, "approve"),
            NotificationAction("DENY", endpoint, "deny"),
        ),
    )


def wait_for_decision(
    server_url: str,
    response_topic: str,
    *,
    timeout: float,
) -> ApprovalDecision | None:
    """Wait for an action message on the per-request ntfy JSON stream."""

    parsed_url = urlsplit(server_url)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        return None
    endpoint = f"{server_url.rstrip('/')}/{quote(response_topic, safe='')}/json"
    request = Request(endpoint, headers={"Accept": "application/x-ndjson"})
    deadline = time.monotonic() + max(0.1, timeout)
    try:
        with urlopen(request, timeout=max(1.0, timeout)) as response:  # noqa: S310
            while time.monotonic() < deadline:
                line = response.readline()
                if not line:
                    break
                try:
                    payload = json.loads(line.decode("utf-8"))
                except (UnicodeDecodeError, ValueError):
                    continue
                if payload.get("event") != "message":
                    continue
                message = str(payload.get("message", "")).strip()
                if message == "approve":
                    return ApprovalDecision("allow")
                if message == "deny":
                    return ApprovalDecision("deny", "Denied from Apple Watch")
    except (HTTPError, URLError, OSError, TimeoutError):
        return None
    return None
