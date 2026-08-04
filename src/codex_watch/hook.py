"""Codex lifecycle hook integration.

The Codex-specific JSON handling lives here, separate from notification
providers. ``UserPromptSubmit`` records the prompt for the active turn and
``Stop`` consumes it when building the completion notification.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from typing import Any, TextIO

from codex_watch.config import ConfigurationError, Settings, load_dotenv, resolve_provider_names
from codex_watch.notifier import build_providers
from codex_watch.notifier.base import (
    DeliveryResult,
    Notification,
    NotificationStatus,
    NotifierService,
)


NOTIFICATION_TITLE = "✅ Codex Finished"
COMPLETION_MESSAGE = "Codex task completed"
HOOK_SUCCESS_RESPONSE = {"continue": True, "suppressOutput": True}


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
    """Persist the documented UserPromptSubmit ``prompt`` for a later Stop."""

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


def consume_task_context(event: dict[str, Any], state_dir: Path) -> TaskContext | None:
    """Read and remove prompt data captured for this session and turn."""

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
    finally:
        try:
            context_path.unlink(missing_ok=True)
        except OSError:
            pass


def format_completion_message(event: dict[str, Any], context: TaskContext | None) -> str:
    """Build a concise body containing the task and available project details."""

    task = context.prompt if context is not None else COMPLETION_MESSAGE
    event_cwd = event.get("cwd")
    cwd = event_cwd if isinstance(event_cwd, str) and event_cwd else None
    if cwd is None and context is not None:
        cwd = context.cwd
    if cwd is None:
        return task
    project_name = Path(cwd.rstrip("/\\")).name
    if project_name:
        return f"{task}\nProject: {project_name}\nDirectory: {cwd}"
    return f"{task}\nDirectory: {cwd}"


def handle_stop_event(
    event: dict[str, Any],
    service: NotifierService,
    *,
    context: TaskContext | None = None,
) -> list[DeliveryResult]:
    """Send a notification for a main-thread Stop event.

    A Stop hook that has already continued a turn is ignored to avoid duplicate
    alerts if another hook asks Codex to continue working.
    """

    if event.get("hook_event_name") != "Stop" or event.get("stop_hook_active") is True:
        return []
    return service.send(
        Notification(
            title=NOTIFICATION_TITLE,
            message=format_completion_message(event, context),
            status=NotificationStatus.SUCCESS,
        )
    )


def _build_parser(default_env_file: Path) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Handle Codex prompt-capture and Stop hooks.")
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
    """Run the fail-open Codex prompt-capture and completion hook command."""

    parser = _build_parser(default_env_file)
    args = parser.parse_args(argv)
    stream = sys.stdin if input_stream is None else input_stream
    context_dir = state_dir or Path(tempfile.gettempdir()) / "codex-watch-notifier"

    try:
        event = json.load(stream)
        if not isinstance(event, dict):
            raise ValueError("hook input must be a JSON object")
        event_name = event.get("hook_event_name")
        if event_name == "UserPromptSubmit":
            remember_task_context(event, context_dir)
            results: list[DeliveryResult] = []
        elif event_name == "Stop":
            load_dotenv(args.env_file)
            settings = Settings.from_environment()
            provider_names = resolve_provider_names(settings, args.provider)
            service = NotifierService(build_providers(settings, provider_names))
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
        # Notification failures must never keep Codex from completing the turn.
        print(f"Warning: Codex completion notification skipped: {exc}", file=sys.stderr)
    except Exception as exc:  # Keep the lifecycle hook fail-open for unexpected errors.
        print(f"Warning: Codex completion notifier failed: {exc}", file=sys.stderr)

    # Supported hook events expect machine-readable output. Never log to stdout.
    print(json.dumps(HOOK_SUCCESS_RESPONSE))
    return 0
