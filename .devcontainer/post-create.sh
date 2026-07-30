#!/usr/bin/env bash
# post-create.sh - one-time setup after the container is created.
#
# Installs Claude Code, makes the template's PowerShell tools runnable on
# Linux, and installs the sandbox settings as USER settings (project settings
# cannot enable sandbox.network.strictAllowlist - Claude Code ignores that key
# outside user / managed / CLI settings).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_HOME="${HOME}/.claude"

log() { printf '[post-create] %s\n' "$*"; }

# ------------------------------------------------------- mounted volumes
# Named volumes are created root-owned; without this the first write fails.
sudo chown -R "$(id -u):$(id -g)" "$CLAUDE_HOME" /commandhistory 2>/dev/null || true
mkdir -p "$CLAUDE_HOME"

# ------------------------------------------------------------ Claude Code
if ! command -v claude >/dev/null 2>&1; then
    log "installing @anthropic-ai/claude-code"
    npm install -g @anthropic-ai/claude-code
fi
log "claude: $(command -v claude || echo 'NOT INSTALLED')"

# --------------------------------------------------------------- pwsh alias
# The template's tools and hooks invoke 'powershell'; on Linux the binary is
# 'pwsh'. One symlink keeps .claude/tools/*.ps1 and .claude/hooks/*.ps1 usable.
if ! command -v powershell >/dev/null 2>&1 && command -v pwsh >/dev/null 2>&1; then
    sudo ln -sf "$(command -v pwsh)" /usr/local/bin/powershell
    log "linked powershell -> $(command -v pwsh)"
fi

# ------------------------------------------------------- sandbox settings
if [ ! -f "${CLAUDE_HOME}/settings.json" ]; then
    cp "${HERE}/claude-user-settings.json" "${CLAUDE_HOME}/settings.json"
    log "installed sandbox settings into ${CLAUDE_HOME}/settings.json"
elif ! diff -q "${HERE}/claude-user-settings.json" "${CLAUDE_HOME}/settings.json" >/dev/null 2>&1; then
    log "NOTE ${CLAUDE_HOME}/settings.json differs from the template version."
    log "     diff .devcontainer/claude-user-settings.json ${CLAUDE_HOME}/settings.json"
fi

# ------------------------------------------------------------- toolchains
if command -v uv >/dev/null 2>&1 && [ -f "pyproject.toml" ]; then
    uv sync || log "WARN uv sync failed - run it manually once the allowlist is right"
fi

# Warm the npx cache while the network is still wide open (the egress firewall
# is applied at postStart, and mermaid-cli is a large download).
if [ -x /usr/bin/chromium ]; then
    npx -y @mermaid-js/mermaid-cli --version >/dev/null 2>&1 \
        && log "mermaid-cli cached" \
        || log "WARN could not pre-cache mermaid-cli"
fi

# --------------------------------------------------------- optional lockdown
# Built with LOCK_DOWN_SUDO=true: from here on the only command the user (and
# therefore any agent) may run as root is the firewall script itself.
if [ -f /usr/local/etc/claude-lock-down-sudo ]; then
    sudo rm -f /etc/sudoers.d/vscode /etc/sudoers.d/1000
    log "blanket sudo removed (only /usr/local/bin/init-firewall.sh remains)"
fi

log "done. Layers: container + egress firewall (postStart) + Claude Code sandbox."
