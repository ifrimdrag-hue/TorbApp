# Torb — Status Execuție Plan Strategic 2026–2030

**Ultima actualizare:** 2026-04-19
**Document referință:** `plan_strategic_5ani.md` (v1.0)
**Regulă:** actualizează acest fișier la fiecare schimbare de stare (nu la fiecare discuție). Legend: `[ ]` = neînceput · `[~]` = în lucru · `[x]` = livrat · `[!]` = blocat.

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

- `[x]` **4.** Pipeline date Baza → Dashboard managerial · *livrat anterior: webapp Flask la app/ + 131,898 tranzacții în SQLite*
- `[ ]` **5.** Bonusare automată lunară · *deadline: 31 mai 2026*
- `[ ]` **6.** Brief intern pentru audit Celmar + Leonex (scope, buget, timeline)
- `[ ]` **7.** Conversație confidențială de retenție cu Bogdan Dragnea · *deadline: 30 iunie 2026*
- `[~]` **4b.** Forecast engine MVP (Faza 1) · *modul `forecast/` + pagina `/forecast` + export Excel livrate; necesită validare owner pe Basilur înainte de rollout complet*

### Zilele 31–90 — Decizii strategice

- `[ ]` **8.** Livrare audit Celmar + Leonex → decizii rebranding, SKU, KAM, prima piață export · *deadline: 31 iulie 2026*
- `[ ]` **9.** Shortlist producători private label tea + decizie go/no-go · *până în septembrie 2026*
- `[ ]` **10.** Catalog corporate gifting B2B pregătit pentru campania Q4 2026 · *deadline: 31 iulie 2026*
- `[ ]` **11.** Margin audit SKU × client · *deadline: 15 iunie 2026*
- `[ ]` **12.** Audit basilurtea.ro + plan relansare (Shopify vs WooCommerce) · *deadline: 30 iunie 2026*
- `[ ]` **13.** Documentare procese critice (comenzi, facturare, listing IKA) · *deadline: 31 iulie 2026*

---

## În curs / blocaje active

*(niciunul încă)*

---

## Livrări recente

- **2026-05-28 — Comprehensive code audit livrat.** Patru agenți paraleli (backend, frontend, infrastructură, AI modules) au analizat întreg proiectul. Aplicat: `SESSION_COOKIE_SECURE` env-controlled, `LOG_LEVEL` env-controlled, 500 error handler, auth gate fixed pentru blueprint statics, open-redirect mitigation în auth, `import_stoc.py` path fix în forecast blueprint, 10 MB upload check în campanii, filenames dinamice în orchestrator (nu mai sunt hardcodate la Mai-2026), `BadRequestError`/`APIStatusError` în ai_suggestions, JSON error logging în campaign/auto_post generators, light theme cu sidebar dark, nav-ul collapsibil cu localStorage, template Trendyol pachete. Infrastructură: `requirements.txt` curățat + `waitress` adăugat, `.gitignore` completat, `force_pw_reset=1` la seed admin, `.env.example` completat. **65/65 teste trec, ruff zero violații noi.**

- **2026-04-19 — Forecast engine MVP livrat.** Modulul `forecast/` cu schema SQLite (tabele `brands_config`, `stock_snapshot`, `forecasts`, `reorder_suggestions`, `forecast_runs`, `forecast_backtests`), motor AutoETS + overlay Q4 + dampener vara, alocare middle-out brand→SKU, reorder cu safety stock, pagina `/forecast` în Flask, export Excel cu 4 sheet-uri (Reorder/Forecast_Luna/Alerts/Metodologie), script `import_stoc.py` pentru stoc curent.

  **Rulare rapidă:** `python3 -m forecast.run --brand Basilur --horizon 20` → `http://localhost:5000/forecast?brand=Basilur`.

  **Backtest Faza 1 (3 folds × 13 săpt):**
  - Toras: WAPE 40%, bias +7% — ✓ în banda acceptabilă
  - Celmar: WAPE 53%, bias −19%
  - Basilur: WAPE 93%, bias −27% — ⚠️ sub under-prezice Q4. Necesită validare owner înainte de rollout complet (Faza 2). Posibile cauze: overlay Q4 conservator, doar 2 ani de istoric, shift 2025→2026.

---

## Next immediate step

**Validare forecast Basilur cu owner-ul:** hindcast 2025 Q4 manual, comparație cu intuiția, decizie go/no-go Faza 2. Paralel: owner livrează Excel stoc curent (doar atunci apar urgențele critical/high reale).
