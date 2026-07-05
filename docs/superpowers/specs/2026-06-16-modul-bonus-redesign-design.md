# Modul Bonus — Redesign (obiective lunare configurabile)

**Data:** 2026-06-16
**Status:** Design aprobat, gata pentru plan de implementare

## Context și problemă

Modulul de bonus actual (`/bonus`) funcționează pe `PRESETS` hardcodate în `app/bonus_calc.py`:
5 agenți cu ponderi, praguri și creștere fixate în cod. Calculul folosește 3 criterii fixe
(vânzări, marjă, branduri strategice ca un singur criteriu compozit) și o grilă de payout cu praguri.

Directorul comercial vrea un **instrument de motivare flexibil**: la începutul fiecărei luni să
seteze pentru fiecare agent obiective configurabile (nu doar valoare), cu ponderi și valoare de
bonus proprii, salvate în baza de date.

**Descoperire importantă:** există deja o schemă DB dormantă (seed-uită pentru 2025, dar
neconectată la UI) care se potrivește aproape exact pe cerință:
`bonus_config`, `bonus_lunar_config`, `bonus_obiective_strategice` (tabel **generic** cu
`tip`/`referinta`/`target_valoare`/`pondere`), `bonus_payout_grid`, `bonus_istoric`.
Redesign-ul **reutilizează și extinde** această schemă, nu reinventează.

Un al doilea model paralel gol (`echipa`, `targeturi_kpi`, `actuale_kpi` cu coloane fixe) **nu se
folosește** și rămâne neatins (poate fi curățat ulterior, în afara scope-ului).

## Obiective (ce trebuie să facă)

1. La început de lună, directorul setează obiective per agent și le salvează.
2. Pe lângă valoare (vânzări), criterii noi: **marjă, game individuale, nr. clienți activi,
   clienți noi/gamă, încasări, obiectiv scriptic**.
3. Director setează **valoarea bonusului lunar** și **ponderea fiecărui criteriu**.
4. Se păstrează default-ul de **creștere +20%** și comparativul permanent **vs anul trecut
   aceeași lună** (PY same-month auto-încărcat, target = PY × 1.20, editabil și salvabil).
5. Fiecare criteriu sub **80% realizat nu se comisionează** (inerent în grila de praguri).
6. Tracker-ul de echipă (`/team`) rămâne **neschimbat**.

## Non-obiective (explicit în afara scope-ului)

- Curățarea mapării SKU→categorie fină (join produse↔tranzacții acoperă doar ~0.7% din valoare).
  KPI-urile de gamă folosesc **doar cele 9 game din `tranzactii.furnizor`** (singurele cu realizat
  automat fiabil).
- Refactorizarea modelului paralel `targeturi_kpi`/`actuale_kpi`.
- Bonus pentru canalele online (eMAG/Site/Trendyol/Altex) — se pot adăuga ulterior din UI.

## Decizii de design (confirmate cu utilizatorul)

| Temă | Decizie |
|------|---------|
| Realizat pt. încasări & scriptic | **Flux lunar de închidere** cu blocare (`bonus_istoric`), audit trail, valori înghețate |
| Mecanică payout | **Grilă cu praguri** (existentă): <80%→0, 80%→0.5×, 95%→0.8×, 100%→1×, 110%→1.2×, 120%→1.5× |
| Selector gamă | **Cele 9 game** din `tranzactii.furnizor` (Basilur, Toras, Celmar, Leonex, Delaviuda, KingsLeaf, Solvex, Tipson, Cosmetice) |
| Roster agenți | Pornim cu 4 agenți de teren (Claudiu, Bogdan, Oana, Ionuț). **Teo eliminat complet.** Agenți gestionabili din UI, sincronizat cu `tranzactii.agent`, flag `activ` |
| Layout setare | **Varianta C**: card-uri stare agenți + formular per agent pe toată lățimea |
| Game pre-încărcate | **5 game strategice** la creare obiective: Basilur (30%), Toras (25%), Leonex (20%), Celmar (15%), Delaviuda (10%) |

## Arhitectură — pagini

Toate sub blueprint-ul `bonus` (`app/blueprints/bonus.py`):

