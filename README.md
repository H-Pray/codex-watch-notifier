# codex-watch-notifier

Receive an Apple Watch notification when local OpenAI Codex CLI needs approval or finishes a turn.

```text
Codex CLI
    ? PermissionRequest or Stop lifecycle hook
scripts/codex_complete.py
    ?
NtfyNotifier
    ?
ntfy server
    ?
iPhone notification
    ? notification mirroring
Apple Watch vibration
```

The notification includes the prompt and project context:

```text
? Codex Finished
Improve the Codex Watch notification system
Project: codex-watch-notifier
Directory: C:\work\codex-watch-notifier
```

If Codex cannot associate a prompt with the completed turn, the body falls back to
`Codex task completed`.

The tool uses Python 3.9 or newer and has no third-party runtime dependencies.

## Features

- Official Codex `UserPromptSubmit` prompt capture, `PermissionRequest` approval alerts, and `Stop` completion integration.
- ntfy notifications for iPhone and Apple Watch.
- Optional desktop notifications on Windows, macOS, and Linux.
- Optional Telegram provider retained for existing users.
- Environment-based configuration with `.env` support.
- A wrapper command for older or custom Codex workflows.
- Notification failures never prevent Codex from completing a turn.

## Quick start on Windows

Clone and enter the repository:

```powershell
git clone https://github.com/H1234L1/codex-watch-notifier.git
cd codex-watch-notifier
```

The hook script can run directly from the clone. Installing the package also makes
the `codex-watch` wrapper command available:

```powershell
python -m pip install .
```

Create your local configuration:

```powershell
Copy-Item example.env .env
notepad .env
```

Set at least these values:

```dotenv
NOTIFICATION_PROVIDERS=ntfy
NTFY_SERVER_URL=https://ntfy.sh
NTFY_TOPIC=codex-watch-2026
NTFY_TOKEN=
NTFY_PRIORITY=default
CODEX_WATCH_TITLE=Codex Watch
```

`.env` is ignored by Git and must not be committed.

## ntfy and Apple Watch setup

1. Install the ntfy app on the paired iPhone.
2. Subscribe to the same topic configured in `NTFY_TOPIC`.
3. Enable ntfy notifications in **iPhone Settings ? Notifications ? ntfy**.
4. Open the iPhone **Watch** app.
5. Open **My Watch ? Notifications**.
6. Under **Mirror iPhone Alerts From**, enable ntfy.
7. For a realistic test, wear and unlock the Watch, then lock the iPhone.

Apple normally sends an alert to either the unlocked iPhone or the Watch, not both.
When the iPhone is locked or asleep, the alert should be routed to the unlocked Watch.
Focus modes and muted app notifications can suppress the vibration.

### Topic security

Public ntfy topics have no access control unless you configure authentication. Anyone
who guesses a public topic name may be able to publish to or subscribe to it. Prefer a
long random topic for normal use, or configure `NTFY_TOKEN` with a protected/self-hosted
ntfy server.

## Test ntfy before configuring Codex

From the repository directory, simulate prompt capture, an approval request, and
completion with the same session and turn IDs:

```powershell
'{"hook_event_name":"UserPromptSubmit","session_id":"manual-test","turn_id":"turn-1","prompt":"Improve the Codex Watch notification","cwd":"C:\\work\\codex-watch-notifier"}' |
    python .\scripts\codex_complete.py --env-file .\.env --provider ntfy

'{"hook_event_name":"PermissionRequest","session_id":"manual-test","turn_id":"turn-1","tool_name":"shell_command","tool_input":{"command":"git push origin v1.0.0"},"cwd":"C:\\work\\codex-watch-notifier"}' |
    python .\scripts\codex_complete.py --env-file .\.env --provider ntfy

'{"hook_event_name":"Stop","session_id":"manual-test","turn_id":"turn-1","stop_hook_active":false,"cwd":"C:\\work\\codex-watch-notifier"}' |
    python .\scripts\codex_complete.py --env-file .\.env --provider ntfy
```

