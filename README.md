# codex-watch-notifier

`codex-watch-notifier` is a lightweight, open-source command-line tool that tells you
when a local Codex coding task finishes. Send the result to Telegram (and therefore
to a phone or mirrored smartwatch), show it on the desktop, or enable both.

```text
Local Codex
    ↓ exits
codex-watch wrapper
    ↓
Telegram and/or desktop notification
    ↓
Phone notification
    ↓ notification mirroring
Smartwatch vibration
```

The project has no third-party runtime dependencies. It supports Python 3.9 or newer.

## Why this exists

Coding agents can run long enough that watching the terminal wastes attention. Codex
Watch lets you step away while keeping the feedback loop short: start one command,
continue with something else, and receive a completion or failure notification.

The tool is project-independent. Install it once and use it from any directory where
you run the Codex CLI.

## Demo workflow

```console
$ codex-watch run "implement authentication system"
# Codex runs normally in this terminal...
Notification delivered via telegram.
```

On success:

```text
Codex Watch
✅ Codex task completed (42.3s)
```

On failure:

```text
Codex Watch
❌ Codex task failed with exit code 1 (8.7s)
```

The wrapper returns the original Codex exit code, making it safe to use in scripts.
A notification error is printed as a warning but never changes the Codex result.

## Installation

### From a clone

```bash
git clone https://github.com/H1234L1/codex-watch-notifier.git
cd codex-watch-notifier
python -m pip install .
```

For an editable developer installation:

```bash
python -m pip install -e .
```

