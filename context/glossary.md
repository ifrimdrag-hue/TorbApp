# Torb Logistic — Shared Vocabulary & Concept Map

---

## 1. Business Flow

How value moves through the business:

```
  [Sri Lanka / EU]          [Torb Logistic]           [Romanian Market]
  ─────────────────         ───────────────           ─────────────────

  Basilur Tea Export  ──►   Import &          ──►   IKA          (Kaufland, Carrefour,
  (Sri Lanka)               Warehousing             (Key Accounts) Mega Image, Auchan)
                            Chiajna, Ilfov
  Toras               ──►                    ──►   Cash & Carry  (Selgros, Metro)
  Leonex              ──►   Sales Team
  Celmar              ──►   (5 roles)         ──►   Pharma        (Dr. Max, Farmacia Tei,
  KingSLeaf           ──►                                          Fildas)
  Delaviuda           ──►                    ──►   Online        (basilurtea.ro / eMAG)
  Solvex              ──►                    ──►   Distribuitor  (resellers)
  Tipson              ──►                    ──►   TT            (traditional trade)
  ...                                        ──►   HoReCa        (underdeveloped)
                                             ──►   Export        (Hungary)

  NOTE: "Furnizor" in the data = Brand (Basilur, Toras, etc.)
        NOT the external vendor in Sri Lanka
```

---

## 2. Team Structure

```
         [Owner]
            │
            │ reports to
            ▼
  ┌─────────────────────────┐
  │   Sales Team (5 roles)  │
  └─────────────────────────┘
            │
     ┌──────┴──────────────────────┐
     │                             │
     ▼                             ▼
  MGR_PHTT_01                 KAM_IKA_01         KAM_MIX_01
  Manager                     Key Account        Key Account
  Pharma + TT                 Manager IKA        Manager IKA + TT
     │                        (pure KA)          (mixed role)
     ├──► AG_TT_01
     │    Agent TT 1          Manages:           Manages:
     │                        Kaufland           IKA accounts
     └──► AG_TT_02            Carrefour          + some TT
          Agent TT 2          Mega Image
                              Auchan
  Manages:                    Profi
  Pharma accounts
  + TT clients

  Real names (from sales data, 2025 share):
  ┌─────────────────────────────────────────────┐
  │ DRAGNEA BOGDAN    55.6%  (likely KAM_IKA)   │  ← KEY PERSON RISK
  │ OANA FILIP        15.3%                     │
  │ BRINZA CLAUDIU    14.9%                     │
  │ BOTEA DANIEL       6.3%                     │
  │ CONSTANTIN IONUT   4.0%                     │
  │ GURAMULTA GHEORGHE 2.8%                     │
  └─────────────────────────────────────────────┘
```

---

## 3. Data Model (SQLite — torb.db)

```
  ┌──────────────────────────────────────────────────────────────┐
  │                        tranzactii                            │
  │  (131,898 rows — one row per SKU line per delivery note)     │
  │                                                              │
  │  TIME         luna, an, data_dl                             │
  │  DOCUMENT     nr_dl, nr_factura, nr_comanda                 │
  │  PRODUCT      cod_produs, sku, furnizor (=brand), um        │
  │  QUANTITY     cantitate                                      │
  │  FINANCIALS   val_neta, val_bruta, val_achizitie,           │
  │               marja_bruta, val_usd, discount_pct            │
  │  CLIENT       client, cod_client, tip_client,               │
  │               oras_client, judet_client                     │
  │  AGENT        agent  (sales rep OR channel)                 │
  └──────────────┬───────────────────┬──────────────────────────┘
                 │                   │
       agent ◄───┘                   └───► client
         │                                   │
         ▼                                   ▼
  ┌─────────────┐                   (no separate table yet —
  │   echipa    │                    client data is embedded
  │  (5 rows)   │                    in tranzactii)
  │             │
  │ employee_id │
  │ rol         │◄────────────────────────────────────┐
  │ activ       │                                     │
  │ bonus_target│                                     │
  └──────┬──────┘                                     │
         │                                            │
         ▼                                            │
  ┌─────────────────────┐    ┌─────────────────────┐  │
  │   targeturi_kpi     │    │    actuale_kpi       │  │
  │   (60 rows)         │    │    (60 rows)         │  │
  │                     │    │                     │  │
  │ an, luna,           │    │ an, luna,           │  │
  │ employee_id ────────┼────┼─► employee_id ──────┘  │
  │ net_sales (target)  │    │ net_sales (actual)      │
  │ gross_margin        │    │ gross_margin            │
  │ active_clients      │    │ active_clients          │
  │ collections         │    │ collections             │
  │ ...                 │    │ penalizare_erori_pct    │
  └─────────────────────┘    └─────────────────────────┘

  ┌──────────────────────────────────────────┐
  │         targeturi_cantitativ             │
  │         (20,919 rows)                    │
  │                                          │
  │  agent   ──────────────────► sales rep   │
  │  client  ──────────────────► buyer       │
  │  sku     ──────────────────► product     │
  │  an, luna                                │
  │  cantitate  (units planned/sold)         │
  │                                          │
  │  2024: historical actuals                │
  │  2025: historical actuals                │
  │  2026: targets (⚠ mostly zero, not set)  │
  └──────────────────────────────────────────┘
```

