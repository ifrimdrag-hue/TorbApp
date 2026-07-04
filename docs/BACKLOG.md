# Backlog — Open Issues & Noted Work

Single home for open technical, infrastructure, and product issues — analysed or just noted. Consolidated 2026-07-02 from `.claude/project_knowledge.md` §Tech-debt and `context/infrastructure.md` §Pending. Strategic decisions and 90-day action items are tracked live in `context/STATUS.md`; delivered work is recorded there and in `CHANGELOG.md`.

---

## Tech-debt (priority order)

Combines the leftovers of the 2026-05-28 code audit (re-verified against code on 2026-06-11) and the infrastructure gaps found in the 2026-06-11 stack assessment.

1. **JSON file storage has no cross-process safety** (`app/automations/*/storage.py`, `_shared/snapshot.py`, `_shared/prices.py` — plain `write_text`, no locking). The original "single-user risk accepted" rationale no longer holds: the app is multi-user with auth and prod runs 3 gunicorn workers, so even `threading.Lock` wouldn't suffice. Concurrent writes can lose updates or truncate files. Fix: move this state into SQLite (migrations + helpers already exist) or use OS-level file locking.
2. **No disaster-recovery runbook for the VPS** — prod, dev, nginx, and the DB share one machine at one provider. Mitigated: the hosting provider backs up the VPS itself, the DB has its own backups, and `docs/manuals/server/manual_server.typ` contains a from-scratch rebuild runbook (packages, systemd units, nginx blocks, certbot, firewall). Remaining: keep it in sync with `docs/TECHNICAL.md` §Infrastructure.
3. **Data ingestion is manual Excel exports** (`docs_input/`, upload-based stock sync) — the real scaling bottleneck, hit long before Flask or SQLite limits. The SmartBill/ERP → pipeline API integration (strategic plan, Pilon 5.1) should be prioritized above the Postgres migration.
4. **No background-job mechanism** — forecasts run via PowerShell CLI, syncs are request-driven, but Pilon 5's roadmap (weekly AI sales briefs, automated bonus emails, churn flags) is all scheduled work. No Celery needed: cron on the VPS calling CLI scripts covers 2026–2027 — just design upcoming features as CLI-invocable jobs, not Flask routes.
5. **Shared `call_claude()` helper** — 6 separate Anthropic call sites (`app/ai.py`, `forecast_agent.py`, `claude_client.py`, `post_generator.py`, `campaign_generator.py`, `ai_suggestions.py`); error handling and model config drift between them.
6. **SQLite → Postgres migration** — trigger on symptoms ("database is locked" errors), not on the revenue milestone; with WAL + busy_timeout this likely stays dormant for a long time. The strategic plan anticipates it at ~30M RON revenue.
7. **`Start-Hub.ps1` launches the Flask dev server** (`python app\app.py`) instead of `waitress`, which is in requirements for this purpose. Dev-only launcher, low risk, quick fix.
8. **Merge `postari/instagram.html` + `postari/facebook.html`** (was listed under `campanii/`; templates moved). Needs UI testing.
9. **eMAG/stock CSS still lives in the global `style.css`** — separate when next touching those styles.
10. **Accessibility pass** — only 6 `aria-label`s across all templates.
11. **Remove the stale `scripts/` line from `.gitignore`** — if anyone recreates that directory, its files would silently never be committed.
12. **Off-VPS copy of DB backups** (low priority by decision 2026-06-11: the hosting provider backs up the whole VPS). If ever needed: pull `data/backups/` to a local machine via scheduled `scp` — admins can also download backups manually from `/admin/db`.

### Resolved (kept for the record)

- ~~`queries.py` connection leaks~~ — the `app/queries/` package now goes through `db.query()`/`get_db()`, which close transient connections in `finally` (request-scoped ones close on teardown)
- ~~`SHOPIFY_SHOP` vs `SHOPIFY_SHOP_DOMAIN` mismatch~~ — `config.py` uses only `shopify_shop_domain`
- ~~`scripts/` vs `tools/` directory-rule inconsistency~~ — `scripts/` no longer exists and CLAUDE.md no longer references it (the stale `.gitignore` line is item 11 above)
- ~~No backup strategy for `data/torb.db`~~ — delivered 2026-06-11: `app/backup_db.py` + `etl/backup_db.py` CLI, daily cron on prod, pre-deploy backup in CI, admin UI at `/admin/db` with guarded restore, 15-day retention/min 3 kept
- ~~`PRAGMA busy_timeout` missing~~ — added to `_PER_CONN_PRAGMAS` in `app/db.py` (5s)

---

## Infrastructure — pending maintenance & open items

Current server facts live in `docs/TECHNICAL.md` §Infrastructure; resolved narratives in `docs/TECHNICAL_history.md`.

- **🔁 Reboot pending (schedule a brief maintenance window).** Login banner shows
  `*** System restart required ***` (kernel update `6.8.0-117` applied) plus ~17 updates available
  (4 ESM security). A reboot also **fully recycles the OpenClaw gateway user session** — closing the
  long-standing "stale `docker`/`sudo` supplementary groups on the live process" residual item. Plan:
  announce downtime, `sudo apt update && sudo apt full-upgrade`, then `sudo reboot`; afterwards verify
  both apps (`/healthz` on prod + dev) and the OpenClaw widget.
