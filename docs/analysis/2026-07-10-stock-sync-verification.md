# Stock-sync verification: ERP vs eMAG vs Shopify (2026-07-10)

Owner reported that an ERP `codmare` renumbering may have broken the stock sync.
Verified the ERP warehouse report (`stoc 10.xls`, 844 rows / 335 unique SKUs /
263 unique EANs / 383,744 units) against live platform exports from the same day:

- eMAG: `update-offer-stock-2026-07-10-*.xlsx` (Oferte sheet, 305 offers), matched on EAN — same key the sync uses.
- Shopify: inventory CSV export (492 variants at "Shop location"), matched on normalized `codmare` vs variant SKU — same key the sync used before the EAN fallback.

Quantities aggregated per key across lots, exactly like the sync. Safety
threshold 5 (stock ≤ 5 is pushed as 0) applied when judging "expected" values.

## Verdict

- The **eMAG** match key (EAN) survived the renumbering — all differences are
  either normal drift since the last sync or the intended threshold zeroing.
- The **Shopify** match key (`codmare` ↔ variant SKU) did **not** survive it —
  several live products lost their match and their Shopify stock froze.
  Fixed in code the same day: EAN fallback matching (see CHANGELOG 2026-07-10).

## eMAG (305 offers)

| Category | Count | Meaning |
|---|---|---|
| Stock identical | 86 | OK |
| Stock differs — eMAG > ERP | ~77 | Warehouse sales since last sync; next sync corrects them (largest: Celmar Mușețel +438, Torras +264/+240, Leonex +140/+135) |
| Stock differs — eMAG 0, ERP 1–5 | ~25 | Intended: safety threshold ≤ 5 → pushed as 0 |
| EAN absent from ERP report, stock 0 | 110 | No impact |
| **EAN absent from ERP report, stock > 0** | **7** | **Never updated by sync — frozen stock, oversell risk** |

The 7 frozen offers:

| EAN | eMAG stock | Product |
|---|---|---|
| 5948593001033 | **1000** | Biluțe de vată Leonex Cotton White — other Leonex EANs (…000890, …001019) are in the report; either the EAN changed in the ERP or the 1000 was set manually |
| 4792252100541 | 36 | Moroccan Mint "Oriental" tin |
| 4792252920705 | 24 | Basilur Bergamotă 100g |
| 4792252920729 | 24 | Basilur Sencha 100g |
| 4792252936805 | 24 | Basilur Pu-erh 100g |
| 4792252920682 | 9 | Basilur English Afternoon loose 100g |
| 4792252916487 | 8 | Basilur Moroccan Mint 100g |

Duplicate EANs on two different eMAG offers each (sync sets both to the same
stock; if they are different physical products one has a wrong EAN):
`4792252945142` (White Tea Mango Orange refill + doze), `4792252932821`
(Winter Hollydays + Christmas Tree).

## Shopify (492 variants at "Shop location")

| Category | Count | Meaning |
|---|---|---|
| Stock correct (incl. threshold) | 117 | OK |
| Stock differs — Shopify > ERP | 48 | Drift since last sync; next sync corrects (2 of them fall under the threshold and will be zeroed) |
| SKU absent from ERP report, stock 0 | 310 | No impact |
| **SKU absent from ERP report, stock > 0** | **17** | Frozen before the EAN fallback; several are the renumbering victims below |

Renumbering victims — product exists in the ERP report under a **different
codmare** (name-based identification, to be confirmed via EAN by the owner):

| Shopify SKU (stock) | Product | ERP codmare today |
|---|---|---|
| 70177-00 (48) | Specialty Classics Earl Grey, 25 bags | 70173-00 |
| 70184-00 (24) | Specialty Classics English Breakfast, 25 bags | 70290-00 |
| 70771-00 (9) | Specialty Classics English Afternoon, 100g | 70293-00 |
| 70427-00 (8) | Moroccan Mint loose 100g | 70419-00 |
| 72397/72400/72401/72402-00 (36 each) | Gin Tea Blue/Purple/Grey/Green editions | only 72403-00 (Pink) is in the report |

Remaining unmatched-with-stock SKUs without a clear ERP candidate (either truly
out of warehouse stock — meaning the Shopify stock is stale — or also
renumbered): 72317, 70170-00, 70781-00, 72315, 71701, 72253-00, 72170-00,
70226-00, 70773-00 (1–48 units each).

With the EAN fallback deployed, every one of these that shares a barcode with
an ERP row syncs again automatically; the rest surface in the preview's
"Negasite pe Shopify" / unmatched lists for manual cleanup.

Duplicate SKUs on two Shopify variants each (sync sets both to the same
stock): 70843, 71076, 70180, 72481, 70187, 80206, 80308, 80307.

## Owner actions

1. Run the eMAG + Shopify sync with a fresh report to clear the drift.
2. Clarify the 7 frozen eMAG EANs — especially Leonex 5948593001033 (1000 units).
3. Confirm the renumbered codmare pairs and decide whether to also fix the
   Shopify variant SKUs / barcodes so the primary match works again.
4. Clean up the duplicate EANs (eMAG) and duplicate SKUs (Shopify).

Tracked as BACKLOG item 14.
