#!/usr/bin/env python3
"""Executable entry point for Codex prompt, approval, and Stop hooks."""

from __future__ import annotations

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from codex_watch.hook import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main(default_env_file=PROJECT_ROOT / ".env"))
