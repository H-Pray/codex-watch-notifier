import io
from email.header import decode_header, make_header
import unittest
from unittest.mock import MagicMock, patch

from codex_watch.notifier.base import (
    Notification,
    NotificationProvider,
    NotificationStatus,
    NotifierService,
)
from codex_watch.notifier.ntfy import NtfyNotifier
from codex_watch.notifier.telegram import TelegramNotifier


class StubProvider(NotificationProvider):
    def __init__(self, should_fail: bool = False) -> None:
        self.should_fail = should_fail

    @property
    def name(self) -> str:
        return "stub"

    def send(self, notification: Notification) -> None:
        if self.should_fail:
            raise RuntimeError("delivery failed")


class NotifierTests(unittest.TestCase):
    def test_service_isolates_provider_failure(self) -> None:
        results = NotifierService([StubProvider(True), StubProvider(False)]).send(
            Notification("title", "message")
        )
        self.assertFalse(results[0].delivered)
        self.assertTrue(results[1].delivered)

    def test_dry_run_does_not_call_provider(self) -> None:
        provider = MagicMock(spec=StubProvider)
        provider.name = "stub"
        with patch("sys.stdout", new_callable=io.StringIO) as output:
            results = NotifierService([provider]).send(
                Notification("title", "message"), dry_run=True
            )
        provider.send.assert_not_called()
        self.assertIn("[dry-run] stub", output.getvalue())
        self.assertTrue(results[0].delivered)

    @patch("codex_watch.notifier.telegram.urlopen")
    def test_telegram_posts_message(self, urlopen: MagicMock) -> None:
        response = MagicMock()
        response.read.return_value = b'{"ok": true}'
        urlopen.return_value.__enter__.return_value = response
        TelegramNotifier("secret", "123").send(Notification("Codex Watch", "done"))
        request = urlopen.call_args.args[0]
        self.assertEqual(request.method, "POST")
        self.assertIn(b"chat_id=123", request.data)
        self.assertIn(b"done", request.data)

    @patch("codex_watch.notifier.ntfy.urlopen")
    def test_ntfy_posts_message(self, urlopen: MagicMock) -> None:
        response = MagicMock()
        response.read.return_value = b'{"id": "message-id"}'
        urlopen.return_value.__enter__.return_value = response

        NtfyNotifier(
            "https://ntfy.example/",
            "private-topic",
            token="secret",
            priority="default",
        ).send(
            Notification(
                "✅ Codex Finished",
                "Task and project context",
                status=NotificationStatus.SUCCESS,
            )
        )

        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://ntfy.example/private-topic")
        self.assertEqual(request.method, "POST")
        self.assertEqual(request.data.decode("utf-8"), "Task and project context")
        self.assertEqual(request.get_header("Authorization"), "Bearer secret")
        self.assertEqual(request.get_header("X-priority"), "high")
        title = str(make_header(decode_header(request.get_header("X-title"))))
        self.assertEqual(title, "✅ Codex Finished")

    @patch("codex_watch.notifier.ntfy.urlopen")
    def test_ntfy_keeps_configured_priority_for_non_completion(
        self, urlopen: MagicMock
    ) -> None:
        urlopen.return_value.__enter__.return_value = MagicMock()

        NtfyNotifier("https://ntfy.example", "topic", priority="low").send(
            Notification("Information", "Still running")
        )

        request = urlopen.call_args.args[0]
        self.assertEqual(request.get_header("X-priority"), "low")


if __name__ == "__main__":
    unittest.main()
