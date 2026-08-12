# Configure Codex for workspace access while requiring user confirmation
# before modifying existing files or deleting files.

$ErrorActionPreference = "Stop"

$codexDirectory = Join-Path $env:USERPROFILE ".codex"
$configPath = Join-Path $codexDirectory "config.toml"
$agentsPath = Join-Path $codexDirectory "AGENTS.md"

New-Item -ItemType Directory -Path $codexDirectory -Force | Out-Null

# Update the top-level default_permissions setting without discarding other
# user configuration. Permission profiles and legacy sandbox_mode settings
# should not be mixed.
$configText = if (Test-Path -LiteralPath $configPath) {
    Get-Content -LiteralPath $configPath -Raw -Encoding UTF8
} else {
    ""
}

if ($configText -match '(?m)^\s*sandbox_mode\s*=|(?m)^\s*\[sandbox_workspace_write\]') {
    throw "config.toml contains legacy sandbox settings. Remove sandbox_mode and [sandbox_workspace_write] before using default_permissions."
}

if ($configText -match '(?m)^\s*default_permissions\s*=.*$') {
    $configText = $configText -replace '(?m)^\s*default_permissions\s*=.*$', 'default_permissions = ":workspace"'
} else {
    if ($configText.Length -gt 0 -and -not $configText.EndsWith("`n")) {
        $configText += "`r`n"
    }
    $configText = 'default_permissions = ":workspace"' + "`r`n" + $configText
}

Set-Content -LiteralPath $configPath -Value $configText -Encoding UTF8

$policyStart = '<!-- codex-confirm-existing-file-changes:start -->'
$policyEnd = '<!-- codex-confirm-existing-file-changes:end -->'
$policyBlock = @"
$policyStart
## File-change approval policy

- Reading files and listing directories inside the active workspace is allowed without asking.
- Creating a new file inside the active workspace is allowed when the user requested creation or implementation.
- Before modifying, overwriting, renaming, or moving any existing file, ask the user for explicit approval and wait for the response.
- Before deleting any file or directory, ask the user for explicit approval and wait for the response.
- Approval applies only to the exact files and change scope described in the request. If the scope expands, ask again.
$policyEnd
"@

$agentsText = if (Test-Path -LiteralPath $agentsPath) {
    Get-Content -LiteralPath $agentsPath -Raw -Encoding UTF8
} else {
    ""
}

$escapedStart = [regex]::Escape($policyStart)
$escapedEnd = [regex]::Escape($policyEnd)
$blockPattern = "(?s)$escapedStart.*?$escapedEnd"

if ($agentsText -match $blockPattern) {
    $agentsText = [regex]::Replace($agentsText, $blockPattern, $policyBlock)
} else {
    if ($agentsText.Length -gt 0 -and -not $agentsText.EndsWith("`n")) {
        $agentsText += "`r`n"
    }
    $agentsText += "`r`n$policyBlock`r`n"
}

Set-Content -LiteralPath $agentsPath -Value $agentsText -Encoding UTF8

Write-Host "Codex workspace permissions configured."
Write-Host "Config: $configPath"
Write-Host "Instructions: $agentsPath"
Write-Host "Restart Codex and open a new task for the changes to take effect."
Write-Warning "The confirmation rule is an agent instruction, not an OS-enforced separation between create, modify, and delete."
