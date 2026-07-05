# Modul Pricing & Ofertare — strategie de implementare

**Data:** 2026-07-05 · **Status:** DRAFT — așteaptă răspunsurile ownerului la întrebările din §7
**Obiectiv:** un modul complet de la preț de achiziție → landing cost → simulare marjă → ofertă de preț cu poze → fișiere de listare (xls) per client, gândit din perspectiva directorului comercial.

---

## 1. Viziune (perspectiva directorului comercial)

Fluxul de decizie comercială pe care modulul trebuie să-l acopere cap-coadă:

```
Preț furnizor (valută, EXW/FOB/CIF)
   └─> Landing cost RON (transport, taxe vamale, alte costuri)
        └─> Preț de bază (marjă țintă pe gamă)
             └─> Preț facturare per client (condiții comerciale: off-invoice %, bonusuri)
                  └─> Marjă netă reală per client / per SKU  ← decizia se ia AICI
                       ├─> Formular modificare preț (per format client)
                       ├─> Ofertă de preț cu poze (client nou sau extindere gamă)
                       └─> Fișier de listare xls (per template client)
```

Regula de aur (confirmată de owner pe alte module): **nimic hardcodat** — clienți, formate, condiții, cursuri = toate definite în date/UI.

## 2. Ce există deja în aplicație (nu construim de la zero)

| Componentă | Stare | Observații |
|---|---|---|
| `produse` (1.324 SKU) | ✅ | are furnizor, brand, gramaj, buc_cutie, EAN, TVA, HS code, taxă vamală, origine — dar **fără** dimensiuni, CBM, kg, bax/palet, poze |
| `costuri_landing` (965 rânduri) | ✅ | preț achiziție valută + curs + transport% + taxă vamală% + alte costuri → landing RON; transportul e **% fix** (default 10%) |
| `preturi_vanzare` (944) | ✅ | preț per an/SKU/client |
| `conditii_comerciale` / `cond_resolved` | ✅ schemă | condițiile detaliate au 0 rânduri; `cond_resolved` (5.643) are % efectiv per client×furnizor — folosit la marja ajustată |
| UI `/preturi`, `/preturi/<sku>`, `/conditii` | ✅ | catalog cu filtre (sub marjă, fără preț), editare landing + preț vânzare per client |
| `rate_schimb` | ✅ | curs per an/monedă |
| `comenzi_furnizori_linii` | ✅ | are deja units_per_carton, gross_kg, net_kg, CBM per linie de comandă — sursa reală de costuri logistice |
| Export xlsx/pptx (`app/exports/`) | ✅ | infrastructură de generare fișiere există |
| Poze articole | ❌ | nu există nicăieri în app |

**Concluzie:** modulul nou = extinderea pipeline-ului existent, nu un modul paralel. Evităm dublarea datelor.

## 3. Ce aduc fișierele de start (`Date pricinng&Logistica&Ofertare/`)

| Fișier | Rol în modul |
|---|---|
| `FISIER_CONSOLIDAT_PRETURI.xlsx` | **sursa de adevăr actuală** (Excel-ul pe care îl înlocuim): preț achiziție + taxe + transport + curs per gamă → preț bază 30% marjă → preț facturare per client (Auchan, Metro…) + coduri interne client + sheet CONDIȚII (% per client) + sheet Cursuri (curs fix per gamă) |
| `RO1-010/011-26.xls` (Basilur order form) | **master logistic complet**: greutate unitate, dimensiuni MC, CBM, kg brut/net, buc/bax, incoterms, porturi, termene de plată — de importat în master-ul de produse |
| `ORDER TORRAS / ipek / Delaviuda` | prețuri EXW reale + buc/bax + bax/palet per furnizor — confirmă că fiecare furnizor are format propriu de comandă |
| `Model_propunere_creare_articol_.xlsx` | fluxul „definire articol nou" (stil Auchan): EAN, cod furnizor, HS, ingrediente, alergeni, nutriție, dimensiuni — baza modulului de creare articol |
| `formular modificare preturi Kaufland / Selgros / Copy of formular…` | **formate de ieșire** per client pentru modificări de preț (coloane diferite per client: cod client, preț vechi/nou, valabil de la) |
| `lista pret Fildas × 4 / Sezamo × 5` | **formate de listare** per client×brand — structuri simple dar diferite (Fildas: cod furnizor+gramaj; Sezamo: cod produs client) |
| `stoc torras.xls`, `vz-hun-trade…` | context stoc/vânzări export — nu intră în faza 1 |

