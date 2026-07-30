# Dev container image for running Claude Code with sandboxing enabled.
#
# Layers of containment (see .devcontainer/README.md):
#   1. the container itself   - the host filesystem is not reachable
#   2. the egress firewall    - default-deny outbound, allowlist only
#   3. Claude Code sandbox    - per-command bubblewrap + network proxy
#
# Everything the template's own tools need (PowerShell, Graphviz, optional
# Mermaid / PlantUML, Python via uv) is installed here so the checks that
# CLAUDE.md makes mandatory also run inside the container.

ARG BASE_IMAGE=mcr.microsoft.com/devcontainers/base:debian-12
FROM ${BASE_IMAGE}

ARG WITH_MERMAID=true
ARG WITH_PLANTUML=false

ENV DEBIAN_FRONTEND=noninteractive

# Base tooling + firewall tooling + sandbox dependencies.
#   iptables / ipset / dnsutils : egress allowlist (init-firewall.sh)
#   bubblewrap / socat          : Claude Code sandbox on Linux
#   graphviz                    : check_diagrams.ps1 (dot)
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        wget \
        jq \
        ripgrep \
        less \
        unzip \
        procps \
        iptables \
        ipset \
        iproute2 \
        dnsutils \
        bubblewrap \
        socat \
        graphviz \
        python3 \
        python3-venv \
    && rm -rf /var/lib/apt/lists/*

# Debian defaults iptables to the nft backend; the legacy backend is the one
# that behaves predictably inside containers.
RUN update-alternatives --set iptables /usr/sbin/iptables-legacy || true \
    && update-alternatives --set ip6tables /usr/sbin/ip6tables-legacy || true

# Chromium is what mermaid-cli drives; the CJK fonts keep Japanese labels
# from rendering as boxes (and therefore failing validation).
RUN if [ "${WITH_MERMAID}" = "true" ]; then \
        apt-get update && apt-get install -y --no-install-recommends \
            chromium fonts-noto-cjk \
        && rm -rf /var/lib/apt/lists/*; \
    fi

# PlantUML pulls in a JRE, so it is opt-in.
RUN if [ "${WITH_PLANTUML}" = "true" ]; then \
        apt-get update && apt-get install -y --no-install-recommends \
            default-jre-headless plantuml \
        && rm -rf /var/lib/apt/lists/*; \
    fi

# uv: the default runner for .claude/tools/*.py
RUN curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin sh

# The firewall script and its allowlist are installed root-owned and outside
# the workspace on purpose: an agent working in /workspaces cannot edit the
# egress policy. Changing the allowlist requires rebuilding the container.
COPY init-firewall.sh /usr/local/bin/init-firewall.sh
COPY allowed-domains.txt /usr/local/etc/claude-allowed-domains.txt
RUN chmod 0755 /usr/local/bin/init-firewall.sh \
    && chmod 0444 /usr/local/etc/claude-allowed-domains.txt

# The unprivileged user may always run the firewall script without a password
# (postStartCommand needs it). The base image additionally grants blanket sudo
# to 'vscode'; that stays by default so a human can install packages, and
# Claude is kept away from it with a permissions.deny rule instead.
# Set LOCK_DOWN_SUDO=true to drop the blanket rule after post-create runs -
# then the only privileged command in the container is the firewall script.
ARG LOCK_DOWN_SUDO=false

RUN echo 'vscode ALL=(root) NOPASSWD: /usr/local/bin/init-firewall.sh' \
        > /etc/sudoers.d/010-init-firewall \
    && chmod 0440 /etc/sudoers.d/010-init-firewall \
    && if [ "${LOCK_DOWN_SUDO}" = "true" ]; then \
           touch /usr/local/etc/claude-lock-down-sudo; \
       fi

# Shell history survives rebuilds through a named volume.
RUN mkdir -p /commandhistory && chown vscode:vscode /commandhistory

USER vscode