[`pipx`](https://pipx.pypa.io/) is also a good fit for a global command-line tool:

```bash
pipx install .
```

Confirm the command is available:

```bash
codex-watch --version
```

## Configuration

Copy the example file and edit the copy. `.env` is ignored by Git.

macOS/Linux:

```bash
cp example.env .env
```

Windows PowerShell:

```powershell
Copy-Item example.env .env
```

The default configuration uses desktop notifications only:

```dotenv
NOTIFICATION_PROVIDERS=desktop
CODEX_COMMAND=codex
CODEX_ARGS=exec
CODEX_WATCH_TITLE=Codex Watch
```

Use Telegram, or both providers, with a comma-separated value:

```dotenv
NOTIFICATION_PROVIDERS=telegram
# or: NOTIFICATION_PROVIDERS=desktop,telegram

TELEGRAM_BOT_TOKEN=replace-with-your-token
TELEGRAM_CHAT_ID=replace-with-your-chat-id
```

Normal environment variables override values from `.env`. You can use another file
by placing the global option before the subcommand:

```bash
codex-watch --env-file ~/.config/codex-watch.env run "update dependencies"
```

Never commit a real bot token. If one is exposed, revoke it with BotFather and create
a replacement.

Validate configuration without sending anything:

```bash
codex-watch check
```

Send a safe dry-run sample:

```bash
codex-watch notify --dry-run --message "✅ Codex task completed"
```

Send a real test notification:

```bash
codex-watch notify --status success --message "✅ Codex Watch is connected"
```

You can override providers for one command:

```bash
codex-watch notify --provider telegram --message "Telegram test"
```

## Telegram setup

Telegram is the easiest cross-platform route from a local computer to a smartwatch.

1. Open Telegram and start a chat with **@BotFather**.
2. Send `/newbot`, follow the prompts, and copy the bot token.
3. Open a chat with the bot you created and send it any message such as `hello`.
4. In a browser, visit the following URL with your token substituted:

   ```text
   https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates
   ```

5. Find `message.chat.id` in the JSON response. That number is the chat ID.
6. Add both values to `.env`, set `NOTIFICATION_PROVIDERS=telegram`, and run:

   ```bash
   codex-watch notify --message "Codex Watch test"
   ```

For a group, add the bot to the group, send a group message, and inspect `getUpdates`.
Group chat IDs commonly begin with a minus sign.

### How smartwatch notifications work

Codex Watch sends a normal Telegram notification to the phone; it does not connect
directly to the watch. Smartwatches then use their normal phone-notification mirroring.

For Apple Watch:

1. Install Telegram on the paired iPhone and allow Telegram notifications in iOS.
2. Open the iPhone **Watch** app.
3. In **Notifications**, enable mirroring for Telegram.
4. Lock the iPhone or let its display sleep, then send a test notification.

Apple decides whether an alert appears on the iPhone or Watch based on device state.
Focus modes, notification summaries, muted Telegram chats, and Watch wrist detection
can affect delivery. Android watches have a similar notification-access or mirroring
setting in their companion application.

## Desktop notifications

No Python notification package is required:

- **Windows:** uses PowerShell plus the built-in Windows Forms notification icon.
- **macOS:** uses `osascript` and Notification Center. The terminal may ask for
  notification permission on first use.
- **Linux:** uses `notify-send`. On Debian/Ubuntu, install it with
  `sudo apt install libnotify-bin` if it is missing.

Test only the desktop provider:

```bash
codex-watch notify --provider desktop --message "Desktop test"
```

Windows Focus Assist, macOS Focus, or a Linux notification daemon can suppress or
delay desktop banners even when the command succeeds.

## Codex integration

### Recommended: wrapper command

The default invocation is equivalent to:

```bash
codex exec "your prompt"
```

Run it through Codex Watch:

```bash
codex-watch run "refactor the API client"
```

Extra Codex arguments can be passed after the prompt. Use `--` to make the boundary
explicit:

```bash
codex-watch run "fix the failing tests" -- --full-auto
```

If your Codex installation uses a different executable or arguments, configure them:

```dotenv
CODEX_COMMAND=/opt/homebrew/bin/codex
CODEX_ARGS=exec --full-auto
```

The executable can also be overridden once:

```bash
codex-watch run --codex-command /custom/path/codex "review this repository"
```

### Shell integration

The [`examples/run-codex.sh`](examples/run-codex.sh) and
[`examples/run-codex.ps1`](examples/run-codex.ps1) scripts show the underlying pattern:
run Codex, capture `$?` or `$LASTEXITCODE`, notify, and return the captured exit code.
This is useful for aliases, CI jobs, or integrating a different agent command.

### Hook integration

If a Codex release or another tool exposes a completion hook, invoke the direct
notification command from that hook:

```bash
codex-watch notify --status success --message "✅ Codex task completed"
```

Use `--status failure` and the matching message from an error hook. The `notify`
subcommand is independent of the Codex wrapper and works in any automation.

## Command reference

```text
codex-watch run [options] PROMPT [-- CODEX_ARGS...]
codex-watch notify [options]
codex-watch check [--provider desktop|telegram]
```

Run `codex-watch <command> --help` for all command-specific options.

## Architecture

```text
src/codex_watch/
├── config.py              # .env and environment configuration
├── main.py                # CLI and workflow orchestration
├── runner.py              # Codex subprocess execution
└── notifier/
    ├── base.py            # provider interface, models, fan-out service
    ├── desktop.py         # native Windows/macOS/Linux provider
    └── telegram.py        # Telegram Bot API provider
```

To add a provider:

1. Subclass `NotificationProvider` from `notifier/base.py`.
2. Implement `name` and `send(notification)`.
3. Add its configuration validation to `Settings.validate_provider`.
4. Register its constructor in `build_providers`.
5. Add focused tests and configuration documentation.

Provider failures are isolated, so one failed destination does not prevent another
from receiving the same event.

## Development and tests

The test suite uses the standard-library `unittest` package. Telegram and Codex are
mocked, so tests do not consume API calls or start a real agent task.

```bash
python -m unittest discover -s tests -v
```

Check all Python source files compile:

```bash
python -m compileall -q src tests
```

## Current limitations

- The wrapper detects completion when the Codex process exits; it does not inspect
  internal Codex events or distinguish partial task completion.
- Telegram requires internet access and stores a bot token locally.
- Desktop display is controlled by operating-system permissions and focus settings.
- Windows uses a temporary notification-area icon rather than a registered Windows
  app identity, so appearance and history vary by Windows version.
- Smartwatch behavior depends on the paired phone, wearable settings, and Telegram.
- This initial repository is not published to PyPI; install it from a clone or Git URL.

## Future extensions

- Discord, Slack, ntfy, Pushover, email, and generic webhook providers.
- A provider entry-point system so external packages can register plugins.
- Richer task context: prompt summary, repository name, duration thresholds, and logs.
- Native Windows App SDK toast registration and richer notification actions.
- Optional retry/backoff and a local delivery queue for temporary network failures.
- Official Codex event-hook integration when an appropriate stable hook is available.
- PyPI releases, signed artifacts, and CI across Windows, macOS, and Linux.

## Contributing

Issues and pull requests are welcome. Keep providers small, type-annotated, and easy
to test without real credentials. Do not add secrets, `.env`, or captured user prompts
to commits.

## License

[MIT](LICENSE)
