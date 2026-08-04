param(
    [Parameter(Mandatory = $true)]
    [string]$Prompt
)

# Minimal PowerShell integration if you prefer not to use the Python wrapper.
codex exec $Prompt
$CodexExitCode = $LASTEXITCODE
if ($CodexExitCode -eq 0) {
    codex-watch notify --status success --message "✅ Codex task completed"
} else {
    codex-watch notify --status failure --message "❌ Codex task failed"
}
exit $CodexExitCode
