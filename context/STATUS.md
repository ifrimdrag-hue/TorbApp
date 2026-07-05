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
- `[x]` **4b.** Forecast engine MVP (Faza 1) · *modul `forecast/` + pagina `/forecast` + export Excel; modelul client × articol e acum **implicit și unic** (flip 2026-07-05 după validare) — legacy + toggle-uri `?model=`/`?compare=1` + comutatorul 3ani/90zile eliminate; afișaj + export pe fereastra istorică. Deciziile 9/11 rezolvate; 6/12+13/14 în backlog. Vezi CHANGELOG.*

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

**Prioritate #1 — reglaj + validare finală forecast Basilur.** Flip-ul la modelul client × articol e făcut (2026-07-05, implicit și unic). Pasul următor: dacă pragul INACTIV (205/473 SKU pe Basilur) pare prea agresiv pentru branduri cu livrare lentă, se ridică `taiere_inactiv_luni` (6 → 9–12) din `/forecast/setari`; hindcast-ul 2025 Q4 rămâne blocat până owner-ul livrează Excel-ul de stoc curent. Toate cele 14 decizii owner sunt închise: 9 (split RO/export) + 11 (prag preț 1%, `prag_alerta_pret_pct`) rezolvate; 6 (MOQ), 12+13 (stoc mort + raport ERP loturi/BBD, o implementare) și 14 (umbrelă „Notificări") trecute în backlog (`docs/BACKLOG.md` §Aprovizionare). Deferate din spec: ramp-up listare nouă §6, confirmare manuală delistare §10, vederea „an curent vs. an trecut" §9, F2/F3/F4. Rămân B5 (prag „tranzit expirat") și B7 (semantica urgenței per tab). Vezi `docs/plans/2026-07-04-forecast-spec-completion.md`.
