# Seasonality & peak-season financing — what the data can answer (2026-08-20)

Owner asked eight questions about how seasonal the business is and whether it can
finance a doubled pre-season stock. This note records **which questions the system
can answer today, from which tables, and which ones have no data behind them** —
plus the tool that produces the numbers.

The figures themselves are deliberately **not** copied into this file. `data/torb.db`
is gitignored and never leaves the owner's machine, so a number pasted here would go
stale on the next import and could not be re-derived. Run the tool instead:

```
python etl/analyze_seasonality.py --out docs/analysis/2026-08-20-sezonalitate.md
```

It is read-only, prints a Romanian markdown report, and takes `--sectiuni q1,q2,…`
to run a subset and `--an` to move the current year used by Q5/Q6.

**Run `--canale` first.** Every channel figure depends on mapping the ERP's raw
`tip_client` onto TT / PHARMA / IKA / DISTRIBUITOR. That mapping is `CANAL_GROUPS`
in the script, seeded from the values the codebase already knows about
(`app/forecast/data.py::_normalize_canal`). Any value not in it is reported as
**NECLASIFICAT** with its revenue rather than being folded into a default bucket, so
a mis-mapped channel is visible instead of silently shifting the TT share.

## Question by question

| # | Question | Data path | Status |
|---|---|---|---|
| 1 | Quarterly share 2025 + 2026 H1, TT / Pharma / total | `tranzactii` (`an`, `luna`, `val_neta`, `tip_client`) | **Answerable in full** |
| 2 | Weakest months + invoiced value per TT client / agent | `tranzactii` | **Answerable in full** |
| 3 | Counter-seasonal brands | `tranzactii` (`furnizor` × `luna`) | **Answerable in full** |
| 4 | Can we finance doubling the stock? | `pnl_balante_raw` (balance-sheet accounts) | **Partial** — see gap 1 |
| 5 | Breakeven per agent in summer | `pnl_balante_raw` (class 6) + `tranzactii` margins | **Partial** — see gap 2 |
| 6 | Max discount agents may grant; per brand or per portfolio? | `tranzactii.discount_pct`, `conditii_comerciale`, `pricing_config` | **Partial** — see gap 3 |
| 7 | Expired / damaged goods at the distributor | — | **No data** — see gap 4 |
| 8 | How much can credit limits rise in peak season? | `solduri_neincasate` (`plafon`, `sumdeincas`, `term_pl_cl`) | **Answerable in full** |

### Method notes

- **Everything is `val_neta`** (net of VAT and of granted discounts), the same base the
  dashboards use, so shares here reconcile with `/dashboard`.
- **Q1 linearity** is measured as the largest deviation of a quarter's share from a flat
  25% (in pp) plus the peak/trough ratio. Under 5 pp reads as linear, 5–10 pp as
  moderately seasonal, above that as strongly seasonal. 2026 has only H1 loaded, so its
  quarters are shares of H1, never of a full year — they are not comparable to 2025's.
- **Q2 ranks months on complete years only.** Including a partial current year would push
  its untouched months to the bottom of the ranking as artificial zeros. Per-year detail
  is still printed next to each month.
- **Q3 seasonality index** = a brand's share of its own annual revenue in month *m*,
  divided by 1/12. A brand is called counter-seasonal only when its summer index is above
  1 *while the firm's is below 1* — rising against the company's own trough is the claim
  being tested, not merely having a flat summer.
- **Q5 allocates fixed costs by revenue share**, because nothing in the system holds costs
  per profit centre. It is the simplest defensible rule and it should be read as such: an
  agent whose route costs more than their revenue share suggests will have their breakeven
  understated. The script uses `rulld` (the month's own debit turnover), matching
  `app/pnl_logic._entity_monthly` — `rulcd` is the cumulative YTD figure and summing it
  across months would inflate OPEX several-fold.
- **Q8's peak factor** is the peak month's invoicing divided by the average month, applied
  to each client's current exposure to size the limit they would need. Increases are
  proposed only for clients with no overdue balance; for the rest an exceeded ceiling is a
  collection problem, not a limit problem.

## The four data gaps

**1. Bank credit lines are not in the system (blocks a complete Q4).**
The trial balance shows how much has been *drawn* (519 short-term, 162 long-term), never
the **contracted ceiling** or the covenants, so the report can state the financing need
(= current stock value) and the liquid resources against it, but not the unused headroom.
Equally missing: the **payment schedule to external suppliers** — `solduri_neincasate`
covers receivables only, so nothing in the system says when import invoices fall due.
Those two numbers are exactly what decides whether doubling stock causes a payment
blockage; they have to come from the owner.

**2. OPEX is not split fixed vs. variable (weakens Q5).**
`pnl_mapping_conturi` classifies accounts into P&L lines, not into fixed and variable. The
breakeven therefore treats all OPEX as fixed, which overstates it: sales bonuses and
volume-driven transport fall with the summer volume they are computed on. Splitting the
mapping is an owner decision, and a small one — a third column on the existing table.

**3. There is no maximum-discount rule anywhere in the system (Q6 is descriptive only).**
No table holds a discount ceiling per agent, per client or per brand. What exists is:
- the **margin floors** in `pricing_config` — 30% minimum, below 25% needs director
  approval — which bound a discount only indirectly, through the margin left after it;
- the **discount actually granted**, line by line, in `tranzactii.discount_pct` /
  `discount_val`, which the report summarises per channel and per brand so the *de facto*
  ceiling is at least visible;
- `conditii_comerciale`, where the 2026 rows are **one total percentage per client**, with
  the per-brand itemization still owed by the owner (`docs/BUSINESS_LOGIC.md` §10). So the
  answer to "per brand or per total portfolio" is, as the data stands: **per total
  portfolio**, and the report counts how many rows are the exception.

**4. Lot and expiry data does not exist (Q7 cannot be answered at all).**
The ERP exports neither lot nor best-before date, on `stoc` or on `tranzactii`, so there is
no way to compute at-risk stock, run FEFO, or value the expiry exposure. Returns are not
flagged by reason either — credit notes land as negative `val_neta` rows, mixing expiry,
damage and commercial returns. And sell-out at the distributor's warehouse or on the
retailer's shelf never reaches the system: visibility stops at Torb's outgoing invoice.
The report prints the only measurable proxy (negative lines by month, mixed reasons) and
says plainly that it is a proxy. The underlying work is already a backlog item —
`docs/BACKLOG.md` §Aprovizionare, decisions 12+13.

## Tests

`tests/test_analyze_seasonality.py` covers the two places the report could be silently
wrong — the channel mapping (unmapped values must surface as NECLASIFICAT, never default
into TT) and the P&L turnover column (`rulld`, not `rulcd`) — plus analytic-account
resolution onto the synthetic parent and graceful degradation when a table is absent.
