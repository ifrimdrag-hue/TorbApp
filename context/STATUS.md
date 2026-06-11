# Torb — Status Execuție Plan Strategic 2026–2030

**Ultima actualizare:** 2026-06-11
**Document referință:** `context/plan_strategic_5ani.md` (v1.0)
**Regulă:** actualizează acest fișier la fiecare schimbare de stare (nu la fiecare discuție). Legend: `[ ]` = neînceput · `[~]` = în lucru · `[x]` = livrat · `[!]` = blocat · `[↑]` = întârziat.

---

## Decizii strategice deschise (trebuie validate cu proprietarul)

| # | Decizie | Statut | Note |
|---|---|---|---|
| D1 | Acceptă board-ul teza de mix 45/35/20 către 2030? | `[ ]` | Necesită meeting |
| D2 | CAGR 38% realist sau target ajustat? | `[ ]` | — |
| D3 | Disponibilitate CapEx €3.5–5M pe 5 ani? | `[ ]` | Din profit + credit + fonduri EU |
| D4 | Deschidere pentru capital extern minoritar (2028–2029)? | `[ ]` | Opțional, nu obligatoriu |
| D5 | Alocare owner per pilon (1–5) | `[ ]` | Cu KPI trimestrial |
| D6 | Selecție 3 OKR-uri 2026 din North Star Metrics | `[ ]` | — |

---

## Acțiuni 90 de zile (aprilie–iulie 2026)

### Săptămânile 1–2 — Validare & aliniere

- `[ ]` **1.** Meeting validare teză strategică cu proprietarul/board
- `[ ]` **2.** Alocare owner per pilon (5 owners)
- `[ ]` **3.** Stabilire 3 OKR-uri 2026

### Zilele 1–30 — Pornește motorul

- `[x]` **4.** Pipeline date Baza → Dashboard managerial · *livrat: webapp Flask + 131,898 tranzacții SQLite + auth + blueprint refactor*
- `[↑]` **5.** Bonusare automată lunară · *deadline: 31 mai 2026 — ÎNTÂRZIAT (4 zile). Următor pas imediat.*
- `[ ]` **6.** Brief intern pentru audit Celmar + Leonex (scope, buget, timeline)
- `[ ]` **7.** Conversație confidențială de retenție cu Bogdan Dragnea · *deadline: 30 iunie 2026*
- `[~]` **4b.** Forecast engine MVP (Faza 1) · *modul `forecast/` + pagina `/forecast` + export Excel livrate; validare owner pe Basilur înainte de rollout complet (Faza 2)*

### Zilele 31–90 — Decizii strategice

- `[ ]` **8.** Livrare audit Celmar + Leonex → decizii rebranding, SKU, KAM, prima piață export · *deadline: 31 iulie 2026*
- `[ ]` **9.** Shortlist producători private label tea + decizie go/no-go · *până în septembrie 2026*
- `[ ]` **10.** Catalog corporate gifting B2B pregătit pentru campania Q4 2026 · *deadline: 31 iulie 2026*
- `[ ]` **11.** Margin audit SKU × client · *deadline: 15 iunie 2026 — 11 zile rămase*
- `[ ]` **12.** Audit basilurtea.ro + plan relansare (Shopify vs WooCommerce) · *deadline: 30 iunie 2026*
- `[ ]` **13.** Documentare procese critice (comenzi, facturare, listing IKA) · *deadline: 31 iulie 2026*

---

## În curs / blocaje active

- `[↑]` **Bonusarea automată** (item 5) — 4 zile întârziere față de deadline 31 mai. Prioritate maximă.
- `[~]` **Validare forecast Basilur** — hindcast 2025 Q4 manual blocată până când owner-ul livrează Excel stoc curent.

---

## Livrări recente

- **2026-06-11 — Status conexiune (connDot) servit din cache server-side.**
  Tabel `connection_status` (migration 0010) + helper `app/connection_cache.py` cu TTL 3 min — maxim un apel API extern eMAG/Shopify per platformă per fereastră, partajat între toți utilizatorii. Rutele `connection-test` neschimbate ca URL/shape (câmpuri noi: `cached`, `checked_at`); tooltip-ul connDot afișează ora verificării. 87 teste trec.