| Rută | Rol |
|------|-----|
| `GET /bonus` | **Tracker** (rebuild). Realizare per agent, KPI cu gate 80%, bonus calculat din DB. Selector perioadă (an/lună). Comparativ vs PY. |
| `GET /bonus/obiective` | **Setare obiective** (varianta C). Card-uri stare + formular per agent. |
| `POST /bonus/obiective/save` | Salvează config lunar + rânduri KPI pentru un agent/lună. |
| `GET /bonus/inchidere` | **Închidere lună**: introducere încasări + scor scriptic + penalizare, review. |
| `POST /bonus/inchidere/lock` | Înghețare snapshot în `bonus_istoric`, `stare='inchis'`. |
| `GET /bonus/config` | **Agenți**: adăugare/dezactivare agenți, config bază, payout grid. |
| `GET /bonus/clienti-noi-gama` | Drill-down: lista clienților noi pe gamă (params: agent, gama, an, luna). |
| `GET /bonus/simulator` | Păstrat, adaptat ușor la noul model config-driven. |
| `GET /bonus/export` | Păstrat, adaptat la noul model. |

## Modelul de KPI (rânduri individuale, plate)

Fiecare obiectiv e un rând în `bonus_obiective_strategice` (redenumit conceptual "obiective KPI").
Structură per rând: `tip`, `referinta`, `target_valoare`, `target_unitate`, `pondere`,
`bonus_per_unit` (păstrat dar nefolosit în modelul cu grilă).

| `tip` | Realizat | Target default | Pre-încărcat |
|-------|----------|----------------|--------------|
| `vanzari` | auto din `tranzactii` (val_neta, luna CY) | PY same-month × 1.20 | da (1 rând) |
| `marja` | auto (marja_bruta) | PY same-month × 1.20 | da (1 rând) |
| `brand` | auto (val_neta filtrat pe `furnizor`=referinta) | PY same-month × 1.20 | **da — 5 game** |
| `clienti` | auto (COUNT DISTINCT cod_client în lună) | PY same-month × 1.20 | opțional |
| `clienti_noi_gama` | auto (query 24 luni, vezi mai jos) + **link drill-down** | PY same-month × 1.20, editabil | opțional, per gamă |
| `incasari` | **manual** la închidere | manual (fără PY) | opțional |
| `scriptic` | **manual** % la închidere | text liber, scor 0-100% | opțional |

- Ponderile însumează 100% (validare vizuală; ≠100% → avertisment, salvarea permisă).
- Butoane "+ Gamă / + Clienți noi gamă / + Scriptic" adaugă rânduri în formular.

### KPI `clienti_noi_gama` — definiție și query

Client "nou pe gamă" = client care **nu a fost facturat cu gama respectivă de niciun agent în
ultimele 24 de luni** înainte de luna țintă, dar a fost facturat cu acea gamă în luna țintă.
Creditul merge la agentul care l-a facturat în luna curentă.

```sql
WITH luna_clienti AS (
  SELECT DISTINCT cod_client, client
  FROM tranzactii
  WHERE furnizor = :gama AND LOWER(agent) = LOWER(:agent)
    AND an = :an AND luna = :luna
)
SELECT lc.cod_client, lc.client
FROM luna_clienti lc
WHERE NOT EXISTS (
  SELECT 1 FROM tranzactii t2
  WHERE t2.cod_client = lc.cod_client
    AND t2.furnizor = :gama
    AND t2.data_dl >= date(:month_start, '-24 months')
    AND t2.data_dl <  :month_start
)
```
`:month_start` = prima zi a lunii țintă. Realizat = `COUNT(*)`; link-ul drill-down afișează
`SELECT cod_client, client` cu același filtru.

**Avertisment de date (de afișat în UI):** baza ține 2024-01 → prezent (~2.5 ani). Lookback-ul de
24 luni e complet doar pentru lunile din 2026 încolo. Pentru brandurile foarte stabilite metricul
e adesea 0 (clienții au istoric anterior); devine mai relevant cu cât trece timpul și pe game noi.
Validat: query rapid (~21ms), produce numere mici dar reale pe agenți de teren (ex. martie 2026:
Claudiu +1 Basilur, Ionuț +3 Toras, +2 Tipson).

## Calcul bonus (păstrat, devine config-driven)

```
multiplicator_i = payout_grid(realizare_i)          # realizare_i = actual_i / target_i
bonus = bonus_lunar × Σ_i (pondere_i × multiplicator_i) × (1 - penalty)
```

