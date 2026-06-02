---
name: Torb Data Files Reference Map
description: What each file in /docs_input/ contains, which sheets matter, and the data structure of the raw transaction data.
type: reference
originSessionId: 080cd978-3a33-4caf-9f60-9e7f2b318b4e
---
All files are in: `/Users/irusu/pdev/torb/docs_input/`

## Raw Transaction Data (source of truth)

### vanzari_01.03.2026.xlsx
**The main sales database.** Contains 2024 complete + 2025 complete + 2026 YTD (Jan-Feb).
Key sheet: `Baza` — row-level transactions with columns:
`Luna, An, datadl, nrdl, cantit, pvanz, tva, pcump, Val_B, Val_Net, Val_Achiz, Value_USD, Marja_B, Client, factout, numeag, procent, adr_livr, [SKU name]`
Other sheets are pivot tables built on Baza: Agent Gama Client Marja, Agent Gama An, Gama_Ani, Basilur luna an, top SKU, Online, Selgros pivots.

### raport Dragos 31_03_2026.xlsx
Sales analysis through March 2026. Has same Baza structure + pivot sheets broken down by agent (Bogdan, Oana, Claudiu separately). Useful for Q1 2026 margin analysis.

### vanzari 2025.xlsx
Full year 2025 — likely similar Baza structure. Not yet inspected in detail.

## Reporting & Planning Templates (currently empty)

### TORB_Dashboard_Managerial_FMCG.xlsx
8 sheets: DASHBOARD, README, CONTROL, INPUT_SALES, INPUT_PNL, INPUT_AR_AP, INPUT_INVENTORY, Input_PnL_Managerial.
Tracks: Net Sales, Gross Profit, Margin%, OPEX, EBITDA, Cash, DSO, Stock Days, DPO, CCC — by 6 brands (Basilur, Celmar, Delaviuda, Leonex, Solvex, Toras).
**STATUS: Template is empty. Needs data pipeline from Baza.**

### TORB_FMCG_FULL_AUTOMATED_DASHBOARD.xlsx / TORB_Dashboard_RO_RON_Calibrat_UPDATED.xlsx / FMCG_Executive_Dashboard_Advanced_Pharma_v2.xlsx
Additional dashboard variants. Not yet inspected in detail.

## Bonus & Team Structure

### bonusare_torb_structura_echipa.xlsx
7 sheets: 00_Instructiuni, 01_Echipa, 02_Rol_KPI, 03_Targeturi_2026, 04_Actuale_2026, 05_Calcul_Bonus, 06_Centralizare.
- 01_Echipa: 5 employee IDs (MGR_PHTT_01, KAM_IKA_01, KAM_MIX_01, AG_TT_01, AG_TT_02)
- 02_Rol_KPI: KPI weights per role (Net Sales, Margin, Active Clients, Collections, Forecast, Promo Exec)
- 05_Calcul_Bonus: Full bonus formula with payout curve and penalty logic (49 columns wide)
- 06_Centralizare: Monthly bonus tracker — **EMPTY, needs automation**

### simulator_bonus_1_om_avansat.xlsx / Target_bonusare/
Advanced bonus simulator and per-rep targets. Not yet inspected.

## Individual Rep Sales Plans

### Cantitativ_Claudiu2026.xlsx / Cantitativ_Oana2026.xlsx / Cantitativ_Bogdan2026.xlsx
Per-rep quantitative targets for 2026. Not yet inspected.

### model_livrabil_plan_vanzari_RON.xlsx
Sales plan template for each rep. Sheets: Liste, Instructiuni, Repere vanzari, Summary, Situatie actuala, Oportunitati, Target propus, Organizare flow.
- `Repere vanzari`: Pre-populated with aggregated benchmarks from vanzari_01.03.2026.xlsx (top clients, top brands, monthly phasing)
- `Summary`: Individual rep fills in name, role, clients, targets, top opportunities, blockers
- `Situatie actuala` / `Oportunitati` / `Target propus`: 200-300 row detail sheets (likely one row per client)

## Financial

### Bal Dec.pdf
December balance sheet. Not yet read.
