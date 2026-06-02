---
name: Torb Key Risks & Data Gaps
description: Critical business risks and operational gaps identified from analyzing the actual data files — not from the background doc.
type: project
originSessionId: 080cd978-3a33-4caf-9f60-9e7f2b318b4e
---
## Risk 1: Agent Concentration — CRITICAL
Bogdan Dragnea = 55.6% of all 2025 revenue (8.35M RON out of 15M RON).
**Why:** Identified from sales agent breakdown in vanzari_01.03.2026.xlsx.
**How to apply:** Any AI workflow involving sales must treat Bogdan's pipeline as a special case. His absence or departure would be existential. Flag this whenever discussing sales automation or team planning.

## Risk 2: Client Concentration — CRITICAL
Kaufland = 41.4% of 2025 revenue. Top 5 clients = ~65% of revenue.
**Why:** Single retailer delisting could destroy the business.
**How to apply:** Recommend monitoring Kaufland order trends closely. Any demand forecasting must model Kaufland separately.

## Risk 3: Data Pipeline Gap — IMMEDIATE OPERATIONAL ISSUE
The managerial dashboard (TORB_Dashboard_Managerial_FMCG.xlsx) has a well-designed template but ALL cells are empty (zeros/nulls). The bonus centralization sheet (06_Centralizare in bonusare_torb_structura_echipa.xlsx) is also empty.
**Why:** Transaction data exists in the Baza sheets but is not being piped to dashboards automatically. Someone either updates these manually (slowly) or not at all.
**How to apply:** The #1 AI quick win is connecting the Baza data to these templates via an automated script. This is the foundation for everything else.

## Risk 4: Multi-brand Management Complexity
12 brands with different margins, clients, and channels. Without automated tracking, margin dilution on lower-margin brands (Toras, Leonex) may go unnoticed vs. premium Basilur.
