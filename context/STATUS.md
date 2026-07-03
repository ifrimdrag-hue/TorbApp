# Torb — Status Execuție Plan Strategic 2026–2030

**Ultima actualizare:** 2026-07-03
**Document referință:** `docs/BUSINESS.md` §7 — Plan Strategic 2026–2030 (v1.0)
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
- `[x]` **5.** Bonusare automată lunară · *livrat 2026-06-16 (branch `feat/bonus-redesign`): modul bonus reconstruit config-driven — obiective lunare per agent (vânzări, marjă, 9 game individuale, nr. clienți, clienți noi/gamă, încasări, scriptic), ponderi + valoare bonus configurabile, grilă payout cu praguri (gate 80%), default creștere +20% vs anul trecut aceeași lună, flux de închidere lună cu snapshot înghețat, management agenți din UI. Tabele: `bonus_config`, `bonus_lunar_config`, `bonus_obiective_strategice`, `bonus_payout_grid`, `bonus_istoric` (migrația 0011). Pagini: `/bonus`, `/bonus/obiective`, `/bonus/inchidere`, `/bonus/config`, `/bonus/clienti-noi-gama`.*
- `[ ]` **6.** Brief intern pentru audit Celmar + Leonex (scope, buget, timeline)
- `[ ]` **7.** Conversație confidențială de retenție cu Bogdan Dragnea · *deadline: 30 iunie 2026*
- `[~]` **4b.** Forecast engine MVP (Faza 1) · *modul `forecast/` + pagina `/forecast` + export Excel livrate; validare owner pe Basilur înainte de rollout complet (Faza 2)*

### Zilele 31–90 — Decizii strategice

- `[ ]` **8.** Livrare audit Celmar + Leonex → decizii rebranding, SKU, KAM, prima piață export · *deadline: 31 iulie 2026*
- `[ ]` **9.** Shortlist producători private label tea + decizie go/no-go · *până în septembrie 2026*
- `[ ]` **10.** Catalog corporate gifting B2B pregătit pentru campania Q4 2026 · *deadline: 31 iulie 2026*
- `[↑]` **11.** Margin audit SKU × client · *deadline: 15 iunie 2026 — depășit*
- `[ ]` **12.** Audit basilurtea.ro + plan relansare (Shopify vs WooCommerce) · *deadline: 30 iunie 2026*
- `[ ]` **13.** Documentare procese critice (comenzi, facturare, listing IKA) · *deadline: 31 iulie 2026*

---

## În curs / blocaje active

- `[~]` **Validare forecast Basilur** — hindcast 2025 Q4 manual blocată până când owner-ul livrează Excel stoc curent. Fix-ul A1 (coduri export HU) e livrat 2026-07-03 — cifrele HU/export ar trebui reverificate de owner înainte de validarea finală.

---

## Livrări recente

- **2026-07-03 — Buton „3 ani / 90 zile" pe pagina `/forecast` (aliniere ecran ↔ Excel).**
  Comutator segmentat lângă Export pe tabul Stoc: schimbă baza pentru coloanele afișate Vânz./lună + Zile stoc (badge-ul de urgență și sortarea urmează din Zile stoc). Sug. RO/HU rămân pe modelul sezonier (cantitățile de comandă nu se schimbă la un buton de afișare). Exportul Excel folosește acum aceleași date ca pagina (`forecast_stoc_extended(vel=)`, coloane curate) în loc de vechiul `forecast_stoc_brand`, deci ecranul și Excel-ul coincid pentru modul selectat; exportul respectă și filtrul de căutare. Implicit: `3 ani` (comportamentul anterior). Rezolvă divergența viteză pagină-vs-Excel (§4.1 din analiză) ca alegere la runtime. 173 teste trec, ruff curat.

