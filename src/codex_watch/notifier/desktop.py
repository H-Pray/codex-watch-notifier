"""Native desktop notifications for Windows, macOS, and Linux."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess

from codex_watch.notifier.base import Notification, NotificationError, NotificationProvider


class DesktopNotifier(NotificationProvider):
    """Use tools already provided by the host operating system."""

    @property
    def name(self) -> str:
        return "desktop"

    def send(self, notification: Notification) -> None:
        system = platform.system()
        if system == "Windows":
            self._send_windows(notification)
        elif system == "Darwin":
            self._send_macos(notification)
        elif system == "Linux":
            self._send_linux(notification)
        else:
            raise NotificationError(f"Desktop notifications are not supported on {system}")

    @staticmethod
    def _run(command: list[str], *, env: dict[str, str] | None = None) -> None:
        try:
            completed = subprocess.run(
                command,
                env=env,
                check=False,
                capture_output=True,
                text=True,
                timeout=15,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise NotificationError(f"Desktop notification command failed: {exc}") from exc
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip() or "unknown error"
            raise NotificationError(detail)

    def _send_windows(self, notification: Notification) -> None:
        powershell = shutil.which("powershell") or shutil.which("pwsh")
        if not powershell:
            raise NotificationError("PowerShell is required for Windows desktop notifications")

        # Values travel through the child environment rather than being interpolated
        # into PowerShell code, so task output cannot become executable script text.
        child_env = os.environ.copy()
        child_env["CODEX_WATCH_NOTIFY_TITLE"] = notification.title
        child_env["CODEX_WATCH_NOTIFY_MESSAGE"] = notification.message
        script = (
            "$ErrorActionPreference = 'Stop'; "
            "Add-Type -AssemblyName System.Windows.Forms; "
            "Add-Type -AssemblyName System.Drawing; "
            "$n = New-Object System.Windows.Forms.NotifyIcon; "
            "$n.Icon = [System.Drawing.SystemIcons]::Information; "
            "$n.BalloonTipTitle = $env:CODEX_WATCH_NOTIFY_TITLE; "
            "$n.BalloonTipText = $env:CODEX_WATCH_NOTIFY_MESSAGE; "
            "$n.Visible = $true; $n.ShowBalloonTip(5000); "
            "Start-Sleep -Seconds 5; $n.Dispose()"
        )
        self._run([powershell, "-NoProfile", "-NonInteractive", "-Command", script], env=child_env)

    def _send_macos(self, notification: Notification) -> None:
        osascript = shutil.which("osascript")
        if not osascript:
            raise NotificationError("osascript is required for macOS desktop notifications")
        script = (
            "on run argv\n"
            "display notification (item 2 of argv) with title (item 1 of argv)\n"
            "end run"
        )
        self._run([osascript, "-e", script, notification.title, notification.message])

    def _send_linux(self, notification: Notification) -> None:
        notify_send = shutil.which("notify-send")
        if not notify_send:
            raise NotificationError(
                "notify-send was not found; install libnotify-bin (Debian/Ubuntu)"
            )
        self._run([notify_send, "--app-name=Codex Watch", notification.title, notification.message])
