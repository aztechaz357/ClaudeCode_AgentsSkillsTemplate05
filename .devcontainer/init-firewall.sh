#!/usr/bin/env bash
# init-firewall.sh - default-deny egress with a domain allowlist.
#
# Runs as root from postStartCommand on every container start (iptables rules
# do not survive a restart). Anything the agent - or code it runs - tries to
# reach outside the allowlist is dropped at the container boundary.
#
# The allowlist is resolved to IPs once, here. Name-based control is the job
# of the Claude Code sandbox (sandbox.network.allowedDomains); the two layers
# are complementary, see .devcontainer/README.md.
#
# Exit code: 0 = rules applied and verified
#            1 = failed (the container is then WITHOUT egress protection;
#                treat it as a hard error, not a warning)
set -euo pipefail
IFS=$'\n\t'

DOMAIN_FILE="${DOMAIN_FILE:-/usr/local/etc/claude-allowed-domains.txt}"
IPSET_NAME="${IPSET_NAME:-claude-allowed}"
WITH_GITHUB_META="${WITH_GITHUB_META:-true}"
VERIFY_BLOCKED_URL="${VERIFY_BLOCKED_URL:-https://example.com}"
VERIFY_ALLOWED_URL="${VERIFY_ALLOWED_URL:-https://api.anthropic.com}"

log() { printf '[init-firewall] %s\n' "$*"; }
die() { printf '[init-firewall] ERROR: %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "must run as root (sudo /usr/local/bin/init-firewall.sh)"
[ -r "$DOMAIN_FILE" ] || die "allowlist not readable: $DOMAIN_FILE"

# ---------------------------------------------------------------- discovery
# Everything that needs the network must happen BEFORE the DROP policy.
HOST_GW="$(ip route | awk '/^default/ {print $3; exit}')"
[ -n "$HOST_GW" ] || die "cannot determine the default gateway"

# The kernel route for the container's own interface is already in canonical
# CIDR form (e.g. 172.17.0.0/16); deriving it from the gateway address by
# hand produces masks that iptables rejects.
HOST_NET="$(ip route | awk '/proto kernel/ && /src/ {print $1; exit}')"
[ -n "$HOST_NET" ] || die "cannot determine the container subnet"

DNS_SERVERS="$(awk '/^nameserver/ {print $2}' /etc/resolv.conf || true)"
[ -n "$DNS_SERVERS" ] || die "no nameserver found in /etc/resolv.conf"

ALLOWED_IPS=""

add_domain() {
    local domain="$1" ips

    # An entry that is already an address or CIDR (a LAN service such as a
    # local LLM host) is used as-is; dig would return nothing for it.
    if echo "$domain" | grep -qE '^[0-9]+(\.[0-9]+){3}(/[0-9]+)?$'; then
        ALLOWED_IPS="${ALLOWED_IPS}${domain}"$'\n'
        log "literal address ${domain}"
        return 0
    fi

    ips="$(dig +short +time=3 +tries=2 A "$domain" | grep -E '^[0-9]+(\.[0-9]+){3}$' || true)"
    if [ -z "$ips" ]; then
        log "WARN could not resolve ${domain} - skipped"
        return 0
    fi
    ALLOWED_IPS="${ALLOWED_IPS}${ips}"$'\n'
    log "resolved ${domain} -> $(echo "$ips" | tr '\n' ' ')"
}

while IFS= read -r line || [ -n "$line" ]; do
    domain="$(echo "$line" | sed 's/#.*//' | tr -d '[:space:]')"
    [ -n "$domain" ] || continue
    add_domain "$domain"
done < "$DOMAIN_FILE"

# GitHub publishes its egress ranges; without them git over HTTPS is flaky
# because the CDN answers from a wide pool.
if [ "$WITH_GITHUB_META" = "true" ]; then
    meta="$(curl -fsSL --max-time 10 https://api.github.com/meta || true)"
    if [ -n "$meta" ]; then
        ranges="$(echo "$meta" | jq -r '[.git[]?, .api[]?, .web[]?] | .[]' 2>/dev/null |
                  grep -E '^[0-9]+(\.[0-9]+){3}/[0-9]+$' || true)"
        if [ -n "$ranges" ]; then
            ALLOWED_IPS="${ALLOWED_IPS}${ranges}"$'\n'
            log "added $(echo "$ranges" | wc -l) GitHub ranges from api.github.com/meta"
        fi
    else
        log "WARN api.github.com/meta unavailable - continuing with resolved A records only"
    fi
fi

[ -n "$(echo "$ALLOWED_IPS" | tr -d '[:space:]')" ] || die "allowlist resolved to nothing - refusing to apply a rule set that blocks everything"

# ------------------------------------------------------------------- apply
iptables -F
iptables -X
iptables -t nat -F
iptables -t nat -X
iptables -t mangle -F
iptables -t mangle -X

ipset destroy "$IPSET_NAME" 2>/dev/null || true
ipset create "$IPSET_NAME" hash:net

while IFS= read -r entry; do
    [ -n "$entry" ] || continue
    ipset add "$IPSET_NAME" "$entry" -exist
done <<< "$ALLOWED_IPS"

iptables -P INPUT DROP
iptables -P FORWARD DROP
iptables -P OUTPUT DROP

iptables -A INPUT -i lo -j ACCEPT
iptables -A OUTPUT -o lo -j ACCEPT

iptables -A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
iptables -A OUTPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT

for dns in $DNS_SERVERS; do
    iptables -A OUTPUT -d "$dns" -p udp --dport 53 -j ACCEPT
    iptables -A OUTPUT -d "$dns" -p tcp --dport 53 -j ACCEPT
done

# The VS Code server and forwarded ports talk to the host network.
iptables -A INPUT -s "$HOST_NET" -j ACCEPT
iptables -A OUTPUT -d "$HOST_NET" -j ACCEPT

iptables -A OUTPUT -m set --match-set "$IPSET_NAME" dst -j ACCEPT

# IPv6 would be a hole in an IPv4-only allowlist.
if command -v ip6tables >/dev/null 2>&1; then
    ip6tables -P INPUT DROP 2>/dev/null || true
    ip6tables -P FORWARD DROP 2>/dev/null || true
    ip6tables -P OUTPUT DROP 2>/dev/null || true
    ip6tables -A INPUT -i lo -j ACCEPT 2>/dev/null || true
    ip6tables -A OUTPUT -o lo -j ACCEPT 2>/dev/null || true
fi

log "rules applied ($(ipset list "$IPSET_NAME" | grep -c '^[0-9]' || true) allowlist entries)"

# ------------------------------------------------------------------ verify
# A firewall that silently does nothing is worse than none: prove both
# directions before reporting success.
if curl -s -o /dev/null --max-time 5 "$VERIFY_BLOCKED_URL"; then
    die "verification failed: ${VERIFY_BLOCKED_URL} is still reachable"
fi
log "OK blocked: ${VERIFY_BLOCKED_URL} is unreachable"

code="$(curl -s -o /dev/null --max-time 10 -w '%{http_code}' "$VERIFY_ALLOWED_URL" || true)"
if [ "$code" = "000" ] || [ -z "$code" ]; then
    die "verification failed: ${VERIFY_ALLOWED_URL} is not reachable (allowlist too tight?)"
fi
log "OK allowed: ${VERIFY_ALLOWED_URL} answered with HTTP ${code}"

log "egress firewall active"
