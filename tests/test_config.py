from pathlib import Path
import tempfile
import unittest

from codex_watch.config import ConfigurationError, Settings, load_dotenv


class ConfigTests(unittest.TestCase):
    def test_environment_settings(self) -> None:
        settings = Settings.from_environment(
            {
                "NOTIFICATION_PROVIDERS": "desktop, telegram,desktop",
                "TELEGRAM_BOT_TOKEN": "token",
                "TELEGRAM_CHAT_ID": "123",
                "CODEX_COMMAND": "codex-test",
                "CODEX_ARGS": "exec --full-auto",
            }
        )
        self.assertEqual(settings.providers, ("desktop", "telegram"))
        self.assertEqual(settings.codex_args, ("exec", "--full-auto"))
        settings.validate_provider("telegram")

    def test_missing_telegram_values_are_rejected(self) -> None:
        settings = Settings.from_environment({"NOTIFICATION_PROVIDERS": "telegram"})
        with self.assertRaises(ConfigurationError):
            settings.validate_provider("telegram")

    def test_dotenv_does_not_replace_existing_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text('FIRST="from file"\nSECOND=two\n', encoding="utf-8")
            values = {"FIRST": "from environment"}
            load_dotenv(path, values)
        self.assertEqual(values, {"FIRST": "from environment", "SECOND": "two"})


if __name__ == "__main__":
    unittest.main()
