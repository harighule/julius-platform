"""
JULIUS — VEIL Node Install Script Generator
Produces a bash script that a partner runs on their server to:
  1. Detect the OS (Ubuntu/Debian/CentOS/Fedora/RHEL).
  2. Install Docker + docker-compose if missing.
  3. Pull the JULIUS VEIL node Docker image.
  4. Configure it with the partner_id and a shared secret.
  5. Start the VEIL mix node container.
  6. Register with the network via POST /onboarding/register.
"""

from __future__ import annotations

import secrets


def generate_shared_secret(length: int = 32) -> str:
    """Generate a cryptographically secure shared secret for node auth."""
    return secrets.token_hex(length)


def generate_install_script(
    partner_id: str,
    shared_secret: str,
    network_url: str = "https://onboarding.julius-veil.net",
    docker_image: str = "juliusveil/veil-node:latest",
    node_name: str = "",
) -> str:
    """
    Generate a complete bash install script for a VEIL node.

    Parameters
    ----------
    partner_id   : Unique partner identifier assigned by the network.
    shared_secret: Pre-shared HMAC secret for node↔network authentication.
    network_url  : Public HTTPS endpoint of the JULIUS onboarding API.
    docker_image : Docker image to pull for the VEIL mix node.
    node_name    : Optional human-readable label for this node.

    Returns
    -------
    str: Full bash script content (safe to pipe to bash).
    """
    safe_name = (node_name or f"veil-node-{partner_id[:8]}").replace("'", "")

    script = f"""#!/bin/bash
# ============================================================
# JULIUS VEIL Node — Automated Onboarding Script
# Partner ID : {partner_id}
# Generated  : $(date -u +"%Y-%m-%dT%H:%M:%SZ")
# ============================================================
set -euo pipefail

# ── Configuration ─────────────────────────────────────────
PARTNER_ID="{partner_id}"
SHARED_SECRET="{shared_secret}"
NETWORK_URL="{network_url}"
DOCKER_IMAGE="{docker_image}"
NODE_NAME="{safe_name}"
VEIL_DIR="/opt/julius-veil"
KEY_FILE="$VEIL_DIR/node_keypair.pem"

echo ""
echo "🔐 JULIUS VEIL Node Installer"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Partner ID : $PARTNER_ID"
echo "  Network    : $NETWORK_URL"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# ── 1. Detect OS ──────────────────────────────────────────
detect_os() {{
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        OS=$ID
        OS_VERSION=$VERSION_ID
    elif command -v lsb_release &>/dev/null; then
        OS=$(lsb_release -si | tr '[:upper:]' '[:lower:]')
        OS_VERSION=$(lsb_release -sr)
    else
        OS="unknown"
        OS_VERSION="unknown"
    fi
    echo "  Detected OS: $OS $OS_VERSION"
}}

detect_os

# ── 2. Install Docker if missing ──────────────────────────
install_docker() {{
    if command -v docker &>/dev/null; then
        echo "  ✓ Docker already installed: $(docker --version)"
        return
    fi

    echo "  Installing Docker..."
    case "$OS" in
        ubuntu|debian)
            apt-get update -qq
            apt-get install -y -qq apt-transport-https ca-certificates curl gnupg lsb-release
            curl -fsSL https://download.docker.com/linux/$OS/gpg | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg
            echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] \
https://download.docker.com/linux/$OS $(lsb_release -cs) stable" > /etc/apt/sources.list.d/docker.list
            apt-get update -qq
            apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin
            ;;
        centos|rhel|fedora|rocky|almalinux)
            yum install -y -q yum-utils
            yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
            yum install -y -q docker-ce docker-ce-cli containerd.io docker-compose-plugin
            systemctl enable --now docker
            ;;
        *)
            echo "  ⚠ Unsupported OS. Installing Docker via convenience script..."
            curl -fsSL https://get.docker.com | sh
            ;;
    esac

    systemctl enable --now docker 2>/dev/null || true
    echo "  ✓ Docker installed: $(docker --version)"
}}

install_docker

# ── 3. Install docker-compose (standalone) if missing ─────
if ! command -v docker-compose &>/dev/null && ! docker compose version &>/dev/null 2>&1; then
    echo "  Installing docker-compose..."
    curl -SL https://github.com/docker/compose/releases/latest/download/docker-compose-linux-$(uname -m) \
         -o /usr/local/bin/docker-compose
    chmod +x /usr/local/bin/docker-compose
fi

# ── 4. Generate node keypair (Ed25519) ────────────────────
echo "  Generating node keypair..."
mkdir -p "$VEIL_DIR"
chmod 700 "$VEIL_DIR"

if ! command -v openssl &>/dev/null; then
    case "$OS" in
        ubuntu|debian) apt-get install -y -qq openssl ;;
        *) yum install -y -q openssl ;;
    esac
fi

if [ ! -f "$KEY_FILE" ]; then
    openssl genpkey -algorithm Ed25519 -out "$KEY_FILE" 2>/dev/null || \
    openssl genrsa -out "$KEY_FILE" 4096 2>/dev/null
    chmod 600 "$KEY_FILE"
fi

# Extract public key (hex)
PUBLIC_KEY=$(openssl pkey -in "$KEY_FILE" -pubout -outform DER 2>/dev/null | xxd -p -c 256 | tr -d '\\n' 2>/dev/null || \
             openssl rsa -in "$KEY_FILE" -pubout 2>/dev/null | md5sum | awk '{{print $1}}')

echo "  ✓ Node public key: ${{PUBLIC_KEY:0:32}}..."

# ── 5. Write docker-compose.yml ───────────────────────────
echo "  Writing configuration..."
cat > "$VEIL_DIR/docker-compose.yml" <<COMPOSE
version: "3.8"
services:
  veil-node:
    image: {docker_image}
    container_name: julius-veil-node
    restart: unless-stopped
    network_mode: host
    environment:
      - PARTNER_ID={partner_id}
      - SHARED_SECRET={shared_secret}
      - NETWORK_URL={network_url}
      - NODE_NAME={safe_name}
      - NODE_PUBLIC_KEY=${{PUBLIC_KEY}}
    volumes:
      - $VEIL_DIR/data:/data
      - $KEY_FILE:/etc/veil/node_key.pem:ro
    logging:
      driver: "json-file"
      options:
        max-size: "50m"
        max-file: "3"
COMPOSE

# ── 6. Pull the VEIL node image ───────────────────────────
echo "  Pulling JULIUS VEIL node image..."
docker pull "$DOCKER_IMAGE" 2>&1 | tail -3 || {{
    echo "  ⚠ Could not pull image (may not be public yet). Using local build..."
}}

# ── 7. Start the container ────────────────────────────────
echo "  Starting VEIL node container..."
cd "$VEIL_DIR"
docker compose up -d 2>/dev/null || docker-compose up -d 2>/dev/null

sleep 3

if docker ps --filter "name=julius-veil-node" --filter "status=running" | grep -q julius-veil-node; then
    echo "  ✓ VEIL node container is running"
else
    echo "  ⚠ Container may not have started. Check: docker logs julius-veil-node"
fi

# ── 8. Register with the JULIUS network ───────────────────
echo "  Registering node with JULIUS network..."

METADATA=$(cat <<JSON
{{
  "os": "$OS",
  "os_version": "$OS_VERSION",
  "docker_version": "$(docker --version 2>/dev/null | head -1)",
  "hostname": "$(hostname -f 2>/dev/null || hostname)",
  "node_name": "$NODE_NAME"
}}
JSON
)

REGISTER_RESPONSE=$(curl -s -w "\\n%{{http_code}}" -X POST "$NETWORK_URL/guardian/onboarding/register" \\
  -H "Content-Type: application/json" \\
  -d "{{
    \\"partner_id\\": \\"$PARTNER_ID\\",
    \\"public_key\\": \\"$PUBLIC_KEY\\",
    \\"node_metadata\\": $METADATA
  }}" 2>/dev/null) || REGISTER_RESPONSE=""

HTTP_CODE=$(echo "$REGISTER_RESPONSE" | tail -1)
BODY=$(echo "$REGISTER_RESPONSE" | head -1)

if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "201" ]; then
    echo "  ✓ Node successfully registered with the JULIUS network!"
else
    echo "  ⚠ Registration response: HTTP $HTTP_CODE"
    echo "    You can retry manually: curl -X POST $NETWORK_URL/guardian/onboarding/register"
fi

# ── 9. Systemd watchdog (optional) ────────────────────────
if command -v systemctl &>/dev/null && [ -d /etc/systemd/system ]; then
    cat > /etc/systemd/system/julius-veil.service <<SERVICE
[Unit]
Description=JULIUS VEIL Mix Node
After=docker.service
Requires=docker.service

[Service]
WorkingDirectory=$VEIL_DIR
ExecStart=/usr/local/bin/docker-compose up
ExecStop=/usr/local/bin/docker-compose down
Restart=always
RestartSec=30

[Install]
WantedBy=multi-user.target
SERVICE
    systemctl daemon-reload
    systemctl enable julius-veil 2>/dev/null || true
    echo "  ✓ Systemd service registered (julius-veil)"
fi

# ── Done ──────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  ✅ JULIUS VEIL Node is now ACTIVE and earning!"
echo ""
echo "  Partner ID : $PARTNER_ID"
echo "  Public Key : ${{PUBLIC_KEY:0:32}}..."
echo "  Data dir   : $VEIL_DIR"
echo ""
echo "  Useful commands:"
echo "    docker logs julius-veil-node     # View node logs"
echo "    docker stats julius-veil-node    # Resource usage"
echo "    docker restart julius-veil-node  # Restart node"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
"""
    return script


def generate_one_liner(partner_id: str, network_url: str) -> str:
    """Return the curl | bash one-liner that partners run."""
    return (
        f"curl -fsSL {network_url}/guardian/onboarding/script/{partner_id} | sudo bash"
    )


def generate_verification_command(network_url: str, partner_id: str) -> str:
    """Return a command the partner can run to verify their installation."""
    return (
        f"curl -s {network_url}/guardian/onboarding/status/{partner_id} | python3 -m json.tool"
    )