Expected console output:

```json
{"continue": true, "suppressOutput": true}
```

With the iPhone locked, your Apple Watch should first receive `?? Codex Needs Approval`,
then `? Codex Finished`. The hook JSON output is machine-readable and never includes
an allow or deny decision, so the real approval dialog remains in Codex.

You can also test ntfy without a hook payload after installing the package:

```powershell
codex-watch notify --provider ntfy --message "Codex completed!"
```

## Configure Codex prompt capture, approval, and completion hooks

Codex reads user-level hooks from:

```text
C:\Users\YOUR_NAME\.codex\hooks.json
```

Use a user-level hook so the notification works in every repository. Commands run with
the active Codex session directory as their working directory, so use absolute paths.

Create or merge this configuration, replacing all repository paths. `UserPromptSubmit` captures the documented `prompt` field; `PermissionRequest`
reads it without deleting it; `Stop` later consumes it and sends the completion
notification:

```json
{
  "description": "Capture the current Codex prompt and notify when the turn stops.",
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python \"C:\\absolute\\path\\to\\codex-watch-notifier\\scripts\\codex_complete.py\" --env-file \"C:\\absolute\\path\\to\\codex-watch-notifier\\.env\" --provider ntfy",
            "timeout": 5
          }
        ]
      }
    ],
    "PermissionRequest": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python \"C:\\absolute\\path\\to\\codex-watch-notifier\\scripts\\codex_complete.py\" --env-file \"C:\\absolute\\path\\to\\codex-watch-notifier\\.env\" --provider ntfy",
            "timeout": 15,
            "statusMessage": "Sending Codex approval notification"
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python \"C:\\absolute\\path\\to\\codex-watch-notifier\\scripts\\codex_complete.py\" --env-file \"C:\\absolute\\path\\to\\codex-watch-notifier\\.env\" --provider ntfy",
            "timeout": 15,
            "statusMessage": "Sending Codex completion notification"
          }
        ]
      }
    ]
  }
}
```

The prompt is cached by `session_id` and `turn_id` in the operating-system temporary
directory. `PermissionRequest` performs a non-destructive read, so later approval
requests and the final `Stop` can reuse it. Only the matching `Stop` deletes it.
No transcript parsing is used.

Approval notifications use high ntfy priority and this exact shape (the Tool, Project,
or Directory lines are omitted only when unavailable):

```text
?? Codex Needs Approval
Original task prompt
Action: sanitized and truncated command or action
Tool: tool_name
Project: project-folder
Directory: full working directory
```

Only the allowlisted `command`, `description`, or `action` field is considered.
The entire `tool_input` object and any `env` object are never serialized. Common
tokens, authorization values, URL credentials, and shell environment assignments are
redacted; task, action, and tool text are length-limited.

A ready-to-edit template is available at
[`examples/hooks.windows.json`](examples/hooks.windows.json). macOS and Linux users can
start with [`examples/hooks.posix.json`](examples/hooks.posix.json).

Important: do not replace an existing `notify = [...]` setting in
`~/.codex/config.toml`. These lifecycle hooks are additive and can coexist with Codex Computer
Use or another existing notification command.

After creating or changing `hooks.json`:

1. Start Codex CLI.
2. Run `/hooks`.
3. Review and trust the `UserPromptSubmit`, `PermissionRequest`, and `Stop` hooks.
4. Exit and start a new Codex turn if requested by the CLI.