- **2026-06-10 — Audit utilizator pe sincronizările de stoc.**
  `sync_sessions.user_id` (migration 0008) înregistrează cine a rulat fiecare sync eMAG/Shopify; username afișat în istoricul din `/stocuri`. Tabelele redenumite `shopify_sync_*` → `sync_sessions`/`sync_rows` (migration 0009 — prefix obsolet de când sunt multi-platform). Teste noi pentru istoric eMAG + fixture comun `testadmin_id`. 79 teste trec.

- **2026-06-04 — Technical debt phases 1–3 livrate + DB cleanup.**
  - Dead code eliminat: `etl/init_forecast_tables.py`, `app/db_stock.py`, `data/stock.db`, tabel orfan `clienti_export_old`.
  - Model AI actualizat: `claude-opus-4-7` (retras) → `claude-sonnet-4-6` în `app/config.py`.
  - CI/CD hardened: pas explicit `python migrations/runner.py` înainte de `systemctl restart` — migrare eșuată abortează deploy-ul, nu cade app-ul.
  - `tests/conftest.py` conectat la migration runner (289 linii schemă manuală → 3 linii) — schema de test mereu în sync cu producția.
  - `app/queries.py` (3,236 linii) → pachet `app/queries/` cu 9 module de domeniu; `__init__.py` re-exportă tot — zero modificări în blueprint-uri.
  - Tabelele forecast mutate în migration 0004 (auto-aplicate la pornire Flask).
  - Documentație corectată: `CLAUDE.md` paths, `README.md`, `docs/STATUS.md`, `context/project_ai_opportunities.md`.

- **2026-06-03 — Shopify stock sync livrat.**
  Integrare API Shopify (GraphQL Admin API 2025-04, OAuth client credentials). Pagina unificată `/stocuri` — switch radio eMAG/Shopify. Logs cereri: `logs/shopify_req.json`.

- **2026-05-28 — Comprehensive code audit livrat.**
  Patru agenți paraleli: backend, frontend, infrastructură, AI modules. Aplicat: `SESSION_COOKIE_SECURE` env-controlled, `LOG_LEVEL` env-controlled, 500 error handler, auth gate fix pentru blueprint statics, open-redirect mitigation, `import_stoc.py` path fix, 10 MB upload check, filenames dinamice în orchestrator, `BadRequestError`/`APIStatusError` în ai_suggestions, JSON error logging în campaign/auto_post generators, light theme cu sidebar dark, nav collapsibil localStorage, template Trendyol pachete. **66 teste trec, ruff zero violații.**

- **2026-05-23 — Autentificare completă livrat (v0.4.0).**
  Login/logout, "Ține-mă minte", forced password reset, reset via email (token SHA-256, 1h), rate limiter, audit log, admin UI (create/edit users, toggle active), role-based access (`admin`/`manager`/`viewer`), CSRF, Blueprint `/auth` + `/admin`.

- **2026-05-23 — Blueprint refactor + migration runner (v0.2.0–v0.3.0).**
  Reorganizare proiect: ETL → `etl/`, scripturi → `scripts/`, blueprint-uri în `app/blueprints/`. Sistem versionat migrări (`migrations/runner.py`). 61 teste. CI/CD: lint + test + pip-audit + deploy + smoke-test VPS.

- **2026-04-19 — Forecast engine MVP livrat (v0.1.0).**
  Modulul `forecast/` cu AutoETS + overlay Q4 + dampener vară, alocare middle-out brand→SKU, reorder cu safety stock, pagina `/forecast`, export Excel 4 sheet-uri, `import_stoc.py`.

  **Backtest Faza 1 (3 folds × 13 săpt):**
  - Toras: WAPE 40%, bias +7% — ✓
  - Celmar: WAPE 53%, bias −19%
  - Basilur: WAPE 93%, bias −27% — ⚠️ sub-prezice Q4. Necesită validare owner înainte de Faza 2.

---

## Next immediate step

**Prioritate #1 — Bonusare automată** (item 5, întârziat). Următor: hindcast Basilur cu owner-ul (item 4b) paralel cu margin audit (item 11, deadline 15 iunie).
