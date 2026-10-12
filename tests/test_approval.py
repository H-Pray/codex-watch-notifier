import io
import json
import unittest
from unittest.mock import MagicMock, patch

from codex_watch.approval import create_approval_request, wait_for_decision


class ApprovalTests(unittest.TestCase):
    def test_request_has_two_one_shot_actions(self) -> None:
        request = create_approval_request("https://ntfy.example")
        self.assertEqual([action.label for action in request.actions], ["ALLOW", "DENY"])
        self.assertTrue(all(action.url.endswith(request.response_topic) for action in request.actions))

    @patch("codex_watch.approval.urlopen")
    def test_wait_for_approve(self, urlopen: MagicMock) -> None:
        response = MagicMock()
        response.readline.side_effect = [
            b'{"event":"message","message":"approve"}\n',
        ]
        urlopen.return_value.__enter__.return_value = response
        decision = wait_for_decision("https://ntfy.example", "reply-topic", timeout=1)
        self.assertEqual(decision.behavior, "allow")

if __name__ == "__main__":
    unittest.main()
