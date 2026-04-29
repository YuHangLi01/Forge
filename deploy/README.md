# Aliyun Deployment Runbook

CI/CD path: PR → `main` merge → GitHub Actions → SSH into Aliyun ECS → `scripts/deploy.sh`.

## 1. Aliyun ECS one-time setup

1. Create an ECS instance (Ubuntu 22.04, ≥ 2 vCPU / 4 GB RAM, ≥ 40 GB SSD).
2. Point your domain's A record at the ECS public IP.
3. Security group inbound rules:
   - `22/tcp` (SSH) — restrict source IP if possible
   - `80/tcp`, `443/tcp` — open to `0.0.0.0/0` (Feishu webhook + certbot)
   - `5432`, `6379`, `8001` — **do NOT** expose; bind to `127.0.0.1` only

## 2. Server bootstrap (run as root or with sudo)

```bash
# 2.1 base packages
apt update && apt install -y git curl nginx certbot python3-certbot-nginx
# 2.2 create deploy user
adduser --disabled-password --gecos "" forge
usermod -aG sudo forge
# 2.3 install uv for forge user
sudo -iu forge bash -lc 'curl -LsSf https://astral.sh/uv/install.sh | sh'
sudo -iu forge bash -lc 'uv python install 3.11'
# 2.4 clone repo
mkdir -p /opt/forge && chown forge:forge /opt/forge
sudo -iu forge git clone https://github.com/YuHangLi01/Forge.git /opt/forge
# 2.5 install postgres + redis (uses repo's idempotent script)
cd /opt/forge && sudo -iu forge make services-install
# 2.6 fill in .env
sudo -iu forge cp /opt/forge/.env.example /opt/forge/.env
sudo -iu forge nano /opt/forge/.env   # edit secrets
# 2.7 install deploy keypair (the public side goes into the GitHub Secret)
sudo -iu forge ssh-keygen -t ed25519 -f /home/forge/.ssh/deploy_key -N ""
cat /home/forge/.ssh/deploy_key.pub >> /home/forge/.ssh/authorized_keys
chmod 600 /home/forge/.ssh/authorized_keys
# you will paste the PRIVATE key (deploy_key) into GitHub Secret DEPLOY_SSH_KEY
cat /home/forge/.ssh/deploy_key
```

## 3. Install systemd units

```bash
sudo cp /opt/forge/deploy/forge-api.service /etc/systemd/system/
sudo cp /opt/forge/deploy/forge-worker.service /etc/systemd/system/
sudo cp /opt/forge/deploy/forge-chromadb.service /etc/systemd/system/
sudo cp /opt/forge/deploy/sudoers-forge /etc/sudoers.d/forge
sudo chmod 440 /etc/sudoers.d/forge

sudo systemctl daemon-reload
# first-time DB migrate
sudo -iu forge bash -lc 'cd /opt/forge && uv sync --frozen && uv run alembic upgrade head'
# enable + start
sudo systemctl enable --now forge-chromadb forge-api forge-worker
sudo systemctl status forge-api forge-worker forge-chromadb --no-pager
```

## 4. Nginx + HTTPS

```bash
sudo cp /opt/forge/deploy/nginx-forge.conf /etc/nginx/sites-available/forge
sudo sed -i 's/YOUR_DOMAIN/your.real.domain/g' /etc/nginx/sites-available/forge
sudo ln -sf /etc/nginx/sites-available/forge /etc/nginx/sites-enabled/forge
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d your.real.domain    # gets cert + uncomments ssl lines
```

## 5. GitHub Secrets (Settings → Secrets and variables → Actions)

| Secret | Value |
|---|---|
| `DEPLOY_HOST` | ECS public IP or domain |
| `DEPLOY_USER` | `forge` |
| `DEPLOY_PORT` | `22` (or your SSH port) |
| `DEPLOY_SSH_KEY` | full content of `/home/forge/.ssh/deploy_key` (private key, including BEGIN/END lines) |

(Optional) Create a GitHub Environment named `production` with required reviewers if you want a manual approval gate before each deploy.

## 6. First deploy

After all the above is in place:

```bash
git push origin main      # triggers .github/workflows/deploy.yml
```

Watch the run at `https://github.com/YuHangLi01/Forge/actions`.

## 7. Set Feishu webhook URL

Feishu developer console → event subscription → request URL:
`https://your.real.domain/api/v1/webhook/feishu`

## 8. Rollback

`git revert <bad-sha> && git push` re-triggers the pipeline with the prior code.
For an emergency manual rollback on the server:

```bash
sudo -iu forge bash -lc 'cd /opt/forge && git reset --hard <good-sha> && uv sync --frozen && sudo systemctl restart forge-api forge-worker'
```
