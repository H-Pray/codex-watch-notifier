import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from codex_watch.hook import (
    COMPLETION_MESSAGE,
    NOTIFICATION_TITLE,
    TaskContext,
    handle_stop_event,
    main,
)
from codex_watch.notifier.base import Notification, NotificationProvider, NotifierService


class RecordingProvider(NotificationProvider):
    def __init__(self) -> None:
        self.notifications: list[Notification] = []

    @property
    def name(self) -> str:
        return "recording"

    def send(self, notification: Notification) -> None:
        self.notifications.append(notification)


class FailingProvider(NotificationProvider):
    @property
    def name(self) -> str:
        return "failing"

    def send(self, notification: Notification) -> None:
        raise RuntimeError("delivery failed")


class HookTests(unittest.TestCase):
    def test_stop_event_includes_prompt_project_and_directory(self) -> None:
        provider = RecordingProvider()
        event = {
            "hook_event_name": "Stop",
            "stop_hook_active": False,
            "cwd": str(Path("C:/work/codex-watch-notifier")),
        }
        results = handle_stop_event(
            event,
            NotifierService([provider]),
            context=TaskContext("Improve completion notifications"),
        )
        self.assertTrue(results[0].delivered)
        notification = provider.notifications[0]
        self.assertEqual(notification.title, NOTIFICATION_TITLE)
        self.assertEqual(notification.title, "✅ Codex Finished")
        self.assertIn("Improve completion notifications", notification.message)
        self.assertIn("Project: codex-watch-notifier", notification.message)
        self.assertIn(f"Directory: {event['cwd']}", notification.message)

    def test_stop_event_uses_safe_fallback_without_prompt(self) -> None:
        provider = RecordingProvider()
        handle_stop_event(
            {"hook_event_name": "Stop", "stop_hook_active": False},
            NotifierService([provider]),
        )
        self.assertEqual(provider.notifications[0].message, COMPLETION_MESSAGE)
        self.assertEqual(provider.notifications[0].message, "Codex task completed")

    def test_non_stop_and_continued_stop_events_are_ignored(self) -> None:
        provider = RecordingProvider()
        service = NotifierService([provider])
        self.assertEqual(handle_stop_event({"hook_event_name": "SessionStart"}, service), [])
        self.assertEqual(
            handle_stop_event(
                {"hook_event_name": "Stop", "stop_hook_active": True},
                service,
            ),
            [],
        )
        self.assertEqual(provider.notifications, [])

    @patch("codex_watch.hook.build_providers")
    def test_prompt_is_captured_then_consumed_by_stop(self, build: object) -> None:
        provider = RecordingProvider()
        build.return_value = [provider]
        prompt_event = {
            "hook_event_name": "UserPromptSubmit",
            "session_id": "session-1",
            "turn_id": "turn-1",
            "prompt": "Add the task name to the watch notification",
            "cwd": "C:/work/watch-project",
        }
        stop_event = {
            "hook_event_name": "Stop",
            "session_id": "session-1",
            "turn_id": "turn-1",
            "stop_hook_active": False,
            "cwd": "C:/work/watch-project",
        }
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            "os.environ", {"NOTIFICATION_PROVIDERS": "desktop"}, clear=True
        ):
            state_dir = Path(directory)
            with patch("sys.stdout", io.StringIO()):
                self.assertEqual(
                    main([], input_stream=io.StringIO(json.dumps(prompt_event)), state_dir=state_dir),
                    0,
                )
                self.assertEqual(
                    main([], input_stream=io.StringIO(json.dumps(stop_event)), state_dir=state_dir),
                    0,
                )
            self.assertEqual(list(state_dir.iterdir()), [])

        self.assertEqual(len(provider.notifications), 1)
        self.assertIn(prompt_event["prompt"], provider.notifications[0].message)
        self.assertIn("Project: watch-project", provider.notifications[0].message)

    @patch("codex_watch.hook.build_providers", return_value=[])
    def test_hook_main_outputs_valid_stop_response(self, build: object) -> None:
        event = io.StringIO(json.dumps({"hook_event_name": "Stop"}))
        output = io.StringIO()
        with patch("sys.stdout", output), patch.dict(
            "os.environ", {"NOTIFICATION_PROVIDERS": "desktop"}, clear=True
        ):
            result = main(
                ["--env-file", str(Path("missing.env"))],
                input_stream=event,
            )
        self.assertEqual(result, 0)
        self.assertEqual(json.loads(output.getvalue()), {"continue": True, "suppressOutput": True})

    @patch("codex_watch.hook.build_providers", return_value=[FailingProvider()])
    def test_notification_failure_is_fail_open(self, build: object) -> None:
        event = io.StringIO(json.dumps({"hook_event_name": "Stop"}))
        output = io.StringIO()
        error = io.StringIO()
        with patch("sys.stdout", output), patch("sys.stderr", error), patch.dict(
            "os.environ", {"NOTIFICATION_PROVIDERS": "desktop"}, clear=True
        ):
            result = main([], input_stream=event)
        self.assertEqual(result, 0)
        self.assertTrue(json.loads(output.getvalue())["continue"])
        self.assertIn("notification failed", error.getvalue())

    def test_malformed_input_fails_open_with_valid_json(self) -> None:
        output = io.StringIO()
        error = io.StringIO()
        with patch("sys.stdout", output), patch("sys.stderr", error):
            result = main([], input_stream=io.StringIO("not json"))
        self.assertEqual(result, 0)
        self.assertTrue(json.loads(output.getvalue())["continue"])
        self.assertIn("notification skipped", error.getvalue())


if __name__ == "__main__":
    unittest.main()