## 4. Arhitectura propusă

### 4.1 Model de date (migrări noi)

- **`produse_logistica`** (1:1 cu `produse`): dimensiuni unitate (L/W/H mm), net/gross kg, buc_bax, bax_palet (straturi × bax/strat), dimensiuni bax, CBM bax, termen valabilitate, min. comandă. Sursă: import din order forms furnizor + editare UI.
- **`produse_media`**: sku → poză (path local `app/static/product_images/` + URL sursă), tip (principală/ambalaj), upload manual sau fetch de pe site.
- **`coduri_client_articol`**: sku × client → cod intern client (Metro 223988, Kaufland 133482, Sezamo 23041…). Există parțial în FISIER_CONSOLIDAT sheet „CODURI INTERNE CLIENTI". Fără asta nu putem genera nici formulare, nici listări.
- **`costuri_landing` v2** (extindere): moduri de calcul transport — `pct` (actual), `per_kg`, `per_cbm`, `absorbit din comandă` (alocă costul real de transport al unei comenzi pe linii, proporțional cu CBM/kg/valoare). Istoricizare: `valabil_de_la` în loc de doar `an`.
- **`oferte`** + **`oferte_linii`**: ofertă per client (draft → trimisă → acceptată), linii cu SKU, preț propus, marjă calculată la momentul ofertei, poze incluse.
- **`liste_pret`** + **`liste_pret_linii`**: listă de preț activă per client cu `valabil_de_la` — istoricul modificărilor de preț per client (azi trăiește doar în emailuri/xls).
- **`client_export_template`**: client → template de fișier (kaufland_modificare, sezamo_lista, fildas_lista, selgros_modificare, generic) + mapare coloane, ca formatele noi de client să se adauge din UI, nu din cod.

### 4.2 Motor de cost & marjă (`app/pricing_engine.py` — pur, testabil)

- `landing_cost(sku, an|data)` — achiziție×curs + transport (per mod) + taxă vamală + alte costuri.
- `pret_baza(sku, marja_tinta)` — marjă = (preț − landing)/preț (așa e în FISIER_CONSOLIDAT: 48,3 → 69 la 30%).
- `marja_client(sku, client, pret)` — scade condițiile efective (`cond_resolved` / condiții detaliate) → **marjă netă**; opțional până la preț raft (marja retailer + TVA), ca în sheet „simulare metro".
- `simulare(sku_list, client, pret_nou)` — waterfall: landing → facturare → condiții → marjă netă; diferență vs. preț actual.

### 4.3 UI (extinderea `/preturi`)

1. **Catalog** (există) + coloane logistice + poză thumbnail + filtre existente.
2. **Simulator de preț** (nou): selectezi client + articole → propui preț (sau % creștere, sau marjă țintă) → vezi live marja netă per articol, semafor sub/peste prag → salvezi ca propunere.
3. **Oferte** (nou): din simulare → generezi ofertă cu poze (xlsx cu imagini embedded prin openpyxl; opțional PDF) → istoric oferte per client.
4. **Listări** (nou): client nou (toată gama sau selecție) sau client vechi (modificare preț: vechi vs. nou, valabil de la) → xls în formatul clientului.
5. **Definire articol** (nou): formular cu câmpurile din Model_propunere (master + logistic + poze) → articolul intră în catalog; export „fișă creare articol" per client.

### 4.4 Import (o singură dată + recurent)

- **One-off:** FISIER_CONSOLIDAT (prețuri, coduri client, condiții, cursuri) + RO1-0xx (logistică Basilur) → scripturi ETL în `etl/`, cu raport de nepotriviri SKU (folosind `queries/_shared.py:resolve_catalog_sku`).
- **Recurent:** upload listă preț furnizor → diff prețuri achiziție vechi/noi → confirmare → actualizare landing + alertă articole a căror marjă scade sub prag.

## 5. Faze de implementare

