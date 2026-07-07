# Torb — Status Execuție Plan Strategic 2026–2030

**Ultima actualizare:** 2026-07-06
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
- `[x]` **4b.** Forecast engine MVP (Faza 1) · *modul `forecast/` + pagina `/forecast` + export Excel; modelul client × articol e acum **implicit și unic** (flip 2026-07-05 după validare) — legacy + toggle-uri `?model=`/`?compare=1` + comutatorul 3ani/90zile eliminate; afișaj + export pe fereastra istorică. Deciziile 9/11 rezolvate; 6/12+13/14 în backlog. Vezi CHANGELOG.*

### Zilele 31–90 — Decizii strategice

- `[ ]` **8.** Livrare audit Celmar + Leonex → decizii rebranding, SKU, KAM, prima piață export · *deadline: 31 iulie 2026*
- `[ ]` **9.** Shortlist producători private label tea + decizie go/no-go · *până în septembrie 2026*
- `[ ]` **10.** Catalog corporate gifting B2B pregătit pentru campania Q4 2026 · *deadline: 31 iulie 2026*
- `[↑]` **11.** Margin audit SKU × client · *deadline: 15 iunie 2026 — depășit*
- `[ ]` **12.** Audit basilurtea.ro + plan relansare (Shopify vs WooCommerce) · *deadline: 30 iunie 2026*
- `[ ]` **13.** Documentare procese critice (comenzi, facturare, listing IKA) · *deadline: 31 iulie 2026*

---

## Livrat recent (detalii în CHANGELOG)

- `[x]` **Raportare clienți/produse + integritate branduri & identitate Auchan** (2026-07-07) — taburi + istoric per produs, fix branduri Auchan/HORECA/catalog (migrațiile 0028–0030), import Tobra pe cod mare + realiniere cod_produs (migrația 0031), pagina de produs unificată pe denumiri. Cereri owner 2026-07-07. Rămâne: owner reimportă/verifică fișierul Tobra iulie pe prod după deploy-ul 0031.
- `[x]` **Modul Comercial → Solduri neîncasate** (2026-07-05) — upload raport ERP + dashboard aging (carduri Nescadent/Scadent 7/30/60 + catch-all, tabel per client/agent/factură, filtrare pe card, export Excel). Referință = azi. Migrație 0021.
- `[x]` **Solduri: navigare drill-down + pagină facturi client** (2026-07-05) — agent → clienți → pagină client cu toate facturile deschise (emitere, scadență, termen, sumă, zile întârziere, categorie), export Excel per client, link către fișa de vânzări. Cerere owner 2026-07-05.
- `[x]` **Solduri: bucket-uri disjuncte + terminologie nouă** (2026-07-06) — intervale 1-7/8-30/31-60/>60 pe ambele părți (fără catch-all), redenumire „În termen” / „Scadență depășită” peste tot. Cerere owner 2026-07-06.

## În curs / blocaje active

- `[~]` **Modul Pricing & Ofertare** — strategie aprobată de owner 2026-07-06 (12 decizii în `docs/plans/2026-07-05-modul-pricing-ofertare.md` §7). Livrate și pushate 2026-07-06: F0 (fundație date, migrație 0022 + import), F1 (motor cost/marjă `pricing_engine`, marjă netă per client în `/preturi/<sku>`, migrație 0023 dedupe), F2 (simulator `/preturi/simulator` + propuneri de preț migrație 0025, articol nou manual `/preturi/nou`), migrația 0024 duce datele de pricing validate local pe dev/prod (JSON seed în git — sursele Excel rămân gitignored), F3 (fișiere client din propuneri: listare/modificare preț per template — Kaufland/Selgros/Fildas/Sezamo/generic, migrația 0026 — + ofertă cu poze embedded, `app/exports/listare_export.py`), runda 4 (clienți prospect, articole potențiale — migrația 0027 —, import ofertă furnizor nou `/preturi/import-oferta`, poze articol upload/URL + link basilurtea.com). F4 (fișă creare articole per propunere — template Auchan + generic) și F5 (actualizare prețuri furnizor existent cu diff, confirmare per linie și alertă la diferențe față de ultima comandă). **Toate fazele planului sunt livrate** — modulul e complet funcțional pe :5001 după deploy. Rămâne: validarea ownerului (fișiere generate vs. cele reale, corecții de layout după caz), defalcarea condițiilor (acum % total per client) și curățenia de date din raportul F0. Logică de domeniu: `docs/BUSINESS_LOGIC.md` §10. De rezolvat din raportul F0 (`Date pricinng&Logistica&Ofertare/rapoarte/`): 51 prețuri achiziție diferite DB vs fișier, condițiile seed-uite ca total per client trebuie defalcate de owner, curs USD 4.5 (DB) vs 4.6 (fișier), 9 SKU cu buc/bax contradictoriu, naming Toras/Torras (BACKLOG #13).
- `[~]` **Validare forecast Basilur** — hindcast 2025 Q4 manual blocată până când owner-ul livrează Excel stoc curent. Fix-ul A1 (coduri export HU) e livrat 2026-07-03 — cifrele HU/export ar trebui reverificate de owner înainte de validarea finală.

---

## Next immediate step

**Prioritate #1 — reglaj + validare finală forecast Basilur.** Flip-ul la modelul client × articol e făcut (2026-07-05, implicit și unic). Pasul următor: dacă pragul INACTIV (205/473 SKU pe Basilur) pare prea agresiv pentru branduri cu livrare lentă, se ridică `taiere_inactiv_luni` (6 → 9–12) din `/forecast/setari`; hindcast-ul 2025 Q4 rămâne blocat până owner-ul livrează Excel-ul de stoc curent. Toate cele 14 decizii owner sunt închise: 9 (split RO/export) + 11 (prag preț 1%, `prag_alerta_pret_pct`) rezolvate; 6 (MOQ), 12+13 (stoc mort + raport ERP loturi/BBD, o implementare) și 14 (umbrelă „Notificări") trecute în backlog (`docs/BACKLOG.md` §Aprovizionare). Deferate din spec: ramp-up listare nouă §6, confirmare manuală delistare §10, vederea „an curent vs. an trecut" §9, F2/F3/F4. Rămân B5 (prag „tranzit expirat") și B7 (semantica urgenței per tab). Vezi `docs/plans/2026-07-04-forecast-spec-completion.md`.