- **Add swap** — box has 0 swap (2 vCPU / 2.8 GB). See server manual ch. "Stare curentă".
- **Delete stray pre-engine DB backup** — `data/torb.db.bak.20260525_010848` (102 MB, from 2026-05-25) on prod can be deleted once the backup system is verified.
- **Secrets vault residual** (vault migration done 2026-06-17 — see `docs/TECHNICAL_history.md`): the laptop SSD makes overwrite-delete of the old plaintext non-guaranteed — full-disk encryption (BitLocker) is the real at-rest protection; confirm it's on.
- **Strict nonce-based CSP** (follow-up to the pragmatic policy shipped 2026-06-17): requires refactoring 17 templates (99 inline event handlers → `addEventListener`, ~25 inline `<script>` blocks externalized/nonce'd, inline `style=` → CSS classes).
- **OpenClaw under a dedicated low-priv user** (long-term) — currently shares the `openclaw` deploy/admin account; removes the shared-identity root cause behind both the exec risk and the earlier sudo lockout.
- **SMTP long-term** — password-reset email is tied to a personal Gmail (App Password); consider a dedicated mailbox / transactional provider.

---

## Forecast page audit findings (2026-07-02)

Full analysis (architecture, both suggestion-algorithm implementations, column-by-column reference, API, 20 ranked issues + recommended fix order in §7): `docs/analysis/forecast_page_analysis.md`.

**10 P0/P1 items fixed 2026-07-03** (plan `docs/plans/2026-07-03-forecast-p0-p1-fixes.md`, ledger `.superpowers/sdd/progress.md`): A3, A1, A5, B1, B2, B6, C3, C5, B3, A4+C1. See `context/STATUS.md` 2026-07-03 entry for the full list.

**D2 + 2 Minor findings also fixed 2026-07-03** (same day, follow-up cleanup batch): mojibake repair, dead-code removal, test-ordering fix — see ledger for commits.

**A2/C4/B8/D1/D-DUP fixed 2026-07-03** (Opus session): status-vocabulary migration (0016) + empty-status guard (A2/C2), foreign_keys pragma (C4), order Excel round-trip column (B8), dead `forecast_stoc()` removed (D1), shared `_ro_hu_split()` extracted (D-DUP, behaviour-preserving). See `context/STATUS.md` 2026-07-03 entry + ledger.

Still open — **owner validation required** (these change suggestion numbers; tie into the open Basilur forecast validation, STATUS item 4b):
- **B4 — Demand overstated for delisted/declining SKUs — addressed 2026-07-04, pending default flip**: the client × article model (`app/forecast/pair_engine.py`, behind `?model=nou`, see `app/forecast/README.md`) computes demand per client×article pair with zero-filled months and an adaptive `SUSPECT` delisting status per pair, so dead pairs drop out of the article forecast instead of diluting slowly. Not yet the default — needs owner validation via `?compare=1` before the toggle flips (same validation track as item 4b).
- **B5 — In-transit counts forever, even overdue**: full in-transit qty is subtracted regardless of ETA; orders weeks past ETA still suppress suggestions. Fix option: exclude/flag transit overdue by > X days. Needs owner call on X.
- **B7 — Urgency semantics differ per tab**: Tab 1 fixed 30/60-day thresholds vs Tab 2 lead-time-based. Needs owner call on which is canonical (fixed thresholds are meaningless for a 120-day-lead brand).

**Page-vs-Excel velocity divergence (analysis §4.1) — resolved 2026-07-03** via a runtime `3 ani | 90 zile` toggle next to Export: both the page (Vânz./lună, Zile stoc) and the Excel export now run off `forecast_stoc_extended(vel=)` and match for the selected mode. Sug. RO/HU stay seasonal. Owner still to pick a *default* basis if they don't want the toggle default (`3 ani`).

**Client × article model (2026-07-04)** — new procurement-forecast core shipped behind `?model=nou` (default off): zeros-in-mean, seasonality cap/gate, adaptive delisting signal, safety-stock (`coef × forecast`) + bax rounding, and a "Parametri forecast" config screen (`forecast_config` table + `/forecast/setari`) are all delivered — see `app/forecast/README.md` for the full breakdown. Deferred/blocked items needing owner decisions are tracked in `docs/decision.html` ("Runda 2", items 5–10): out-of-stock month exclusion (§4.4, item 5), MOQ floor (§8, item 6), full DELISTAT/REACTIVAT confirmation lifecycle (§5, item 7), new-listing ramp-up (§6, item 8), keeping the RO/Export split (item 9), nightly-batch vs. on-demand recalculation (§10, item 10).

---

## Product / AI opportunity backlog

The prioritized opportunity analysis lives in `docs/BUSINESS.md` §5–6. Still open:

- **C. Weekly sales rep AI brief** (Priority 2)
- **D. Client churn/reactivation detector** (Priority 2)
- **E. Sales plan pre-population** (Priority 2)
- **G. Kaufland order monitoring / early warning** (Priority 3 — 41.4% revenue dependency)
- **H. eMAG/online competitive intelligence** (Priority 3)
- Not yet explored: HoReCa lead generation agent · supply chain risk monitor (Sri Lanka / USD/RON) · basilurtea.ro D2C relansare (Shopify vs WooCommerce decision pending)
