import io
import unittest
from unittest.mock import patch

from codex_watch.main import main


class CliTests(unittest.TestCase):
    @patch.dict("os.environ", {"NOTIFICATION_PROVIDERS": "desktop"}, clear=True)
    def test_sample_dry_run_notification(self) -> None:
        with patch("sys.stdout", new_callable=io.StringIO) as output:
            result = main(
                [
                    "--env-file",
                    "missing.env",
                    "notify",
                    "--dry-run",
                    "--message",
                    "✅ Codex task completed",
                ]
            )
        self.assertEqual(result, 0)
        self.assertIn("✅ Codex task completed", output.getvalue())

    @patch.dict("os.environ", {"NOTIFICATION_PROVIDERS": "desktop"}, clear=True)
    @patch("codex_watch.main.run_codex", return_value=3)
    def test_wrapper_preserves_failure_exit_code(self, run: object) -> None:
        with patch("sys.stdout", new_callable=io.StringIO):
            result = main(
                ["--env-file", "missing.env", "run", "--dry-run", "test prompt"]
            )
        self.assertEqual(result, 3)


if __name__ == "__main__":
    unittest.main()