Codex records trust against the hook definition. If the command changes later, open
`/hooks` and approve the new definition again. See the
[official Codex hooks documentation](https://developers.openai.com/codex/hooks).

## End-to-end Codex test on Windows

PowerShell may choose the npm `codex.ps1` shim, which can be blocked by execution
policy. Calling `codex.cmd` avoids that issue:

```powershell
codex.cmd exec "Reply with only: done"
```

When the turn stops, the hook sends the original prompt and working-directory context through ntfy. Lock the iPhone
before running the command if you want the alert to appear on Apple Watch rather than
the phone.

## Configuration reference

| Variable | Default | Purpose |
| --- | --- | --- |
| `NOTIFICATION_PROVIDERS` | `desktop` | Comma-separated provider names: `ntfy`, `desktop`, `telegram` |
| `NTFY_SERVER_URL` | `https://ntfy.sh` | ntfy server base URL |
| `NTFY_TOPIC` | none | Required ntfy topic |
| `NTFY_TOKEN` | none | Optional bearer token for protected topics |
| `NTFY_PRIORITY` | `default` | ntfy priority, such as `default` or `high` |
| `CODEX_WATCH_TITLE` | `Codex Watch` | Wrapper/manual notification title; the completion hook uses `? Codex Finished` |
| `TELEGRAM_BOT_TOKEN` | none | Required only for the optional Telegram provider |
| `TELEGRAM_CHAT_ID` | none | Required only for the optional Telegram provider |
| `CODEX_COMMAND` | `codex` | Executable used by the wrapper command |
| `CODEX_ARGS` | `exec` | Arguments placed before the wrapper prompt |

Real environment variables take precedence over `.env` values.

## Optional providers

Use ntfy and desktop together:

```dotenv
NOTIFICATION_PROVIDERS=ntfy,desktop
```

Send one desktop test:

```powershell
codex-watch notify --provider desktop --message "Desktop test"
```

Telegram remains supported for existing users:

```dotenv
NOTIFICATION_PROVIDERS=telegram
TELEGRAM_BOT_TOKEN=replace-with-your-token
TELEGRAM_CHAT_ID=replace-with-your-chat-id
```

```powershell
codex-watch notify --provider telegram --message "Telegram test"
```

No Telegram configuration is needed for the ntfy/Apple Watch workflow.

## Wrapper command

The official Stop hook is recommended. The existing wrapper remains useful when hooks
are unavailable or when wrapping another Codex executable:

```powershell
codex-watch run "refactor the API client"
```

It executes `codex exec <prompt>`, sends success or failure notifications after the
process exits, and preserves the original Codex exit code.

## Architecture

```text
src/codex_watch/
??? config.py
??? hook.py                   # Prompt capture, approval, and Stop handling
??? main.py                   # codex-watch CLI
??? runner.py                 # optional Codex wrapper
??? notifier/
    ??? base.py               # provider interface and fan-out service
    ??? ntfy.py               # ntfy HTTP backend
    ??? desktop.py            # Windows/macOS/Linux desktop backend
    ??? telegram.py           # optional Telegram backend

scripts/
??? codex_complete.py         # executable lifecycle-hook entry point
```

Codex event parsing never lives in the ntfy provider. This keeps notification delivery
replaceable and makes the hook independently testable.

## Development and tests

Unit tests mock network requests and do not send real ntfy or Telegram messages:

```powershell
$env:PYTHONPATH = "$PWD\src"
python -B -m unittest discover -s tests -v
```

Check source compilation:

```powershell
python -m compileall -q src scripts tests
```

## Troubleshooting

### Direct test works but Codex sends nothing

- Run `/hooks` and trust the hook definition.
- Confirm `C:\Users\YOUR_NAME\.codex\hooks.json` contains `UserPromptSubmit`,
  `PermissionRequest`, and `Stop` entries.
- Use absolute paths in the hook command.
- Confirm Python is available in the environment used to launch Codex.
- Run the hook command manually with the test JSON shown above.

### iPhone receives it but Apple Watch does not vibrate

- Lock the iPhone before testing.
- Ensure the Watch is worn and unlocked.
- Enable ntfy under **Watch ? Notifications ? Mirror iPhone Alerts From**.
- Check Focus modes and ntfy notification permissions.

### ntfy returns an authorization error

- Remove `NTFY_TOKEN` for an unprotected public topic.
- For a protected topic, verify the bearer token and server URL.
- Confirm the token has permission to publish to the selected topic.

## License

[MIT](LICENSE)
