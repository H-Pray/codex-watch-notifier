"""Codex lifecycle hook integration.

The Codex-specific JSON handling lives here, separate from notification
providers. UserPromptSubmit records the prompt for the active turn,
PermissionRequest reads it without consuming it, and Stop consumes it when
building the completion notification.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import re
import sys
import tempfile
from typing import Any, TextIO

from codex_watch.approval import create_approval_request, wait_for_decision
from codex_watch.config import ConfigurationError, Settings, load_dotenv, resolve_provider_names
from codex_watch.notifier import build_providers
from codex_watch.notifier.base import (
    DeliveryResult,
    Notification,
    NotificationAction,
    NotificationStatus,
    NotifierService,
)

NOTIFICATION_TITLE = "✅ Codex Finished"
APPROVAL_NOTIFICATION_TITLE = "⚠️ Codex Needs Approval"
COMPUTER_USE_NOTIFICATION_TITLE = "Codex Computer Use"
COMPLETION_MESSAGE = "Codex task completed"
APPROVAL_MESSAGE = "Codex task awaiting approval"
HOOK_SUCCESS_RESPONSE = {"continue": True, "suppressOutput": True}
MAX_TASK_LENGTH = 300
MAX_ACTION_LENGTH = 180
MAX_TOOL_LENGTH = 80

_ENV_ASSIGNMENT = re.compile(
    r"(?i)(^|[\s;])((?:\$env:)?[A-Za-z_][A-Za-z0-9_]*\s*=\s*)"
    r"(?:\"[^\"]*\"|'[^']*'|[^\s;]+)"
)
_SENSITIVE_OPTION = re.compile(
    r"(?i)((?<![\w-])--?(?:api[-_]?key|token|password|passwd|secret|authorization|auth)"
    r"(?:=|\s+))(?:\"[^\"]*\"|'[^']*'|\S+)"
)
_BEARER_TOKEN = re.compile(r"(?i)\b(Bearer\s+)\S+")
_URL_CREDENTIALS = re.compile(r"(https?://)[^\s/@:]+(?::[^\s/@]*)?@", re.IGNORECASE)


@dataclass(frozen=True)
class TaskContext:
    """Prompt details captured when Codex accepts a user turn."""

    prompt: str
    cwd: str | None = None


def _context_path(event: dict[str, Any], state_dir: Path) -> Path | None:
    """Return a safe per-turn cache path without exposing IDs in filenames."""

    session_id = event.get("session_id")
    turn_id = event.get("turn_id")
    if not isinstance(session_id, str) or not session_id:
        return None
    if not isinstance(turn_id, str) or not turn_id:
        return None
    digest = hashlib.sha256(f"{session_id}\0{turn_id}".encode("utf-8")).hexdigest()
    return state_dir / f"{digest}.json"


def remember_task_context(event: dict[str, Any], state_dir: Path) -> None:
    """Persist the UserPromptSubmit prompt for later hooks."""

    if event.get("hook_event_name") != "UserPromptSubmit":
        return
    prompt = event.get("prompt")
    context_path = _context_path(event, state_dir)
    if not isinstance(prompt, str) or not prompt.strip() or context_path is None:
        return
    cwd = event.get("cwd")
    context = TaskContext(prompt=prompt.strip(), cwd=cwd if isinstance(cwd, str) else None)
    state_dir.mkdir(parents=True, exist_ok=True)
    context_path.write_text(json.dumps(asdict(context)), encoding="utf-8")


def read_task_context(event: dict[str, Any], state_dir: Path) -> TaskContext | None:
    """Read prompt data for this session and turn without removing it."""

    context_path = _context_path(event, state_dir)
    if context_path is None or not context_path.is_file():
        return None
    try:
        payload = json.loads(context_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return None
        prompt = payload.get("prompt")
        cwd = payload.get("cwd")
        if not isinstance(prompt, str) or not prompt.strip():
            return None
        return TaskContext(
            prompt=prompt.strip(),
            cwd=cwd if isinstance(cwd, str) and cwd else None,
        )
    except (OSError, ValueError):
        return None


def consume_task_context(event: dict[str, Any], state_dir: Path) -> TaskContext | None:
    """Read and remove prompt data captured for this session and turn."""

    context_path = _context_path(event, state_dir)
    context = read_task_context(event, state_dir)
    if context_path is not None:
        try:
            context_path.unlink(missing_ok=True)
        except OSError:
            pass
    return context


def _sanitize_text(value: str, *, limit: int) -> str:
    """Redact common credentials, flatten whitespace, and cap watch payload size."""

    text = _URL_CREDENTIALS.sub(r"\1[REDACTED]@", value)
    text = _BEARER_TOKEN.sub(r"\1[REDACTED]", text)
    text = _SENSITIVE_OPTION.sub(r"\1[REDACTED]", text)
    text = _ENV_ASSIGNMENT.sub(r"\1\2[REDACTED]", text)
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "?"


def _requested_action(event: dict[str, Any], tool_name: str | None) -> str:
    """Extract allowlisted fields instead of serializing a tool payload."""

    tool_input = event.get("tool_input")
    candidate: str | None = None
    if isinstance(tool_input, dict):
        for key in ("command", "description", "action"):
            value = tool_input.get(key)
            if isinstance(value, str) and value.strip():
                candidate = value
                break
            if key == "command" and isinstance(value, list):
                parts = [part for part in value if isinstance(part, str)]
                if parts:
                    candidate = " ".join(parts)
                    break
    if candidate is not None:
        sanitized = _sanitize_text(candidate, limit=MAX_ACTION_LENGTH)
        if sanitized:
            return sanitized
    if tool_name:
        return f"Approval requested for {tool_name}"
    return "Approval requested"


def _event_cwd(event: dict[str, Any], context: TaskContext | None) -> str | None:
    event_cwd = event.get("cwd")
    if isinstance(event_cwd, str) and event_cwd:
        return event_cwd
    return context.cwd if context is not None else None


def _project_name(cwd: str) -> str:
    return re.split(r"[/\\]", cwd.rstrip("/\\"))[-1]


def _display_directory(cwd: str) -> str:
    """Shorten the local home directory for compact watch notifications."""

    home = str(Path.home()).rstrip("/\\")
    if cwd == home:
        return "~"
    if cwd.startswith(home + "/"):
        return "~" + cwd[len(home) :]
    return cwd


def format_completion_message(event: dict[str, Any], context: TaskContext | None) -> str:
    """Build a concise body containing the task and available project details."""

    task = context.prompt if context is not None else COMPLETION_MESSAGE
    cwd = _event_cwd(event, context)
    if cwd is None:
        return task
    project_name = _project_name(cwd)
    display_directory = _display_directory(cwd)
    if project_name:
        return f"{task}\nProj: {project_name}\nDir: {display_directory}"
    return f"{task}\nDir: {display_directory}"


def format_permission_message(event: dict[str, Any], context: TaskContext | None) -> str:
    """Build an approval alert from cached context and safe event fields."""

    task = context.prompt if context is not None else APPROVAL_MESSAGE
    task = _sanitize_text(task, limit=MAX_TASK_LENGTH) or APPROVAL_MESSAGE
    raw_tool = event.get("tool_name")
    tool_name = (
        _sanitize_text(raw_tool, limit=MAX_TOOL_LENGTH)
        if isinstance(raw_tool, str) and raw_tool.strip()
        else None
    )
    lines = [task, f"Action: {_requested_action(event, tool_name)}"]
    if tool_name:
        lines.append(f"Tool: {tool_name}")

    cwd = _event_cwd(event, context)
    if cwd:
        project_name = _sanitize_text(_project_name(cwd), limit=MAX_TOOL_LENGTH)
        if project_name:
            lines.append(f"Proj: {project_name}")
        display_directory = _display_directory(cwd)
        lines.append(f"Dir: {_sanitize_text(display_directory, limit=MAX_TASK_LENGTH)}")
    return "\n".join(lines)


def _is_computer_use_request(event: dict[str, Any]) -> bool:
    """Recognize Computer Use permission requests across tool-name variants."""

    tool_name = event.get("tool_name")
    return isinstance(tool_name, str) and "computer" in tool_name.lower()


def handle_stop_event(
    event: dict[str, Any],
    service: NotifierService,
    *,
    context: TaskContext | None = None,
) -> list[DeliveryResult]:
    """Send a notification for a main-thread Stop event."""

    if event.get("hook_event_name") != "Stop" or event.get("stop_hook_active") is True:
        return []
    return service.send(
        Notification(
            title=NOTIFICATION_TITLE,
            message=format_completion_message(event, context),
            status=NotificationStatus.SUCCESS,
        )
    )


def handle_permission_request_event(
    event: dict[str, Any],
    service: NotifierService,
    *,
    context: TaskContext | None = None,
    actions: tuple[NotificationAction, ...] = (),
) -> list[DeliveryResult]:
    """Notify about an approval prompt without making an allow/deny decision."""

    if event.get("hook_event_name") != "PermissionRequest":
        return []
    return service.send(
        Notification(
            title=(
                COMPUTER_USE_NOTIFICATION_TITLE
                if _is_computer_use_request(event)
                else APPROVAL_NOTIFICATION_TITLE
            ),
            message=format_permission_message(event, context),
            status=NotificationStatus.ATTENTION,
            actions=actions,
        )
    )


def _build_parser(default_env_file: Path) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Handle Codex prompt-capture, approval, and Stop hooks."
    )
    parser.add_argument("--env-file", type=Path, default=default_env_file)
    parser.add_argument(
        "--provider",
        action="append",
        help="Provider to use; defaults to NOTIFICATION_PROVIDERS from the env file.",
    )
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    input_stream: TextIO | None = None,
    default_env_file: Path = Path(".env"),
    state_dir: Path | None = None,
) -> int:
    """Run the fail-open Codex lifecycle hook command."""

    parser = _build_parser(default_env_file)
    args = parser.parse_args(argv)
    stream = sys.stdin if input_stream is None else input_stream
    context_dir = state_dir or Path(tempfile.gettempdir()) / "codex-watch-notifier"

    try:
        response: dict[str, object] = HOOK_SUCCESS_RESPONSE
        event = json.load(stream)
        if not isinstance(event, dict):
            raise ValueError("hook input must be a JSON object")
        event_name = event.get("hook_event_name")
        if event_name == "UserPromptSubmit":
            remember_task_context(event, context_dir)
            results: list[DeliveryResult] = []
        elif event_name in {"PermissionRequest", "Stop"}:
            load_dotenv(args.env_file)
            settings = Settings.from_environment()
            provider_names = resolve_provider_names(settings, args.provider)
            service = NotifierService(build_providers(settings, provider_names))
            if event_name == "PermissionRequest":
                context = read_task_context(event, context_dir)
                approval_request = None
                if settings.approval_actions and "ntfy" in provider_names:
                    approval_request = create_approval_request(settings.ntfy_server_url)
                results = handle_permission_request_event(
                    event,
                    service,
                    context=context,
                    actions=approval_request.actions if approval_request else (),
                )
                if approval_request and any(result.delivered for result in results):
                    decision = wait_for_decision(
                        settings.ntfy_server_url,
                        approval_request.response_topic,
                        timeout=settings.approval_timeout,
                    )
                    if decision is not None:
                        response = decision.as_hook_response()
            else:
                context = None
                if event.get("stop_hook_active") is not True:
                    context = consume_task_context(event, context_dir)
                results = handle_stop_event(event, service, context=context)
        else:
            results = []
        for result in results:
            if not result.delivered:
                print(
                    f"Warning: {result.provider} notification failed: {result.error}",
                    file=sys.stderr,
                )
    except (ConfigurationError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Warning: Codex lifecycle notification skipped: {exc}", file=sys.stderr)
    except Exception as exc:
        print(f"Warning: Codex lifecycle notifier failed: {exc}", file=sys.stderr)

    print(json.dumps(response, ensure_ascii=False))
    return 0