- **2026-07-03 — Al doilea val de fix-uri `/forecast` (sesiune Opus): A2/C4/B8/D1/D-DUP.**
  Continuare directă a batch-ului P0/P1, implementat cu TDD (fără subagenți). 170 teste trec, ruff curat.
  - **A2 (+C2 status)** — vocabular statusuri normalizat: migrația `0016` pliază statusurile legacy capitalizate (`Emisa`/`Confirmata`→`confirmata`, `In tranzit`→`in_tranzit`, `Receptionata`→`livrata`); `comanda_update` refuză un status gol/whitespace (dar aplică restul câmpurilor din același apel), deci modalul nu mai poate scrie `status=''`. Toate listele `IN(...)` de tranzit standardizate la `('confirmata','in_tranzit')` — `export.in_transit_ro_hu` era doar-capitalizat și ar fi returnat 0 rânduri după migrare. Migrarea aplicată pe `data/torb.db` local după backup. ETL-urile scriau deja lowercase.
  - **C4** — `PRAGMA foreign_keys=ON` adăugat pe conexiunile aplicației, deci `ON DELETE CASCADE` funcționează (ștergerea unei comenzi îi șterge liniile în loc să lase orfani).
  - **B8** — coloană nouă `— Cantitate comandată` în exportul Excel al comenzii, ca fluxul „export → editează cantități → re-import" să funcționeze (importul cerea o coloană cu „COMAND").
  - **D1** — șters `forecast_stoc()` mort (0 apelanți; `forecast_stoc_brand` rămâne — încă folosit de exportul Excel).
  - **D-DUP** — extras `_ro_hu_split()` partajat de `build_suggestion` + 3 ramuri din `forecast_stoc_extended`; verificat identic numeric (Basilur, 293 + 240 SKU) înainte/după.
  Teste noi: `tests/test_order_status.py`, `tests/test_comanda_excel_roundtrip.py`, `tests/test_ro_hu_split.py`. **Rămase deschise — necesită validare owner (schimbă cifrele sugestiei):** B4 (medie SKU delistate), B5 (tranzit expirat contorizat la infinit), B7 (praguri urgență diferite per tab), plus divergența viteză pagină-vs-Excel (§4.1 din analiză). Detalii: `.superpowers/sdd/progress.md`.

- **2026-07-03 — 10 fix-uri P0/P1 pagina `/forecast` livrate direct pe `main`.**
  Plan `docs/plans/2026-07-03-forecast-p0-p1-fixes.md`, execuție agentică (subagent-driven development, 10 task-uri + review final pe fiecare + review whole-branch). Rezolvate din `docs/analysis/forecast_page_analysis.md`:
  - **A3** — șters endpoint mort `/api/comenzi/<id>/avanseaza`.
  - **A1** — split Export HU repornit: `clienti_export.cod_client` patch-uit direct în DB (`BRANDMIX`→`1429`, `HUNTRADE`→`1430`, cu backup prealabil), plus validare la adăugare cod client nou (respinge coduri fără tranzacții).
  - **A5** — preț de achiziție în valută (`costuri_landing`) afișat în tabul Stoc & Urgente.
  - **B1** — cardurile KPI numără SKU-uri distincte, nu loturi.
  - **B2** — „Zile stoc" exclude stocul în tranzit (coloana separată „cu tranzit" rămâne neschimbată).
  - **B6** — ETA tranzit preferă `costuri_landing.eta` peste `data_estimata_livrare` când există.
  - **C3** — interogare coduri export SQL-injection-safe (subselect în loc de f-string).
  - **C5** — cheile din `_listing_changes()` normalizate ca să se potrivească cu `build_suggestion()`.
  - **B3** — „Confirmă Comanda" exclude rândurile ascunse de filtru (aliniat cu `updateTotal()`).
  - **A4+C1** — `escapeHtml()` adăugat + folosit peste tot în `loadExportClients`/`addExportClient`/modal status/`sendAgentMsg`; atribute HTML mutate din string-uri interpolate în `data-*`; escapare extinsă și la ghilimele (`"`/`'`) după găsirea unui gap de context-atribut la review-ul final.
  Teste noi: `tests/test_forecast_queries.py` (6 teste) + 3 teste în `tests/test_flask_routes.py`. 165 teste trec, ruff curat. Neatinse (necesită decizie owner/Opus): A2 (migrare vocabular statusuri), D-DUP (unificare cod duplicat `build_suggestion`/`forecast_stoc_extended`), B4/B5/B7/B8. Detalii progres: `.superpowers/sdd/progress.md`.

  **Follow-up aceeași zi** — cele 3 itemi rămași din review-ul final rezolvați direct (fără subagenți, fix-uri mecanice): **D2** — reparate separatoare de comentarii `── ... ──` dublu-codate UTF-8 în `app/blueprints/forecast.py` (script pe bytes, nu Edit tool; singurul mojibake rămas în fișier — 303 apariții, doar comentarii). **Minor** — șters `get_export_codes()` mort din `app/forecast/forecast_logic.py`. **Minor** — `tests/test_forecast_queries.py` decuplat de ordinea de execuție (`_next_snapshot()` calculează data la runtime în loc de literali hardcodați crescători); verificat rulând testele în ordine inversă. 165 teste trec, ruff curat.

