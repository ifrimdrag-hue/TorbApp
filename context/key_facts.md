# Torb — Key Facts & Data File Map

Business facts and the input-file map. Read when you need business context or need to locate a data file — not needed for routine code edits.

## Key facts (do not re-derive from scratch)
- Torb distributes **12 brands** (not just Basilur). Main ones: Basilur 31%, Toras 22%, Leonex 20%, Celmar 13%.
- 2025 total revenue: ~15M RON across 3,297 clients
- Biggest risk: Bogdan Dragnea = 55.6% of all sales. Kaufland = 41.4% of revenue.
- The reporting dashboards are well-designed templates but **contain no data** — the core gap is a missing data pipeline from raw transactions to management reports.

## File map
- `context/torb_background.md` — company background research (note: incomplete on brand portfolio)
- `docs_input/` — all Excel data files (gitignored)
- `docs_input/vanzari_01.03.2026.xlsx` — main sales database (Baza sheet = raw transactions)
- `docs_input/bonusare_torb_structura_echipa.xlsx` — team structure + KPI/bonus system
- `docs_input/TORB_Dashboard_Managerial_FMCG.xlsx` — executive dashboard template (empty, needs pipeline)
- `docs_input/model_livrabil_plan_vanzari_RON.xlsx` — individual sales plan template
