# ⌚ Codex Watch Notifier

> Get notified on your phone and Apple Watch when Codex CLI finishes a task.  
> 当 Codex CLI 完成任务时，在手机和 Apple Watch 上收到提醒。

## Introduction | 项目简介

Codex Watch Notifier is a lightweight notification tool for Codex CLI. It uses Codex lifecycle hooks to capture the original task and sends a completion notification containing the task name and project context, so you do not need to keep checking the terminal.

Codex Watch Notifier 是一个面向 Codex CLI 的轻量级通知工具。它通过 Codex 生命周期 Hook 捕获原始任务，并在任务完成后发送包含任务名称和项目上下文的通知，让你无需一直查看终端。

## Features | 功能

- Codex lifecycle hook integration｜集成 Codex 生命周期 Hook
- Original task prompt capture｜捕获用户原始任务
- Project name and directory context｜显示项目名称和工作目录
- ntfy, desktop and Telegram providers｜支持 ntfy、桌面通知和 Telegram
- iPhone and Apple Watch notifications｜支持 iPhone 和 Apple Watch
- Fail-open behavior｜通知失败不会影响 Codex 正常完成任务

Example notification｜通知示例：

```text
✅ Codex Finished

Improve Codex Watch notification content
Project: codex-watch-notifier
Directory: C:\Projects\codex-watch-notifier
```

## How It Works | 工作原理

Codex Watch Notifier uses two lifecycle events:

```text
UserPromptSubmit → Save task context
Codex executes the task
Stop             → Send notification
```

The `Stop` event does not contain the original prompt, so the project stores it during `UserPromptSubmit` and retrieves it using `session_id + turn_id` when the task finishes.

由于 `Stop` 事件不包含原始 Prompt，本项目会在 `UserPromptSubmit` 阶段保存任务，并在任务完成时通过 `session_id + turn_id` 恢复对应上下文。

## Installation | 安装

### 1. Clone the repository | 克隆仓库

```bash
git clone https://github.com/H1234L1/codex-watch-notifier.git
cd codex-watch-notifier
```

### 2. Install the package | 安装项目

```bash
pip install -e .
```

### 3. Configure ntfy | 配置 ntfy

Copy `example.env` to `.env`:

```bash
cp example.env .env
```

Windows PowerShell:

```powershell
Copy-Item example.env .env
```

Edit `.env`:

```env
NOTIFICATION_PROVIDERS=ntfy
NTFY_SERVER_URL=https://ntfy.sh
NTFY_TOPIC=your-private-topic
NTFY_PRIORITY=default
```

Install the ntfy app on your iPhone, subscribe to the same topic, and enable ntfy notification mirroring in the Apple Watch app.

在 iPhone 上安装 ntfy，订阅相同 Topic，并在 Watch App 中开启 ntfy 通知镜像。

### 4. Configure Codex Hooks | 配置 Codex Hook

Example files are included:

```text
examples/hooks.windows.json
examples/hooks.posix.json
```

Copy the appropriate configuration to:

```text
~/.codex/hooks.json
```

Replace the script and `.env` paths with absolute paths to your local repository.

Windows command example:

```json
{
  "description": "Capture the current Codex prompt and notify when the turn stops.",
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python \"C:\\path\\to\\codex-watch-notifier\\scripts\\codex_complete.py\" --env-file \"C:\\path\\to\\codex-watch-notifier\\.env\" --provider ntfy",
            "timeout": 5
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python \"C:\\path\\to\\codex-watch-notifier\\scripts\\codex_complete.py\" --env-file \"C:\\path\\to\\codex-watch-notifier\\.env\" --provider ntfy",
            "timeout": 15
          }
        ]
      }
    ]
  }
}
```

Restart Codex, run `/hooks`, and trust both hooks:

```text
UserPromptSubmit
Stop
```

Both should show `Installed: 1` and `Active: 1`.

## Testing | 测试

Run the automated tests:

```bash
pytest
```

Current result:

```text
19 tests passed
```

You can also test ntfy manually:

```bash
echo '{"hook_event_name":"Stop","session_id":"manual-test","turn_id":"turn-1","stop_hook_active":false,"cwd":"."}' | python scripts/codex_complete.py --env-file .env --provider ntfy
```

Then run a real Codex task and confirm that the completion notification appears on your phone or Apple Watch.

## Apple Watch Notes | Apple Watch 说明

Notifications are delivered through the Internet:

```text
Codex → ntfy → iPhone → Apple Watch
```

There is no direct distance limit between the computer and Apple Watch. However, the iPhone or Apple Watch must have an available network connection.

电脑与 Apple Watch 之间没有直接距离限制，但 iPhone 或 Apple Watch 需要保持联网。

When the iPhone is unlocked and being used, iOS may display the notification only on the phone. Locking the iPhone makes Apple Watch vibration more reliable.

当 iPhone 正在解锁使用时，通知可能只显示在手机上；锁定 iPhone 后，Apple Watch 通常会更稳定地收到震动提醒。

## Project Structure | 项目结构

```text
codex-watch-notifier/
├── examples/
│   ├── hooks.posix.json
│   └── hooks.windows.json
├── scripts/
│   └── codex_complete.py
├── src/
│   └── codex_watch/
│       ├── config.py
│       ├── hook.py
│       ├── main.py
│       └── notifier/
│           ├── base.py
│           ├── ntfy.py
│           └── telegram.py
├── tests/
│   ├── test_config.py
│   ├── test_hook.py
│   └── test_notifiers.py
├── example.env
├── pyproject.toml
└── README.md
```

## License | 开源协议

This project is licensed under the MIT License.

本项目使用 MIT License。
