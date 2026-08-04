"""Configuration loading for codex-watch-notifier.

Real environment variables take precedence over values in a local .env file.
The small parser intentionally supports the common KEY=value subset, avoiding
an additional runtime dependency for a simple command-line tool.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import shlex
from typing import Mapping, MutableMapping, Sequence


class ConfigurationError(ValueError):
    """Raised when configuration is missing or invalid."""


def load_dotenv(
    path: Path,
    environ: MutableMapping[str, str] | None = None,
) -> None:
    """Load simple .env values without replacing existing environment values."""

    target = os.environ if environ is None else environ
    if not path.is_file():
        return

    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            raise ConfigurationError(f"Invalid .env entry at {path}:{line_number}")

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key or not key.replace("_", "a").isalnum() or key[0].isdigit():
            raise ConfigurationError(f"Invalid variable name at {path}:{line_number}")
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        target.setdefault(key, value)


def _split_command_args(value: str) -> tuple[str, ...]:
    if not value.strip():
        return ()
    # .env files conventionally use shell-like quoting on every platform. Python's
    # subprocess module handles the later Windows command-line quoting itself.
    return tuple(shlex.split(value, posix=True))


@dataclass(frozen=True)
class Settings:
    """Application settings sourced from environment variables."""

    providers: tuple[str, ...] = ("desktop",)
    ntfy_server_url: str = "https://ntfy.sh"
    ntfy_topic: str | None = None
    ntfy_token: str | None = None
    ntfy_priority: str = "default"
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    codex_command: str = "codex"
    codex_args: tuple[str, ...] = ("exec",)
    notification_title: str = "Codex Watch"

    @classmethod
    def from_environment(cls, environ: Mapping[str, str] | None = None) -> "Settings":
        values = os.environ if environ is None else environ
        raw_providers = values.get("NOTIFICATION_PROVIDERS", "desktop")
        providers = tuple(
            dict.fromkeys(item.strip().lower() for item in raw_providers.split(",") if item.strip())
        )
        if not providers:
            raise ConfigurationError("NOTIFICATION_PROVIDERS must name at least one provider")

        return cls(
            providers=providers,
            ntfy_server_url=values.get("NTFY_SERVER_URL", "https://ntfy.sh").rstrip("/"),
            ntfy_topic=values.get("NTFY_TOPIC") or None,
            ntfy_token=values.get("NTFY_TOKEN") or None,
            ntfy_priority=values.get("NTFY_PRIORITY", "default").strip() or "default",
            telegram_bot_token=values.get("TELEGRAM_BOT_TOKEN") or None,
            telegram_chat_id=values.get("TELEGRAM_CHAT_ID") or None,
            codex_command=values.get("CODEX_COMMAND", "codex").strip() or "codex",
            codex_args=_split_command_args(values.get("CODEX_ARGS", "exec")),
            notification_title=values.get("CODEX_WATCH_TITLE", "Codex Watch").strip()
            or "Codex Watch",
        )

    def validate_provider(self, name: str) -> None:
        """Validate settings needed by a single provider."""

        if name == "ntfy":
            if not self.ntfy_topic:
                raise ConfigurationError("ntfy is enabled but NTFY_TOPIC is missing")
            if not self.ntfy_server_url:
                raise ConfigurationError("ntfy is enabled but NTFY_SERVER_URL is empty")
        elif name == "telegram":
            missing = []
            if not self.telegram_bot_token:
                missing.append("TELEGRAM_BOT_TOKEN")
            if not self.telegram_chat_id:
                missing.append("TELEGRAM_CHAT_ID")
            if missing:
                raise ConfigurationError(
                    "Telegram is enabled but these values are missing: " + ", ".join(missing)
                )
        elif name != "desktop":
            raise ConfigurationError(f"Unknown notification provider: {name}")


def resolve_provider_names(settings: Settings, override: Sequence[str] | None) -> tuple[str, ...]:
    """Return a normalized provider selection from CLI options or settings."""

    if not override:
        return settings.providers
    names: list[str] = []
    for value in override:
        names.extend(item.strip().lower() for item in value.split(",") if item.strip())
    return tuple(dict.fromkeys(names))