---

## 4. Transaction Anatomy

What a single row in `tranzactii` represents:

```
  One delivery (nr_dl) can have many invoice lines:

  DL: 301225024  (delivery note, date: 2025-12-31)
  Factura: TORB25121178
  Agent: EMAG
  Client: 3NYBLE TECHNOLOGIES SRL
  │
  ├── Line 1:  cod_produs=1561
  │            sku="B.CEAI FRUIT INFUSIONS ASSORTED 40E 72G"
  │            furnizor=Basilur
  │            cantitate=3, pret_vanzare=29.35
  │            val_neta=88.05, val_achizitie=31.46
  │            marja_bruta=56.59  (64% margin)
  │
  └── Line 2:  cod_produs=1236
               sku="B.CEAI STRAWBERRY & RASPBERRY 25X1.8G"
               furnizor=Basilur
               cantitate=1, pret_vanzare=20.18
               val_neta=20.18, val_achizitie=2.18
               marja_bruta=18.00  (89% margin)
```

---

## 5. Bonus Calculation Flow

```
  Each month, per employee:

  tranzactii  ──────────────────────────────────────────────►  actuale_kpi
  (actual sales)     compute:                                  (filled in)
                     - Net Sales (val_neta sum)
                     - Gross Margin (marja_bruta sum)
                     - Active Clients (COUNT DISTINCT client)
                     - Collections (manual input)
                     - Promo Exec (manual input)
                     - Forecast (manual input)

  targeturi_kpi ───────────────────────────────────────────►  scor per KPI
  (monthly targets)  formula:                                  = actual / target
                     each KPI weighted by rol (02_Rol_KPI)

                     Scor final = Σ (KPI_score × KPI_weight)

  Scor final  ─────────────────────────────────────────────►  payout
                     prag minim = 0.85  → below = 0 bonus
                     scor 1.0   → payout 1.0  (100% of target bonus)
                     scor 1.2   → payout 1.4  (140% — max)
                     + penalizari (manual deductions)

  payout × bonus_target_lunar_ron  ────────────────────────►  bonus lunar (RON)
  (from echipa)
```

---

## 6. Key Concepts — Quick Reference

| Term | Plain meaning | ⚠️ Gotcha |
|---|---|---|
| **Furnizor** | Brand (Basilur, Toras…) | NOT the Sri Lanka vendor |
| **Agent** | Sales rep or channel | Includes EMAG, SITE (not human) |
| **Client** | Torb's customer (retailer) | NOT the end consumer |
| **Baza** | Raw transaction data | Excel sheet name; = `tranzactii` in DB |
| **Gama** | Product line within a brand | Not in DB yet — embedded in SKU name |
| **IKA** | Large retail chains | = Key Accounts = Modern Trade |
| **TT** | Traditional trade | Small shops, visited by field agents |
| **Val Neta** | Net revenue | Primary revenue figure |
| **Marja Bruta** | Gross margin RON | val_neta − val_achizitie |
| **Scor** | Bonus performance score | Weighted avg of KPI achievements |
| **Cantitativ** | Unit-quantity target | vs. value target (RON) |
| **Phasing** | Monthly split of annual target | Oct–Dec = peak (gifting season) |
| **YTD** | Year to date cumulative | |
| **DL** | Delivery note | Groups all SKU lines in one shipment |