- Grila de praguri rămâne cea existentă din `bonus_payout_grid` (per agent, cu fallback `_default`).
- Gate 80% per criteriu = inerent: sub 80% realizare → multiplicator 0 → 0 lei pe acel KPI.
- `penalty` (penalizare) = opțional, introdus la închidere.
- `bonus_calc.py` se refactorizează: `calc_month`/`simulate` iterează **rânduri KPI generice**
  (listă de dict-uri cu `tip`, `target`, `actual`, `pondere`) în loc de cele 3 criterii hardcodate.

## Model de date (DB)

Reutilizare schemă existentă + migrație nouă pentru coloane lipsă:

- **`bonus_config`** — `agent_key, db_agent, tip_agent, growth_pct, activ`. Ponderile/gate-urile
  globale devin redundante (mutate pe rânduri KPI); rămân pentru compatibilitate/fallback.
  Acțiune seed: șterge Teo; păstrează cei 4 agenți de teren.
- **`bonus_lunar_config`** — per `(an, luna, agent_key)`: `monthly_bonus`, `growth_pct`
  (override opțional). Pondere globală mutată pe rânduri.
- **`bonus_obiective_strategice`** — rândurile KPI. Extindere `tip` la enum-ul de mai sus.
  Coloană nouă (migrație): `realizat_manual REAL` pentru target manual/valori scriptice dacă e
  nevoie în afara `bonus_istoric`. La creare obiective pentru o lună nouă, dacă nu există rânduri,
  se pre-încarcă: vânzări, marjă, 5 game strategice (cu PY auto + target ×1.20).
- **`bonus_payout_grid`** — neschimbat (per agent + `_default`).
- **`bonus_istoric`** — închidere lună: `lunar_data` (JSON snapshot înghețat al tuturor KPI +
  bonus calculat + actualele manuale), `penalty_pct`, `grad_incasare`, `stare`
  (`deschis`/`inchis`), `inchis_la`, `note`. O linie per `(an, luna, agent_key)`.

**Citire tracker:** dacă luna e `inchis` → citește snapshot înghețat din `bonus_istoric`; altfel
calculează live (KPI auto din `tranzactii`, KPI manuale = pending/0).

## Componente (separare responsabilități)

- `app/bonus_calc.py` — logică pură de calcul (grilă, multiplicatori, agregare KPI). Refactorizat
  config-driven. Testabil izolat (input: params + listă KPI → output: bonus).
- `app/queries/bonus.py` — toate query-urile DB (config, obiective, realizat auto per tip,
  clienți noi/gamă, citire/scriere istoric). Extins semnificativ.
- `app/blueprints/bonus.py` — rute + orchestrare (citește config + actuals → calc → render).
- `app/templates/bonus.html` — tracker (rebuild).
- `app/templates/bonus/obiective.html` — setare (varianta C).
- `app/templates/bonus/inchidere.html` — închidere lună.
- `app/templates/bonus/config.html` — agenți.
- `app/templates/bonus/clienti_noi_gama.html` — drill-down.
- `migrations/000X_*.py` — coloane noi + seed (elimină Teo).

## Testare

- **Unit (`bonus_calc`):** grila de praguri (granițe 79.9/80/95/100/110/120%), gate sub 80%→0,
  agregare ponderată, penalty, ponderi care nu însumează 100%.
- **Query (`queries/bonus`):** `clienti_noi_gama` (verificat 21ms; cazuri: client nou, client cu
  istoric în fereastră, fereastră incompletă la marginea datelor), PY same-month, realizat auto
  per tip pe DB de test.
- **Integration (rute):** salvare obiective → reload → valori persistate; închidere lună →
  snapshot înghețat → tracker citește din istoric; agent dezactivat dispare din tracker.
- **Manual/smoke:** flux complet pe un agent (setare → realizat → închidere → export).

## Riscuri / atenționări

- **Adâncimea datelor** limitează `clienti_noi_gama` (vezi mai sus) — UI afișează avertisment.
- **Migrarea de la PRESETS la DB:** valorile actuale din `bonus_config`/`bonus_lunar_config`
  (seed 2025) trebuie verificate să corespundă cu `PRESETS` înainte de a tăia codul hardcodat.
- **Compatibilitate retroactivă:** lunile 2025 deja afișate în tracker trebuie să dea aceleași
  cifre după rebuild (test de regresie pe o lună cunoscută).
- Regula de encoding românesc pentru fișiere `.py` (vezi `.claude/project_knowledge.md`).
