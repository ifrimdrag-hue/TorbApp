# Infrastructure — History & Resolved Items

> ⛔ **Archive — do not auto-load.** Read this file **only** when explicitly investigating a past
> change. It is excluded from session-start reading and is not pulled in by `infrastructure.md`.
>
> **Purpose:** archive of dated changes, resolved security items, and applied checklists for the VPS
> server. The live source of truth for **current** facts is `context/infrastructure.md`. This file
> is append-mostly — record what was done, when, and why, so the current file can stay lean.

---

## Secrets vault migration — 2026-06-17

Replaced the plaintext secrets companion with an encrypted vault (backlog item #5: "encrypt the
secrets companion / move to a password vault").

- **Tool:** KeePassXC (installed via `winget install KeePassXCTeam.KeePassXC`). Chosen for being
  offline, single-file, free, cross-platform — satisfies both "encrypt" and "vault" goals.
- **Vault:** `C:\Users\rosio\Vault\torb-secrets.kdbx` — kept **outside** the repo. AES-256 + Argon2id
  KDF; master passphrase held only by the owner (and stored in a second trusted place).
- **Content:** full former `secrets.local.md` pasted into a "Server manual — secrets index" entry,
  plus dedicated entries for the high-value uniques (cyberfolks console, server SSH, app admin
  accounts, SMTP Gmail app password).
- **Plaintext removed:** `docs/manuals/server/secrets.local.md` overwritten with random data (3
  passes) then deleted. ⚠️ SSD wear-leveling means overwrite-delete is best-effort — full-disk
  encryption (BitLocker) is the real at-rest protection; confirm it's enabled.
- **Docs updated:** `infrastructure.md` references + pending list; `.gitignore` (retained the
  `secrets.local.md` ignore as a safety net, added `*.kdbx`).
- **Follow-up:** the Typst server manual (`manual_server.typ`, ch. 9) still documents the old
  `secrets.local.md` file/path — needs updating + a recompile.

---

## GitHub secrets / deploy-key cleanup — 2026-06-17

- **Deploy-key item closed:** repo *Settings → Deploy keys* is empty (this project deploys via
  GitHub Actions SSHing into the VPS using the `VPS_SSH_KEY` **Actions secret**, not a GitHub repo
  deploy key). The orphaned `github-actions-deploy` (`SHA256:5DP0…f2r0`) was already removed from the
  server's `authorized_keys` on 2026-06-15; nothing stale remained on GitHub. **Resolved.**
- **SMTP secrets confirmed:** `SMTP_USER` + `SMTP_PASSWORD` present in Actions secrets. **Resolved.**
- **Deleted dead secret `OPENCLAW_TOKEN`** — leftover from the pre-CLI WebSocket integration;
  referenced in neither the code nor `deploy_VPS.yml`. Flask's OpenClaw path is CLI-only now.
- Actions secrets inventory after cleanup: `ANTHROPIC_API_KEY`, `EMAG_PASSWORD`, `EMAG_USERNAME`,
  `EMAG_WAREHOUSE_ID`, `FLASK_SECRET_KEY`, `SHOPIFY_CLIENT_ID`, `SHOPIFY_CLIENT_SECRET`,
  `SMTP_PASSWORD`, `SMTP_USER`, `VPS_HOST`, `VPS_SSH_KEY`, `VPS_USERNAME`.

---

## CSP header — pragmatic policy shipped 2026-06-17

Audit found **no external/CDN assets** (all CSS/JS/fonts served from `static/`), but ~25 inline
`<script>` blocks, 99 inline event handlers, and many inline `style=` attributes — so a strict
nonce/hash CSP needs a full template refactor. Shipped a pragmatic `'self'`-based policy in
`app/app.py` `_security_headers` (`'unsafe-inline'` for script/style); blocks external script/style/
frame injection + exfiltration with zero breakage risk. Regression test extended in
`tests/test_security_headers.py`. Strict nonce-based CSP logged as a follow-up task.

---

## SSH / authorized_keys cleanup — 2026-06-15

- Switched human admin login to **key-only** on port 2112 (`PasswordAuthentication no`). A personal
  admin SSH key (`vladr-laptop`, `SHA256:rFRS0osjmEEO+xmifuXLbDzYcbR2gOi5Nnojj9/2Ie0`) was added to
  `~/.ssh/authorized_keys`; the `openclaw` account password is now used **only** for the cyberfolks
  emergency console (not SSH).
- Removed a stray literal `paste-public-key-here` line and a **stale** rotated deploy key
  `github-actions-deploy` (`SHA256:5DP0…f2r0`, unused since 2026-05-25). Backups:
  `~/.ssh/authorized_keys.bak.*`.
- Remaining live key: `github-deploy` (`SHA256:EigIB4gJEujSSi0Hko7rZSCwmpcJmmxo6ctouxqzfaE`) = the
  **live `VPS_SSH_KEY`** used by GitHub Actions.

---

## Security hardening — 2026-06-15 (RESUME CHECKLIST applied after sudo restore)

Applied after `openclaw` was restored to the `sudo` group (provider ticket resolved):

- Removed stale `22/tcp` + `8888/tcp` firewall rules (sshd listens on `2112` only).
- Disabled Tailscale (`systemctl disable --now tailscaled`) + closed `41641/udp` (was `Logged out`).
- sshd `PermitRootLogin prohibit-password` via `/etc/ssh/sshd_config.d/99-torb-hardening.conf`.
- `.env` confirmed `640 openclaw:www-data`; no pending security updates; OpenClaw gateway recycled.
- fail2ban `[sshd]` active.
- `server_tokens off;` applied in `nginx.conf` (reloaded — version no longer leaked).
- `PasswordAuthentication no` — personal admin SSH key configured first, then password auth disabled;
  SSH now key-only. Recovery if the key is lost: cyberfolks console (local console, not SSH).

### Verbatim RESUME CHECKLIST (kept for rebuild reference)

```bash
# 1. Confirm recovery
id openclaw                 # expect: ...,27(sudo),33(www-data)
sudo -v                     # should succeed (no "not allowed")

# 2. SSH hardening
sshd -T | grep -Ei 'permitrootlogin|passwordauthentication|pubkeyauthentication'
sudo tee /etc/ssh/sshd_config.d/99-torb-hardening.conf >/dev/null <<'EOF'
PermitRootLogin prohibit-password
# PasswordAuthentication no   # uncomment ONLY after confirming key login works for you
EOF
sudo sshd -t && sudo systemctl reload ssh

# 3. nginx version leak — add `server_tokens off;` inside http{} of /etc/nginx/nginx.conf, then:
sudo nginx -t && sudo systemctl reload nginx

# 4. Recycle the OpenClaw gateway session (drop stale docker/sudo groups from the live process)
sudo loginctl terminate-user openclaw    # linger restarts the gateway
sleep 5                                   # then verify gateway is up + widget chat answers

# 5. Firewall — remove stale SSH rules (sshd listens on 2112 only; 22 + 8888 are dead)
sudo ufw status verbose
sudo ufw delete allow 22/tcp
sudo ufw delete allow 8888/tcp
sudo fail2ban-client status sshd          # confirm maxretry/bantime

# 6. Tailscale — installed but Logged out + 41641/udp open. Pick ONE:
#    (a) if NOT needed:
sudo systemctl disable --now tailscaled
sudo ufw delete allow 41641/udp
#    (b) if needed: `sudo tailscale up`, then document the tailnet in secrets.local.md

# 7. Cleanup (optional)
ls -l /var/www/html/torb-py/.env                      # confirm 640 openclaw:www-data
sudo rm /etc/nginx/sites-available/*.bak.2026-06-13   # leftover clutter
apt-get -s upgrade | grep -i security                  # any pending security updates
```

**Notes:** keep `PasswordAuthentication no` commented until `sshd -T` + a test key-login confirm you
won't re-lock yourself. Dev app (`:5001`) internet-exposed (separate DB, same auth) — accepted.

---

## OpenClaw gateway setup & fixes — 2026-06-13

Auto-updated to **v2026.6.6** mid-setup. Runs as a **user-linger** systemd service under the
`openclaw` account (not system scope).

**Fixes applied (gateway was dead before this):**
1. Config `openclaw.json` was truncated/corrupt (JSON5 EOF at line 56) → restored from
   `~/.openclaw/openclaw.json.last-good`.
2. The unit's ExecStart had `--trusted-proxy 127.0.0.1`, **unsupported in this version** → removed
   (gateway exited 1 on every start).
3. Auto-updated to **2026.6.6** mid-setup (v4 control protocol + per-agent auth store). Needed a
   gateway restart to clear a v3/v4 "protocol mismatch" in the dashboard.
4. **Device scopes:** the old `operator` device (paired under 2026.4.29) was stuck at
   `read`+`pairing`; agent turns need `write`, and piecemeal CLI approval races on ephemeral request
   ids (`unknown requestId`). Fixed by approving the pending scope upgrade in the **dashboard**
   (Nodes → Devices) once an admin-scoped device existed. New local pairings under 2026.6.6 auto-get
   full scopes.
5. **Provider auth is per-agent** (`~/.openclaw/agents/main/agent/openclaw-agent.sqlite`). Set via
   `openclaw models auth login --provider openrouter` (OAuth). **Restart the gateway afterward** so
   it reloads the key, else turns fail "No API key found".

Verified working end-to-end 2026-06-13: the full app path
`www-data → sudo -u openclaw → wrapper → openclaw agent → gateway → OpenRouter` returns a real reply
in ~4s. Output shape: `{runId, status:"ok", result:{payloads:[{text}], meta}}`. Agent `main` is out
of BOOTSTRAP and replies normally.

**Free-only models (2026-06-13):** model switched `openrouter/auto` → `openrouter/free` in
`~/.openclaw/openclaw.json` (default + alias + configured-models entry) to cap cost at free tier.
Verified end-to-end: agent turn returns `status:ok`, `winnerModel:openrouter/free`, tool calls
succeed. Trade-offs: slower (~15s vs ~4s) and lower output quality. Revert: restore
`~/.openclaw/openclaw.json.bak.<ts>` + `systemctl --user restart openclaw-gateway.service`. If turns
later fail on tool schemas, pin a specific free model (e.g. `meta-llama/llama-3.3-70b-instruct:free`).

**Optional items resolved 2026-06-13:**
- (a) exec is now `deny-all` — agent cannot run server commands at all. Chat-only by design. To later
  allow read-only server prompts, switch to `exec-policy preset cautious` + a tight allowlist
  (`openclaw approvals allowlist add`) rather than reverting to `deny-all`/`full`.
- (b) removed the two legacy nginx `location /admin/openclaw-ws` blocks (`app.robrands.ro` +
  `default`). `/admin/openclaw-ws/` now returns 302→login (served by Flask) instead of proxying to
  the gateway, closing the auth-bypass back-door. Backups: `*.bak.<date>` in
  `/etc/nginx/sites-available/`.
- (d) The app route `/admin/openclaw-ask` shipped (commits `5d3fcc1`, `5bc162a`).

---

## OpenClaw security lockdown — RESOLVED 2026-06-13

**Question asked:** "is everything secure, including what OpenClaw can execute on the server?"

**Original verdict:** Internet-facing surface was fine (admin-only + CSRF route, gateway
loopback-only, nginx back-door removed). But **what the agent could execute was NOT secure** —
`tools.exec security=full, ask=off`, empty allowlist (runs any shell command, no prompt), while
`openclaw` was in the `sudo` + `docker` (root-equivalent) groups. Any Flask admin, or anyone with
code-exec as `www-data`, could prompt the agent into arbitrary commands and **escalate to root**.

**Lockdown applied (all verified):**
1. **Exec disabled.** `openclaw exec-policy preset deny-all` → host approvals
   `~/.openclaw/exec-approvals.json` defaults now `security=deny, ask=off, askFallback=deny`. Gateway
   restarted to load it. Effective policy confirmed `security=deny`. (Rollback:
   `openclaw approvals set --file ~/.openclaw/exec-approvals.json.bak.20260613` + gateway restart.)
2. **Root-equivalent groups dropped.** `sudo gpasswd -d openclaw docker` (zero containers, group
   unused) + `sudo gpasswd -d openclaw sudo`. *(Note: the `sudo` removal locked out the human admin —
   see lesson below; `sudo` was later restored 2026-06-15.)*
3. **Deploys still work** — the `torb-deploy` sudoers file grants `openclaw` NOPASSWD on
   `/bin/systemctl restart torb-py` and `/usr/bin/systemctl restart torb-dev` directly (user-based,
   not group-based).
4. **Widget chat unaffected** — `www-data → wrapper → agent` smoke test returns `status: ok`.

---

## Full security audit — 2026-06-13

Read-only audit across app + host after the OpenClaw lockdown. Posture sound.

**Verified solid:** fail2ban active (`[sshd]` jail on); ufw active; gunicorn (`:5000`/`:5002`) + agent
gateway (`:18789`) loopback-only; `~/.openclaw` is `700`, agent key sqlite `600`, nothing
world-readable; unattended security upgrades on; SQLi not exposed (bound params; dynamic `{sets}` =
whitelisted columns); CSRF app-wide; passwords pbkdf2.

**Fixed in code/CI (commit `51e6b4c`):**
- `ProxyFix(x_for, x_proto)` in `app/app.py` — nginx sets `X-Forwarded-For`/`-Proto` but Flask saw
  `127.0.0.1`, so the login rate limiter was effectively global and audit IPs were useless.
- Security headers via `after_request`: `X-Content-Type-Options`, `X-Frame-Options=SAMEORIGIN`,
  `Referrer-Policy`, HSTS. CSP deliberately deferred (inline scripts + CDN assets need an audit).
- `deploy_VPS.yml` (prod+dev): inject `SESSION_COOKIE_SECURE=1`; `chgrp www-data` + `chmod 640` on
  `.env` after every write.

**Fixed on server 2026-06-13:** `.env` was `664 openclaw:openclaw` (secrets world-readable) →
`640 openclaw:www-data` on prod + dev.

> **⚠️ LESSON 2026-06-13:** dropping `openclaw` from the `sudo` group locked the human admin out of
> root — `openclaw` is the *only* admin account and there is no separate root password. The real
> escalation hole was the **`docker`** group (passwordless root); `sudo` is password-gated and the
> non-interactive agent could never use it. **Keep `openclaw` in `sudo`.** Recovery requires the
> provider console (`usermod -aG sudo openclaw`). Don't remove the sole admin's sudo again.

**UPDATE 2026-06-15:** ✅ **sudo restored** — `openclaw` is back in the `sudo` group (provider ticket
resolved); `sudo -v` works. Block B was run and surfaced new findings (un-hardened sshd, stale
22/8888 rules, dormant Tailscale) — folded into the 2026-06-15 hardening above. `ANTHROPIC_API_KEY`
confirmed **still in use** by the in-app Claude features (ai.py, post/campaign generators,
ai_suggestions, auto_posts) — do **not** remove it; the OpenRouter switch only affects the OpenClaw
gateway.
