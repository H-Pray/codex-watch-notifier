"""Execute Codex and preserve its exit status."""

from __future__ import annotations

from collections.abc import Sequence
import subprocess


def run_codex(
    prompt: str,
    *,
    command: str,
    command_args: Sequence[str],
    extra_args: Sequence[str] = (),
) -> int:
    """Run Codex attached to the current terminal and return its exit code."""

    invocation = [command, *command_args, prompt, *extra_args]
    try:
        completed = subprocess.run(invocation, check=False)
    except FileNotFoundError:
        print(
            f"Codex executable not found: {command!r}. "
            "Set CODEX_COMMAND or pass --codex-command.",
        )
        return 127
    except OSError as exc:
        print(f"Could not start Codex: {exc}")
        return 126
    except KeyboardInterrupt:
        print("\nCodex task interrupted.")
        return 130
    return completed.returncode
