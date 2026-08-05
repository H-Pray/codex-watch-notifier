import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from codex_watch.hook import (
    APPROVAL_MESSAGE,
    APPROVAL_NOTIFICATION_TITLE,
    COMPLETION_MESSAGE,
    NOTIFICATION_TITLE,
    TaskContext,
    handle_permission_request_event,
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
        self.assertEqual(notification.title, "? Codex Finished")
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

    def test_permission_request_includes_context_and_safe_action(self) -> None:
        provider = RecordingProvider()
        event = {
            "hook_event_name": "PermissionRequest",
            "cwd": "C:/work/codex-watch-notifier",
            "tool_name": "shell_command",
            "tool_input": {
                "command": (
                    "GH_TOKEN=top-secret git push origin v1.0.0 "
                    "--authorization Bearer-secret"
                ),
                "env": {"PRIVATE_TOKEN": "must-never-appear"},
            },
        }

        results = handle_permission_request_event(
            event,
            NotifierService([provider]),
            context=TaskContext("Push version tag to GitHub"),
        )

        self.assertTrue(results[0].delivered)
        notification = provider.notifications[0]
        self.assertEqual(notification.title, APPROVAL_NOTIFICATION_TITLE)
        self.assertEqual(notification.title, "?? Codex Needs Approval")
        self.assertIn("Push version tag to GitHub", notification.message)
        self.assertIn(
            "Action: GH_TOKEN=[REDACTED] git push origin v1.0.0 "
            "--authorization [REDACTED]",
            notification.message,
        )
        self.assertIn("Tool: shell_command", notification.message)
        self.assertIn("Project: codex-watch-notifier", notification.message)
        self.assertIn("Directory: C:/work/codex-watch-notifier", notification.message)
        self.assertNotIn("top-secret", notification.message)
        self.assertNotIn("must-never-appear", notification.message)

    def test_permission_request_fallback_and_action_truncation(self) -> None:
        provider = RecordingProvider()
        handle_permission_request_event(
            {
                "hook_event_name": "PermissionRequest",
                "tool_name": "custom_tool",
                "tool_input": {"command": "x" * 500},
            },
            NotifierService([provider]),
        )
        message = provider.notifications[0].message
        self.assertIn(APPROVAL_MESSAGE, message)
        action = message.splitlines()[1].removeprefix("Action: ")
        self.assertLessEqual(len(action), 180)
        self.assertTrue(action.endswith("?"))

    @patch("codex_watch.hook.build_providers")
    def test_permission_request_does_not_consume_prompt_before_stop(
        self, build: object
    ) -> None:
        provider = RecordingProvider()
        build.return_value = [provider]
        common = {
            "session_id": "session-approval",
            "turn_id": "turn-approval",
            "cwd": "C:/work/watch-project",
        }
        events = [
            {
                **common,
                "hook_event_name": "UserPromptSubmit",
                "prompt": "Push version tag to GitHub",
            },
            {
                **common,
                "hook_event_name": "PermissionRequest",
                "tool_name": "shell_command",
                "tool_input": {"command": "git push origin v1.0.0"},
            },
            {
                **common,
                "hook_event_name": "Stop",
                "stop_hook_active": False,
            },
        ]
        outputs: list[dict[str, object]] = []
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            "os.environ", {"NOTIFICATION_PROVIDERS": "desktop"}, clear=True
        ):
            state_dir = Path(directory)
            for event in events:
                output = io.StringIO()
                with patch("sys.stdout", output):
                    self.assertEqual(
                        main(
                            [],
                            input_stream=io.StringIO(json.dumps(event)),
                            state_dir=state_dir,
                        ),
                        0,
                    )
                outputs.append(json.loads(output.getvalue()))
                if event["hook_event_name"] == "PermissionRequest":
                    self.assertEqual(len(list(state_dir.iterdir())), 1)
            self.assertEqual(list(state_dir.iterdir()), [])

        self.assertEqual(outputs[1], {"continue": True, "suppressOutput": True})
        self.assertEqual(len(provider.notifications), 2)
        self.assertEqual(provider.notifications[0].title, APPROVAL_NOTIFICATION_TITLE)
        self.assertEqual(provider.notifications[1].title, NOTIFICATION_TITLE)
        self.assertIn("Push version tag to GitHub", provider.notifications[0].message)
        self.assertIn("Push version tag to GitHub", provider.notifications[1].message)

    @patch("codex_watch.hook.build_providers", return_value=[FailingProvider()])
    def test_permission_notification_failure_is_fail_open(self, build: object) -> None:
        event = {
            "hook_event_name": "PermissionRequest",
            "tool_name": "shell_command",
            "tool_input": {"command": "git push"},
        }
        output = io.StringIO()
        error = io.StringIO()
        with patch("sys.stdout", output), patch("sys.stderr", error), patch.dict(
            "os.environ", {"NOTIFICATION_PROVIDERS": "desktop"}, clear=True
        ):
            result = main([], input_stream=io.StringIO(json.dumps(event)))
        self.assertEqual(result, 0)
        self.assertTrue(json.loads(output.getvalue())["continue"])
        self.assertIn("notification failed", error.getvalue())

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
