# Infrastructure — VPS Server

## Server

| Property | Value |
|---|---|
| Provider | VPS (Linux) |
| IP | 188.241.116.172 |
| SSH port | 2112 |
| SSH user | openclaw |
| Domain | app.robrands.ro |
| SSL | Let's Encrypt via Certbot (auto-renewal) |

---

## Environments

### Production

| Property | Value |
|---|---|
| URL | https://app.robrands.ro |
| Path | `/var/www/html/torb-py` |
| Systemd service | `torb-py` |
| Gunicorn bind | `127.0.0.1:5000` |
| Gunicorn workers | 3 |
| Run as | `www-data` |
| venv | `/var/www/html/torb-py/venv` |
| Database | `/var/www/html/torb-py/data/torb.db` |
| Env file | `/var/www/html/torb-py/.env` |
| Logs | `/var/www/html/torb-py/logs/app.log` |
| Deploy trigger | Push to `main` (GitHub Actions) |

### Dev / Test

| Property | Value |
|---|---|
| URL | https://app.robrands.ro:5001 |
| Path | `/var/www/html/torb-py-dev` |
| Systemd service | `torb-dev` |
| Gunicorn bind | `127.0.0.1:5002` |
| Gunicorn workers | 2 |
| Run as | `www-data` |
| venv | `/var/www/html/torb-py-dev/venv` |
| Database | `/var/www/html/torb-py-dev/data/torb.db` (independent copy) |
| Env file | `/var/www/html/torb-py-dev/.env` |
| Logs | `/var/www/html/torb-py-dev/logs/app.log` |
| Deploy trigger | Push to `main` via `deploy_dev` CI job (planned) |

---

## Nginx

Config files:
- `/etc/nginx/sites-available/app.robrands.ro` — production vhost (managed by Certbot)
- `/etc/nginx/sites-available/torb-dev` — dev vhost (port 5001)
- `/etc/nginx/sites-enabled/default` — fallback, proxies to `127.0.0.1:5000`

Routing summary:
```
:80  → 301 to https://app.robrands.ro (Certbot)
:443 → nginx → 127.0.0.1:5000 (prod gunicorn)
:5001 ssl → nginx → 127.0.0.1:5002 (dev gunicorn)
```

SSL certificate: `/etc/letsencrypt/live/app.robrands.ro/`
- `fullchain.pem` / `privkey.pem`
- Shared by both prod and dev nginx blocks

---

## Systemd Services

```bash
sudo systemctl status torb-py      # production
sudo systemctl status torb-dev     # dev/test
sudo systemctl restart torb-py
sudo systemctl restart torb-dev
```

Service files:
- `/etc/systemd/system/torb-py.service`
- `/etc/systemd/system/torb-dev.service`

---

## Firewall (ufw)

| Port | Protocol | Purpose |
|---|---|---|
| 22 / 2112 | TCP | SSH |
| 80 | TCP | HTTP (redirects to HTTPS) |
| 443 | TCP | HTTPS — production |
| 5001 | TCP | HTTPS — dev/test |

---

## Repository

GitHub: `https://github.com/ifrimdrag-hue/TorbApp`

Git safe directories configured on server:
```bash
git config --global --add safe.directory /var/www/html/torb-py
git config --global --add safe.directory /var/www/html/torb-py-dev
```

---

## CI/CD

Pipeline: `.github/workflows/deploy_VPS.yml`

Current jobs (as of 2026-06-04):
1. `lint` — ruff check
2. `test` — pytest
3. `security` — pip-audit
4. `deploy` → being renamed to `deploy_prd`
5. `smoke-test-vps` → being renamed to `test_prd`

Planned jobs (not yet implemented — see memory `project-dev-env-plan`):
- `deploy_dev` — deploys to `/var/www/html/torb-py-dev`, restarts `torb-dev`
- `test_dev` — smoke tests against `https://app.robrands.ro:5001`
- `approve_prd` — manual gate via GitHub Environment `production`

---

## Useful One-Liners

```bash
# Tail logs
sudo tail -f /var/www/html/torb-py/logs/app.log
sudo tail -f /var/www/html/torb-py-dev/logs/app.log

# Smoke test prod
curl -s -o /dev/null -w "%{http_code}\n" https://app.robrands.ro/healthz

# Smoke test dev
curl -s -o /dev/null -w "%{http_code}\n" https://app.robrands.ro:5001/healthz

# Check nginx config
sudo nginx -t

# Reload nginx (no downtime)
sudo systemctl reload nginx
```