- **2026-07-02 — Constante business centralizate + cost real Torb pe vânzările Auchan.**
  Modul nou `app/business_constants.py` (excepția Auchan/Tobra: agent, coduri client, prefix factură, fereastră cost 30z), folosit de `import_vanzari_erp.py` + `import_vanzari_tobra_auchan.py`. Tabel nou `corr_vanzari_tobra` (migrația 0013): liniile Torb→Tobra (cod 719) sunt deviate acolo la importul ERP în loc să fie aruncate. Importul Auchan suprascrie `pret_cumparare` cu media simplă pe 30 de zile per `cod_produs` la data fiecărui rând (fallback: ultimul cost cunoscut, apoi valoarea din fișier) și recalculează `val_achizitie`/`marja_bruta`. Ordine încărcare: Vânzări ERP înainte de Vânzări Auchan (notat în UI). Necesită backfill: un re-import al fișierului ERP de vânzări.

- **2026-07-02 — Audit complet pagina `/forecast` (doar analiză, fără fix-uri aplicate).**
  Documentat în `docs/analysis/forecast_page_analysis.md`: arhitectura celor 5 taburi + agent AI, algoritmul de sugestie (ambele implementări), referință coloană-cu-coloană pentru tabul Stoc & Urgente, tot API-ul, plus 20 de probleme ierarhizate. Critice: (A1) split-ul Export HU e mort — `clienti_export` are codurile `BRANDMIX`/`HUNTRADE`, dar `tranzactii` folosește `1429`/`1430` → 0 potriviri, toate sugestiile HU sunt 0; (A2) statusurile legacy capitalizate din DB (`In tranzit` etc.) + modalul lowercase pot scrie `status=''` și scot comanda din calculul tranzitului — agentul AI nu vede deloc comenzile în tranzit; (B1) cardurile KPI numără loturi, nu SKU-uri; (B3) „Confirmă Comanda" include și rândurile ascunse de filtru. Ordinea de fix recomandată în §7 din document. Relevant pentru item 4b (validare forecast Basilur) — cifrele HU/export din pagina actuală nu sunt de încredere până la fix A1.

- **2026-07-01 — Organsia adăugat ca al patrulea brand virtual Basilur (branch `feat/organsia-brand`).**
  Produsele `B.ECO ORGANSIA*` (nume ERP) / `ORGANSIA - ...` (nume din lista de prețuri) erau etichetate greșit ca `Basilur`. Adăugat regula de derivare pe prefix în cele 3 module ETL (`import_stoc`, `import_vanzari_erp`, `import_vanzari_tobra_auchan`), override pe `produse` în `import_preturi.py`, seed lead-time 120 zile în `rebuild_db` + migrația `0012` (seed `termene_aprovizionare` + backfill istoric: ~20 stoc, ~718 tranzacții, 11 produse). Organsia apare acum ca al patrulea brand în raportul Basilur (`/raportare-basilur`, export Excel + PPT, culoare mov `#6f42c1`), plus dropdown-uri bonus/postări și prompturi AI. Logica celor 3 branduri virtuale documentată în `docs/BUSINESS_LOGIC.md`. Test nou `tests/test_derive_furnizor.py`; 139 teste trec, ruff curat.

- **2026-06-11 — Backup & restore DB livrat (prod).**
  Engine `app/backup_db.py` (SQLite online backup API, gzip, retenție 15 zile / min 3) + CLI `etl/backup_db.py` (backup/list/restore). Trigger: cron zilnic 02:30 pe VPS prod + backup automat pre-deploy în CI înainte de migrări. Pagină admin `/admin/db`: listă, backup manual, download, restaurare cu confirmare "RESTORE" (backup de siguranță automat + re-aplicare migrări). `PRAGMA busy_timeout=5000` adăugat în `app/db.py`. 101 teste trec (14 noi).

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

**Prioritate #1 — Validare forecast Basilur cu owner-ul** (item 4b), paralel cu margin audit (item 11, deadline 15 iunie — depășit). În aceeași discuție de validare intră și cele 3 decizii de algoritm rămase din auditul `/forecast` (B4 fereastră de mediere pentru SKU delistate, B5 prag „tranzit expirat", B7 semantica urgenței per tab) — vezi `docs/BACKLOG.md` §Forecast.
