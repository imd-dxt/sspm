#!/usr/bin/env bash
# setup_droplet.sh — Run ONCE as root on a fresh Ubuntu 22.04 Droplet.
# Usage: curl -fsSL https://raw.githubusercontent.com/YOUR_USER/sspm/main/scripts/setup_droplet.sh | bash
#   or:  bash setup_droplet.sh
set -euo pipefail

REPO_URL="https://github.com/YOUR_USERNAME/YOUR_REPO.git"   # ← update this
DEPLOY_USER="sspm"
APP_DIR="/opt/sspm"

# ── 1. Docker ─────────────────────────────────────────────────────────────────
echo "=== Installing Docker ==="
apt-get update -y
apt-get install -y ca-certificates curl gnupg git

install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  | tee /etc/apt/sources.list.d/docker.list > /dev/null

apt-get update -y
apt-get install -y docker-ce docker-ce-cli containerd.io \
  docker-buildx-plugin docker-compose-plugin

# ── 2. Deploy user ────────────────────────────────────────────────────────────
echo "=== Creating deploy user: $DEPLOY_USER ==="
if ! id "$DEPLOY_USER" &>/dev/null; then
  useradd -m -s /bin/bash "$DEPLOY_USER"
fi
usermod -aG docker "$DEPLOY_USER"

# ── 3. SSH key for GitHub Actions ─────────────────────────────────────────────
echo "=== Configuring SSH for GitHub Actions deploy key ==="
mkdir -p "/home/$DEPLOY_USER/.ssh"

# Paste the PUBLIC key that corresponds to the SSH_PRIVATE_KEY GitHub secret:
#   ssh-keygen -t ed25519 -C "sspm-deploy" -f ~/.ssh/sspm_deploy
#   cat ~/.ssh/sspm_deploy.pub   ← paste below
#   Add ~/.ssh/sspm_deploy (private) as SSH_PRIVATE_KEY in GitHub secrets
echo "PASTE_YOUR_PUBLIC_KEY_HERE" >> "/home/$DEPLOY_USER/.ssh/authorized_keys"

chmod 700  "/home/$DEPLOY_USER/.ssh"
chmod 600  "/home/$DEPLOY_USER/.ssh/authorized_keys"
chown -R "$DEPLOY_USER:$DEPLOY_USER" "/home/$DEPLOY_USER/.ssh"

# ── 4. Clone repository ───────────────────────────────────────────────────────
echo "=== Cloning repository to $APP_DIR ==="
if [ -d "$APP_DIR/.git" ]; then
  echo "Repo already exists, skipping clone."
else
  git clone "$REPO_URL" "$APP_DIR"
fi
chown -R "$DEPLOY_USER:$DEPLOY_USER" "$APP_DIR"

# Allow the deploy user to git-pull inside this directory
sudo -u "$DEPLOY_USER" git -C "$APP_DIR" config --global --add safe.directory "$APP_DIR"

# ── 5. Environment file ───────────────────────────────────────────────────────
echo "=== Creating .env ==="
if [ ! -f "$APP_DIR/.env" ]; then
  cp "$APP_DIR/.env.example" "$APP_DIR/.env"
  echo ""
  echo "⚠️  Edit $APP_DIR/.env before continuing:"
  echo "   nano $APP_DIR/.env"
  echo ""
  echo "Required values to fill in:"
  echo "   POSTGRES_PASSWORD   — strong random password"
  echo "   NEO4J_PASSWORD      — strong random password"
  echo "   ENCRYPTION_KEY      — python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
  echo "   GITHUB_REPOSITORY   — your-username/sspm"
  echo ""
  read -rp "Press Enter after editing .env to continue, or Ctrl+C to stop here..."
else
  echo ".env already exists, skipping."
fi

# ── 6. Start infrastructure services ─────────────────────────────────────────
echo "=== Starting postgres, neo4j, redis ==="
cd "$APP_DIR"
sudo -u "$DEPLOY_USER" docker compose -f docker/docker-compose.yml \
  up -d postgres neo4j redis

echo ""
echo "✅ Droplet setup complete!"
echo ""
echo "Next steps:"
echo "  1. Verify services: docker compose -f $APP_DIR/docker/docker-compose.yml ps"
echo "  2. Add GitHub Actions secrets (see README or deploy.yml comments):"
echo "       DROPLET_IP      → $(curl -sf https://checkip.amazonaws.com || hostname -I | awk '{print $1}')"
echo "       SSH_PRIVATE_KEY → content of your sspm_deploy private key file"
echo "       ENCRYPTION_KEY  → same value as in $APP_DIR/.env"
echo "  3. Push to main to trigger the first full deployment."
