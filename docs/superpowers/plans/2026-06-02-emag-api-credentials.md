# eMAG API Credentials & Sync Activation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the "Sincronizare stoc — eMAG" API connection indicator go green and the full sync flow work end-to-end.

**Architecture:** The eMAG API client reads credentials from `EMAG_USERNAME` / `EMAG_PASSWORD` env vars via `app/config.py` (pydantic-settings). These vars are missing from the server `.env` — the deploy script only injects `ANTHROPIC_API_KEY`. Fix is: (1) patch the server `.env` now, (2) wire the credentials through GitHub Secrets + deploy script so future deploys keep them.

**Tech Stack:** bash (SSH on VPS), GitHub Actions secrets, httpx (already in venv), pydantic-settings (already installed)

---

## Files touched

| File | Action | Why |
|------|--------|-----|
| `/var/www/html/torb-py/.env` (server) | Edit manually via SSH | Add missing `EMAG_USERNAME`, `EMAG_PASSWORD` |
| `.github/workflows/deploy_VPS.yml` | Modify | Inject eMAG secrets into `.env` on every deploy |

No Python changes needed — the code is correct. This is purely a configuration gap.

---

### Task 1: Add eMAG credentials to the server `.env` (immediate fix)

**Files:**
- Edit: `/var/www/html/torb-py/.env` on the VPS (via SSH)

- [ ] **Step 1: SSH into the VPS**

```bash
ssh -p 2112 username@your-vps-host
```

- [ ] **Step 2: Inspect the current `.env` to confirm eMAG vars are missing**

```bash
grep -E "EMAG" /var/www/html/torb-py/.env
```

Expected output: empty (no lines) — confirming the vars are absent.

- [ ] **Step 3: Add the eMAG credentials**

Replace `your_emag_email@firma.ro` and `your_emag_password` with the real seller account credentials from the eMAG Marketplace seller panel.

```bash
cd /var/www/html/torb-py

# Append without overwriting existing vars
echo "EMAG_USERNAME=your_emag_email@firma.ro" >> .env
echo "EMAG_PASSWORD=your_emag_password" >> .env
```

- [ ] **Step 4: Verify both lines are now in `.env`**

```bash
grep -E "EMAG" .env
```

Expected output:
```
EMAG_USERNAME=your_emag_email@firma.ro
EMAG_PASSWORD=your_emag_password
```

- [ ] **Step 5: Restart the app**

```bash
sudo systemctl restart torb-py
sudo systemctl status torb-py
```

Expected: `active (running)` with no restart counter climbing.

- [ ] **Step 6: Verify the connection dot turns green**

Open `https://app.robrands.ro/stocuri/emag` in a browser.

Expected: the bubble next to "Sincronizare stoc — eMAG" turns **green** within ~5 seconds.

If it stays red: run the connection test manually to see the exact error:
```bash
cd /var/www/html/torb-py
source venv/bin/activate
python3 -c "
import asyncio
from app.automations.stocuri_emag.api_client import EmagClient
c = EmagClient()
asyncio.run(c.test_connection())
print('OK')
"
```

---

### Task 2: Wire eMAG credentials through CI/CD (permanent fix)

**Files:**
- Modify: `.github/workflows/deploy_VPS.yml` (local, then push)

Every deploy runs `git reset --hard origin/main` which doesn't touch `.env`, but the deploy script currently only writes `ANTHROPIC_API_KEY`. eMAG credentials need the same treatment.

- [ ] **Step 1: Add GitHub secrets for eMAG**

In GitHub → repository → **Settings → Secrets and variables → Actions → New repository secret**, add:

| Secret name | Value |
|---|---|
| `EMAG_USERNAME` | The eMAG seller account email |
| `EMAG_PASSWORD` | The eMAG seller account password |

- [ ] **Step 2: Update the deploy script to inject eMAG credentials**

In `.github/workflows/deploy_VPS.yml`, find the `env:` block on the deploy step and the `envs:` + secret injection lines. Replace them:

```yaml
      - name: Deploy via SSH
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          EMAG_USERNAME: ${{ secrets.EMAG_USERNAME }}
          EMAG_PASSWORD: ${{ secrets.EMAG_PASSWORD }}
        uses: appleboy/ssh-action@v1.0.3
        with:
          host: ${{ secrets.VPS_HOST }}
          username: ${{ secrets.VPS_USERNAME }}
          key: ${{ secrets.VPS_SSH_KEY }}
          port: 2112
          envs: ANTHROPIC_API_KEY,EMAG_USERNAME,EMAG_PASSWORD
          script: |
            set -e
            git config --global --add safe.directory /var/www/html/torb-py
            cd /var/www/html/torb-py

            # Discard any accidental local changes on the server — source of truth is git
            git fetch origin main
            git reset --hard origin/main

            # Remove dev-only files — no runtime use on the production server
            rm -rf tests/ context/ docs/

            # Inject secrets into .env (create if missing, update if present)
            touch .env
            grep -v '^ANTHROPIC_API_KEY=' .env > .env.tmp && mv .env.tmp .env
            echo "ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}" >> .env
            grep -v '^EMAG_USERNAME=' .env > .env.tmp && mv .env.tmp .env
            echo "EMAG_USERNAME=${EMAG_USERNAME}" >> .env
            grep -v '^EMAG_PASSWORD=' .env > .env.tmp && mv .env.tmp .env
            echo "EMAG_PASSWORD=${EMAG_PASSWORD}" >> .env

            # Update dependencies
            source venv/bin/activate
            pip install --quiet --upgrade pip
            pip install --quiet -r requirements.txt

            # Restart app (migrations run automatically on startup)
            sudo systemctl restart torb-py
```

- [ ] **Step 3: Stage and commit the workflow change**

```bash
git add .github/workflows/deploy_VPS.yml
git commit -m "ci: inject eMAG credentials into server .env on deploy"
```

- [ ] **Step 4: Push and verify the deploy job passes**

```bash
git push origin main
```

Watch the GitHub Actions run. The deploy job should complete without error, and the app should restart with all credentials in place.

---

### Task 3: Verify the full sync flow end-to-end

Once the dot is green, confirm the actual sync works (not just the connection test).

- [ ] **Step 1: Open the eMAG sync page**

Navigate to `https://app.robrands.ro/stocuri/emag`.

Expected: green connection dot, "Vizualizează ofertele eMAG" button enabled.

- [ ] **Step 2: Load eMAG offers without uploading a report**

Click **"Vizualizează ofertele eMAG"** (no file upload). The table should populate with current eMAG stock levels fetched live from the API.

Expected: table with offer rows, each showing current stock.

If this fails: the API credentials are wrong (not just missing) — double-check the username/password in the eMAG seller panel.

- [ ] **Step 3: Upload an internal stock report and preview**

Upload a stock Excel report (`.xls` / `.xlsx`) from `docs_input/`. The parser expects columns: `cod`, `codbare` (EAN), `cantit`.

Expected: comparison table showing old eMAG stock vs. new stock from the report. Rows flagged as: `updated` / `zeroed_threshold` / `unchanged` / `no_ean`.

- [ ] **Step 4: Sync a small batch (test with 1–2 rows)**

Select 1–2 rows marked `updated` and click **"Sincronizează pe eMAG"**.

Expected: success count = selected rows, error count = 0. Verify on the eMAG seller panel that the stock values actually changed.

If errors appear: expand the error list — the per-item error message from eMAG will explain the cause (wrong offer ID, invalid stock value, etc.).
