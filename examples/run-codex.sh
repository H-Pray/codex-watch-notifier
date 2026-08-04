#!/usr/bin/env sh
# Minimal shell integration if you prefer not to use the Python wrapper command.
# Usage: ./examples/run-codex.sh "implement authentication"
codex exec "$1"
status=$?
if [ "$status" -eq 0 ]; then
  codex-watch notify --status success --message "✅ Codex task completed"
else
  codex-watch notify --status failure --message "❌ Codex task failed"
fi
exit "$status"
