"""Command-line entry point for codex-watch-notifier."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import time
from typing import Sequence

from codex_watch import __version__
from codex_watch.config import (
    ConfigurationError,
    Settings,
    load_dotenv,
    resolve_provider_names,
)
from codex_watch.notifier import build_providers
from codex_watch.notifier.base import Notification, NotificationStatus, NotifierService
from codex_watch.runner import run_codex


def _add_delivery_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--provider",
        action="append",
        help="Provider to use (desktop, ntfy, or telegram); repeat or use commas.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print without delivering.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="codex-watch",
        description="Run Codex and notify your phone, smartwatch, or desktop when it finishes.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--env-file",
        type=Path,
        default=Path(".env"),
        help="Path to a .env file (default: ./.env).",
    )
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    run_parser = subparsers.add_parser("run", help="Run a Codex task and notify on exit.")
    _add_delivery_options(run_parser)
    run_parser.add_argument(
        "--codex-command", help="Override the Codex executable (default: CODEX_COMMAND or codex)."
    )
    run_parser.add_argument("prompt", help="Prompt passed to the Codex CLI.")
    run_parser.add_argument(
        "codex_extra_args",
        nargs=argparse.REMAINDER,
        help="Extra Codex arguments placed after the prompt (prefix with --).",
    )

    notify_parser = subparsers.add_parser("notify", help="Send a notification directly.")
    _add_delivery_options(notify_parser)
    notify_parser.add_argument("--title", help="Notification title.")
    notify_parser.add_argument("--message", default="Codex notification test", help="Message text.")
    notify_parser.add_argument(
        "--status",
        choices=[status.value for status in NotificationStatus],
        default=NotificationStatus.INFO.value,
    )

    check_parser = subparsers.add_parser("check", help="Validate configuration without sending.")
    check_parser.add_argument("--provider", action="append")
    return parser


def _service(settings: Settings, provider_override: Sequence[str] | None) -> NotifierService:
    names = resolve_provider_names(settings, provider_override)
    return NotifierService(build_providers(settings, names))


def _report_results(service: NotifierService, notification: Notification, dry_run: bool) -> bool:
    results = service.send(notification, dry_run=dry_run)
    all_delivered = True
    for result in results:
        if not result.delivered:
            all_delivered = False
            print(f"Warning: {result.provider} notification failed: {result.error}", file=sys.stderr)
        elif not dry_run:
            print(f"Notification delivered via {result.provider}.")
    return all_delivered


def _run_command(args: argparse.Namespace, settings: Settings) -> int:
    service = _service(settings, args.provider)
    command = args.codex_command or settings.codex_command
    extra_args = list(args.codex_extra_args)
    if extra_args[:1] == ["--"]:
        extra_args = extra_args[1:]

    started = time.monotonic()
    exit_code = run_codex(
        args.prompt,
        command=command,
        command_args=settings.codex_args,
        extra_args=extra_args,
    )
    elapsed = time.monotonic() - started
    if exit_code == 0:
        status = NotificationStatus.SUCCESS
        message = f"✅ Codex task completed ({elapsed:.1f}s)"
    else:
        status = NotificationStatus.FAILURE
        message = f"❌ Codex task failed with exit code {exit_code} ({elapsed:.1f}s)"

    _report_results(
        service,
        Notification(title=settings.notification_title, message=message, status=status),
        args.dry_run,
    )
    # Notification failures never hide or change the Codex process result.
    return exit_code


def _notify_command(args: argparse.Namespace, settings: Settings) -> int:
    service = _service(settings, args.provider)
    delivered = _report_results(
        service,
        Notification(
            title=args.title or settings.notification_title,
            message=args.message,
            status=NotificationStatus(args.status),
        ),
        args.dry_run,
    )
    return 0 if delivered else 1


def _check_command(args: argparse.Namespace, settings: Settings) -> int:
    names = resolve_provider_names(settings, args.provider)
    build_providers(settings, names)
    print("Configuration is valid.")
    print(f"Providers: {', '.join(names)}")
    print(f"Codex invocation: {settings.codex_command} {' '.join(settings.codex_args)} <prompt>")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        load_dotenv(args.env_file)
        settings = Settings.from_environment()
        if args.subcommand == "run":
            return _run_command(args, settings)
        if args.subcommand == "notify":
            return _notify_command(args, settings)
        if args.subcommand == "check":
            return _check_command(args, settings)
    except ConfigurationError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
