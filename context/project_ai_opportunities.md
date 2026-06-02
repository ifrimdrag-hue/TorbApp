---
name: Torb AI Opportunities — Prioritized
description: AI/agentic automation opportunities identified for Torb Logistic, ordered by impact and effort.
type: project
originSessionId: 080cd978-3a33-4caf-9f60-9e7f2b318b4e
---
## Priority 1 — Quick Wins (data already exists, just needs pipeline)

**A. Auto-populate dashboards from Baza**
Connect vanzari Baza sheet → TORB_Dashboard_Managerial_FMCG.xlsx INPUT sheets automatically each month.
Stack: Python + openpyxl/pandas + Claude API for narrative commentary.
Why: Dashboard is currently empty. Data exists. This is a missing pipe, not a missing feature.

**B. Automate bonus calculation**
Read actuals from Baza → compute KPI scores per role → fill 06_Centralizare.
Bonus system is fully designed (05_Calcul_Bonus has complete payout logic). Just needs to be connected to actual sales data.

## Priority 2 — Strategic, Medium Effort

**C. Weekly sales rep AI brief**
Auto-generate Monday morning email per rep: YTD vs. target, clients at risk (no recent order), top SKUs, suggested focus.
Stack: Python + Claude API + email/WhatsApp delivery.

**D. Client churn/reactivation detector**
Flag clients from 3,297 active who haven't ordered in 60/90 days.
Generate prioritized call list per TT agent with context.

**E. Sales plan pre-population**
Pre-fill model_livrabil_plan_vanzari_RON.xlsx for each rep from historical Baza data.
Suggest phasing based on 2025 monthly pattern, pre-populate client opportunities.

## Priority 3 — Higher Value, More Setup

**F. Demand forecasting**
2+ years of monthly data by SKU/brand/client. Clear seasonality (Oct-Dec peak).
Output: recommended stock orders per brand 4-6 weeks ahead.
Addresses the debt issue (overstock financing).

**G. Kaufland order monitoring**
Weekly alert on Kaufland order volume trend vs. same period last year.
41.4% dependency = early warning system is critical.

**H. eMAG/online competitive intelligence**
Monitor competitor pricing and listing quality on eMAG for Basilur.
Auto-generate improved product copy for underperforming listings.

## Not Yet Explored
- basilurtea.ro Shopify integration possibilities
- HoReCa lead generation agent
- Supply chain risk monitor (Sri Lanka / USD/RON)
