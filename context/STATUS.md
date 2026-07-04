# Torb — Status Execuție Plan Strategic 2026–2030

**Ultima actualizare:** 2026-07-04
**Document referință:** `docs/BUSINESS.md` §7 — Plan Strategic 2026–2030 (v1.0)
**Regulă:** actualizează acest fișier la fiecare schimbare de stare (nu la fiecare discuție). Legend: `[ ]` = neînceput · `[~]` = în lucru · `[x]` = livrat · `[!]` = blocat · `[↑]` = întârziat.
**Istoric livrări:** rezumatele implementărilor livrate stau în `CHANGELOG.md`, nu aici — acest fișier ține doar starea curentă (decizii deschise, acțiuni 90 de zile, în curs/blocaje, pasul următor).

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

- `[x]` **4.** Pipeline date Baza → Dashboard managerial · *livrat (v0.1.0) — vezi CHANGELOG*
- `[x]` **5.** Bonusare automată lunară · *livrat 2026-06-16 (`feat/bonus-redesign`) — modul bonus config-driven cu flux de închidere lună; detalii în CHANGELOG*
- `[ ]` **6.** Brief intern pentru audit Celmar + Leonex (scope, buget, timeline)
- `[ ]` **7.** Conversație confidențială de retenție cu Bogdan Dragnea · *deadline: 30 iunie 2026*
- `[~]` **4b.** Forecast engine MVP (Faza 1) · *modul `forecast/` + pagina `/forecast` + export Excel livrate; nucleul client × articol livrat 2026-07-04 în spatele `?model=nou`; validare owner pe Basilur înainte de rollout complet (Faza 2). Vezi CHANGELOG.*

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

## Next immediate step

**Prioritate #1 — Validare forecast Basilur cu owner-ul** (item 4b), paralel cu margin audit (item 11, deadline 15 iunie — depășit). Nucleul modelului client × articol e livrat (2026-07-04) în spatele toggle-ului `?model=nou` (implicit tot `actual`) — pasul următor e ca owner-ul să valideze cifrele prin `?compare=1` înainte să schimbăm implicitul, plus deciziile 5–10 din `docs/decision.html` (rupturi de stoc §4.4, MOQ §8, ciclu delistare §5, ramp-up listare nouă §6, split RO/Export, momentul recalculării §10). Rămân și B5 (prag „tranzit expirat") și B7 (semantica urgenței per tab) din auditul `/forecast` — vezi `docs/BACKLOG.md` §Forecast (B4 e acum rezolvat de noul model, condiționat de flip-ul de implicit).