| Fază | Livrabil | Estimare |
|---|---|---|
| **F0 — Fundație date** | migrări (produse_logistica, media, coduri_client, landing v2), import FISIER_CONSOLIDAT + RO1-0xx, raport calitate date | prima |
| **F1 — Motor cost/marjă** | pricing_engine + teste, landing v2 în UI /preturi, marjă netă per client corectă | după F0 |
| **F2 — Simulator** | tab Simulator, salvare propuneri, semafor marjă | după F1 |
| **F3 — Ofertare + listare** | generare xls oferte cu poze, formulare modificare preț + liste per template client (Kaufland, Sezamo, Fildas, Selgros primele) | după F2 |
| **F4 — Definire articol** | formular creare articol + poze (upload/URL), export fișă articol | paralel cu F3 |
| **F5 — Import recurent** | upload liste furnizor cu diff & confirmare | ultima |

Fiecare fază: dezvoltare pe `main` local → teste → push → Dev :5001 → evaluare owner → aprobare prod. Fișierele Excel cu date comerciale rămân **în afara git-ului** (adăugat la `.gitignore`).

## 6. Riscuri / decizii tehnice

- **Potrivirea SKU** între sistemul Torb, codurile furnizor și codurile client e cel mai mare risc de date (deja vizibil: FISIER_CONSOLIDAT are coloane „DENUMIRE SISTEM TORB" goale). F0 include raport explicit de nepotriviri.
- **Poze în xlsx**: openpyxl suportă imagini embedded; dimensiunea fișierului crește — thumbnail-uri max ~200px în oferte.
- **`an` vs. `valabil_de_la`**: modelul actual e per an calendaristic; prețurile reale se schimbă în cursul anului (15.06, 01.07 în fișiere). Propun migrare graduală la valabilitate pe dată, cu compatibilitate pe an.

## 7. Întrebări deschise (răspunsurile ownerului) — BLOCANTE pentru F0/F1

1. **Transport în landing cost:** rămânem la % din valoare (azi 10% default, în fișier 0 la Basilur) sau alocăm costul real de transport per comandă pe CBM/kg? Care e regula pe care o folosiți azi în practică, per furnizor?
2. **Curs valutar:** curs fix „de calcul" per gamă (USD 4,6 / EUR 5,4 ca în fișier) actualizat manual, sau curs BNR + marjă de siguranță? Cine îl schimbă și când?
3. **Marja de bază 30%:** e aceeași pentru toate gamele sau diferă (Basilur vs. Torras vs. Celmar)? Există praguri minime sub care echipa nu are voie să coboare fără aprobarea ta?
4. **Condiții client:** ne ajunge un % total per client (ca în sheet CONDIȚII: Auchan 11,72%) sau vrei defalcat pe tipuri (bonus logistic, marketing, promo, listare) ca să vezi unde se duce marja? Tabelul detaliat există deja în app, dar e gol.
5. **Preț raft:** vrei ca simulatorul să meargă până la preț raft estimat (marja retailerului + TVA, ca în „simulare metro")? De unde luăm marja de raft per client — o introduci tu per client/categorie?
6. **Poze:** de pe ce site se iau pozele (robrands.ro? site-urile furnizorilor?) și există o regulă de potrivire (EAN/SKU în URL), sau se încarcă manual la definirea articolului?
7. **Clienți prioritari pentru template-uri:** confirmi ordinea Kaufland, Sezamo, Fildas, Selgros, Auchan? Formatul trebuie 1:1 cu fișierele existente (le atașează echipa direct în portalurile clienților)?
8. **Cine folosește modulul:** câți oameni din echipă generează oferte? Vrei flux de aprobare (echipa propune → directorul aprobă → abia apoi se generează fișierul de listare)?
9. **Valabilitate & istoric:** confirmi trecerea la `valabil_de_la` (dată) în locul prețului „per an"? Păstrăm istoricul complet al listelor trimise per client?
10. **Sursa prețului de achiziție:** lista de preț oficială a furnizorului sau prețul din ultima comandă efectivă (`comenzi_furnizori_linii` le are pe ambele potențial diferite)? Ce facem când diferă?
11. **Export (HU/BG…):** modulul de pricing acoperă și clienții export (HunTrade etc., prețuri în EUR?) din prima, sau întâi RO și extindem după?
12. **Alte costuri în marjă:** vrei incluse în „marja netă" și costuri operaționale (depozitare, retur, transport la client, termen de plată/cost finanțare — există `termene_plata`), sau doar condițiile comerciale?

---
*Documentul se actualizează cu răspunsurile + deciziile finale înainte de începerea F0.*
