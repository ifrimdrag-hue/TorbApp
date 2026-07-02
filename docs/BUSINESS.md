# Torb Logistic — Business, Company & Strategy

Single consolidated reference for everything business-side: key facts, company profile, market research, risks, AI opportunities, and the full 5-year strategic plan. Consolidated 2026-07-02 from `context/` (torb_background, project_business_overview, key_facts, project_key_risks, project_ai_opportunities, ai_optimization_report_1, glossary business sections, plan_strategic_5ani).

---

## Key facts (quick reference — do not re-derive from scratch)

- Torb distributes **12 brands** (not just Basilur). Main ones: Basilur 31%, Toras 22%, Leonex 20%, Celmar 13%.
- **Celmar and Leonex are Torb's own brands** (mărci proprii) — together ~38% of 2025 revenue. Torb is a hybrid brand house + distributor, not a pure distributor.
- 2025 total revenue: ~15M RON across 3,297 clients.
- Biggest risk: Bogdan Dragnea = 55.6% of all sales. Kaufland = 41.4% of revenue.
- The reporting dashboards were well-designed templates but **contained no data** — the core gap was a missing data pipeline from raw transactions to management reports (now addressed by the Flask webapp).
- Seasonality: peak months Oct > Nov > Dec (gifting season); Apr–Jun are base months.

---

## 1. Business overview (from actual sales data)

Torb Logistic SRL is a Romanian FMCG distributor, NOT just a Basilur Tea importer. They distribute 12 brands.

**Why this matters:** The background research (§4 below) describes them as exclusive Basilur distributor, but the actual sales files reveal a multi-brand portfolio. Always reference the actual brand mix when discussing strategy. Do not treat Torb as a tea-only company.

### Brand portfolio (2025 actuals from vanzari_01.03.2026.xlsx)

| Brand | 2025 Sales (RON) | Share | Tip |
|---|---|---|---|
| Basilur | 4,474,030 | 31% | Distribuit (exclusivitate) |
| Toras | 3,005,276 | 22% | Distribuit |
| **Leonex** | **2,964,326** | **20%** | **MARCĂ PROPRIE TORB** |
| **Celmar** | **2,691,367** | **13%** | **MARCĂ PROPRIE TORB** |
| KingSLeaf | 658,692 | 5% | Distribuit |
| Delaviuda | 634,583 | 5% | Distribuit |
| Solvex | 413,185 | 2% | Distribuit |
| Tipson | 93,332 | 1% | Distribuit |
| Others (Cosmetice, Colian, Foite) | ~94k | <1% | Distribuit |

**Total 2025: ~15,029,290 RON** | **Total 2026 YTD (Jan-Feb): 2,852,669 RON**
**Share mărci proprii (Celmar + Leonex): 5,655,693 RON = ~38% din CA 2025**

Note: KingsLeaf, Tipson, and Organsia are virtual sub-brands of Basilur, split at import time — see `docs/BUSINESS_LOGIC.md` §Virtual brands.

### Sales channels

- KA (Key Accounts / IKA): Kaufland, Carrefour, Mega Image, Auchan, Profi
- TT (Traditional Trade): smaller clients, managed by field agents
- Pharma: Dr. Max, Farmacia Tei, Fildas Trading
- Cash & Carry: Selgros, Metro
- Online: basilurtea.ro (SITE), eMAG
- Export: HUN-TRADE KFT (Hungary), BRANDMIX KFT

### Sales team (5 active roles)

- MGR_PHTT_01: Manager Vanzari Pharma + TT (2 TT agents in subordine)
- KAM_IKA_01: Key Account Manager IKA
- KAM_MIX_01: Key Account Manager IKA + TT
- AG_TT_01: Agent Vanzari TT 1
- AG_TT_02: Agent Vanzari TT 2

### Real names from sales data (2025)

- DRAGNEA BOGDAN: 8,351,770 RON — 55.6% of total sales
- OANA FILIP: 2,301,410 RON — 15.3%
- BRINZA CLAUDIU: 2,245,530 RON — 14.9%
- BOTEA DANIEL: 945,523 RON — 6.3%
- CONSTANTIN IONUT: 597,502 RON — 4.0%
- GURAMULTA GHEORGHE: 419,556 RON — 2.8%
- SITE (online): 85,463 RON — 0.6%
- EMAG: 82,232 RON — 0.5%

### Top clients (2025)

1. KAUFLAND ROMANIA SCS: 6,226,454 RON — **41.4% of total**
2. CARREFOUR ROMANIA SA: 903,240 RON — 6.0%
3. TOBRA INVEST SRL: 826,479 RON — 5.5%
4. SELGROS CASH & CARRY SRL: 706,385 RON — 4.7%
5. BEBETEI INVESTMENTS GROUP SRL: 606,852 RON — 4.0%
6. FARMACIA TEI SRL: 463,503 RON — 3.1%
7. FILDAS TRADING SRL: 455,269 RON — 3.0%
8. DR.MAX SRL: 367,251 RON — 2.4%

**Total unique clients: 3,297**

---

## 2. Business flow & team structure

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

Team structure:

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

## 3. Key risks & data gaps

Critical business risks and operational gaps identified from analyzing the actual data files — not from the background research.

### Risk 1: Agent concentration — CRITICAL
Bogdan Dragnea = 55.6% of all 2025 revenue (8.35M RON out of 15M RON).
**Why:** Identified from sales agent breakdown in vanzari_01.03.2026.xlsx.
**How to apply:** Any AI workflow involving sales must treat Bogdan's pipeline as a special case. His absence or departure would be existential. Flag this whenever discussing sales automation or team planning.

### Risk 2: Client concentration — CRITICAL
Kaufland = 41.4% of 2025 revenue. Top 5 clients = ~65% of revenue.
**Why:** Single retailer delisting could destroy the business.
**How to apply:** Recommend monitoring Kaufland order trends closely. Any demand forecasting must model Kaufland separately.

### Risk 3: Data pipeline gap — IMMEDIATE OPERATIONAL ISSUE (largely addressed)
The managerial dashboard (TORB_Dashboard_Managerial_FMCG.xlsx) had a well-designed template but ALL cells were empty (zeros/nulls). The bonus centralization sheet (06_Centralizare in bonusare_torb_structura_echipa.xlsx) was also empty.
**Why:** Transaction data existed in the Baza sheets but was not piped to dashboards automatically. Someone either updated these manually (slowly) or not at all.
**How to apply:** The #1 AI quick win was connecting the Baza data to these templates via an automated script — this was the foundation for everything else, and is now delivered as the Flask webapp (dashboard + automated bonus module).

### Risk 4: Multi-brand management complexity
12 brands with different margins, clients, and channels. Without automated tracking, margin dilution on lower-margin brands (Toras, Leonex) may go unnoticed vs. premium Basilur.

### Existential-risk summary (from the 2026-04-13 AI optimization report)

| Risc | Magnitudine | Consecință |
|---|---|---|
| Bogdan Dragnea pleacă | 55.6% din revenue = 8.35M RON | Business în pericol |
| Kaufland delistează | 41.4% din revenue = 6.2M RON | Business în pericol |
| Niciun dashboard activ | Management orb în timp real | Decizii tardive |

---

## 4. Company background research (April 2026)

> Notă: cercetare de birou din surse publice. **Incompletă pe portofoliul de branduri** — descrie Torb ca importator exclusiv Basilur, dar datele reale de vânzări arată un portofoliu multi-brand (vezi §1). Surse: basilurtea.ro, eMAG.ro, Termene.ro, RisCo.ro, EMIS, Ziar Financiar, Revista Progresiv, Euromonitor, erp-distribnet.ro, juniorsoft.ro, agriculturaecologica.ro.

### 4.1 Basilur Tea — profil companie (global)

| Câmp | Detalii |
|------|---------|
| **Nume legal** | Basilur Tea Export Pvt Ltd |
| **Fondată** | 2006, Sri Lanka |
| **Fondator** | Dr. Gamini Abeywickrama |
| **Director Creativ** | Andrey Mareev |
| **Sediu producție** | 143/6, Weediyabandara Mawatha, Kelanimulla, Angoda, Sri Lanka |
| **Suprafața fabricii** | ~6 acri, Kelaniya, Sri Lanka |
| **Prezență globală** | 44+ țări |
| **Website** | basilurtea.com |
| **Contact** | info@basilurtea.com / +94 11 2 549 500 |

Portofoliu de branduri (grup Basilur):

| Brand | Poziționare | Note |
|-------|-------------|------|
| **Basilur Tea** | Premium Ceylon, gifting, colecții | Brand flagship, iconic Tea Book/Tea Island |
| **Tipson Tea** | Wellness, organic, ayurvedic | Fără microplastic, compostabil |
| **Vazar Tea** | Segment de masă | Prezență limitată în România |

Produse & gamă: ceai negru Ceylon (pur și aromatizat), ceai verde, ceai alb, Oolong, infuzii de fructe (Cold Brew, Magic Fruits etc.), ceaiuri organice wellness (Tipson), accesorii ceai. **Peste 150 de arome/variante** disponibile la nivel global.

Premii & recunoaștere: multiple **Great Taste Awards** (Guild of Fine Food, UK); „Most influential brand in China market" — Food and Wine Magazine; Asia Marketing Excellence Award — Regional Winner 2022.

### 4.2 Torb Logistic SRL — profil companie (România)

| Câmp | Detalii |
|------|---------|
| **Nume legal** | Torb Logistic SRL |
| **CUI** | 13123498 |
| **J** | J40/5750/2000 |
| **Înfiinţată** | 20 iunie 2000 (25 ani activitate) |
| **Sediu social** | Str. Matei Basarab 108, bl. 74, sc. A, et. 7, ap. 32, Sector 3, București |
| **Sediu secundar** | Str. Industriilor nr. 10, Chiajna, jud. Ilfov |
| **Telefon** | 021-326.35.38 |
| **Email** | shop@tobra.ro |
| **Website România** | basilurtea.ro |
| **CAEN principal** | 5229 — Alte activități anexe transporturilor |
| **CAEN secundare** | 4637 (comerț ridicata ceai/cafea/cacao), 4639, 4645 |
| **Angajați (2024)** | 12 |
| **Rol** | Importator & distribuitor exclusiv Basilur în România |

Date financiare:

| An | Cifră de afaceri (RON) | Profit net (RON) | Creștere CA |
|----|----------------------|-----------------|-------------|
| 2024 | 13.462.090 | 1.696.076 | +17,61% |
| 2023 | ~11.447.000* | ~1.756.000* | — |

*valori estimate pe baza creşterii raportate

Alte date financiare (2024): datorii totale ~4.050.016 RON (+102% față de 2023); total active +39,3%; marjă profit net în scădere cu 3,32%; risc insolvență **scăzut** (conform Termene.ro); facturi restante raportate: **niciuna**.

Certificări: **operator ecologic certificat** (RO-ECO-026) — emis de SRAC CERT SRL, pentru import, distribuție și depozitare de ceaiuri, ciocolată, pudră de cacao.

### 4.3 Distribuție & canale în România

Retail modern (hypermarketuri):

| Retailer | Tip | Note |
|----------|-----|------|
| Kaufland | Hypermarket | Confirmat oficial |
| Carrefour | Hypermarket | Confirmat (Summer Tea, White Tea etc.) |
| Mega Image | Supermarket | Confirmat oficial |
| Auchan | Hypermarket | Listat cu Torb Logistic ca producător |
| Cora (acum Carrefour) | Hypermarket | Confirmat anterior |
| Selgros | Cash & Carry | Prezent cu gama Masala Chai + altele |

Online:

| Canal | Produse Basilur | Note |
|-------|----------------|------|
| basilurtea.ro | Toată gama | Magazin oficial, Shopify |
| eMAG | 133 produse | Torb (104), Planteea (50), ABR Mag (20) |
| Planteea.ro | Gamă selectată | Magazin specializat |
| Dr. Max Farmacia | Gamă wellness | Canal farmacie |
| Paradisul Verde (Brașov) | Gamă selectată | Magazin fizic + online |

Politică eMAG (Torb Logistic): livrare gratuită pentru comenzi peste **200 RON**; taxă livrare comenzi sub 200 RON: **17 RON**; taxa în perioadele promoționale: **19,5 RON**.

### 4.4 Piața de ceai în România — context

| Indicator | Valoare |
|-----------|---------|
| Volum anual | ~3.000 tone |
| Valoare piață | ~81 mil. USD (retail) / ~120 mil. RON |
| Creștere 2019–2021 | +30% |
| Segmentul dominant | Ceai de fructe + plante (>90%) |

Top branduri concurente (cotă de piață):

| Brand | Origine | Cotă estimată |
|-------|---------|--------------|
| **Fares** | România | ~27,8% |
| **Belin** | Polonia | ~10% |
| **Plafar** | România | top 5 |
| **Aromfruct** | România | top 5 |
| **Vedda** | România | top 5 |
| **Twinings** | UK | creștere activă |
| **Yogi Tea** | Germania | prezent eMAG |
| **Basilur** | Sri Lanka | nișă premium |

> **Notă:** Basilur nu concurează pe volum cu brandurile locale. Segmentul său țintă este **ceai premium + gifting**, unde concurează cu Twinings, Yogi Tea și branduri specialty.

### 4.5 Sistem ERP — DistribNET (Junior Software)

Junior Software: firmă românească de software, fondată ~1995, București (Str. Petru Maior 86, Sector 1), specializată în software pentru firme de distribuție și import-export.

| Caracteristică | Detalii |
|---------------|---------|
| **Tip** | ERP modular offline + online |
| **Prima versiune** | 1998 |
| **Clienți** | 500+ companii în România |
| **Target** | Firme de distribuție, import-export, comerț |

Module principale: gestiune stocuri, contabilitate, salarizare (JSAL), mijloace fixe (MifAmor), producție, securitate & drepturi utilizatori (JS Admin), modul agenți (GreenTea — comenzi în timp real via smartphone), integrare nativă multinaționale (Metro, Selgros).

Avantaje relevante pentru Torb: peste 500 de rapoarte de management și vânzări; funcționează offline și online între locații; suport tehnic 24/7; integrare directă cu Selgros și Metro (canale active ale Torb); raport preț/calitate bun pentru IMM-uri.

Limitări potențiale: produs de o firmă mică, cu roadmap incert pe termen lung; integrare limitată cu platforme moderne (Shopify, eMAG API, EDI retail); pe măsura scalării Torb, nevoia de integrări e-commerce și BI va depăși capacitățile actuale.

### 4.6 Analiză SWOT — Torb Logistic SRL

✅ **Strengths (puncte forte)**
- **Exclusivitate de brand** — singurul importator oficial al grupului Basilur în România
- **Acoperire omnichannel** — hypermarketuri, cash & carry, farmacie, online
- **Brand puternic** — Basilur cu premii internaționale, identitate vizuală distinctivă
- **Certificare ecologică** — avantaj competitiv în creștere (eco-cert RO-ECO-026)
- **Creștere financiară** — +17,6% cifră de afaceri în 2024, risc insolvență scăzut
- **Vechime 25 ani** — relații consolidate cu retaileri și furnizori

⚠️ **Weaknesses (puncte slabe)**
- **Dependență totală** față de un singur furnizor (Basilur Tea Export Pvt Ltd)*
- **Echipă foarte mică** — 12 angajați; putere limitată de negociere cu retailerii mari
- **Datorii în creștere** — +102% în 2024 (de la 2M la 4M RON)
- **Marjă în scădere** — -3,32% marjă profit net, în ciuda creșterii CA
- **Portofoliu îngust** — o singură categorie de produs (ceai/cacao grup Basilur)*
- **ERP cu limitări digitale** — DistribNET slab integrat cu canale e-commerce moderne

*corectat de datele reale: portofoliul este multi-brand (12 branduri), cu 38% mărci proprii — vezi §1.

🚀 **Opportunities (oportunități)**
- **Piața premium în creștere** — consumatorul român migrează lent spre calitate superioară
- **Gifting culture** — Basilur ideal pentru cadouri corporate și ocazii speciale
- **Tipson wellness** — segment sănătate/organic în ascensiune la consumatorul urban
- **HoReCa** — canal insuficient exploatat; Selgros e deja deschis
- **E-commerce** — basilurtea.ro și eMAG pot fi scalate cu investiții moderate în marketing digital
- **Certificare eco** — diferențiator față de competitorii fără certificare

🔴 **Threats (amenințări)**
- **Dominanța locală** — Fares (28%), Belin (10%); prețuri mult mai accesibile
- **Risc valutar & logistic** — import din Sri Lanka, expus la fluctuații USD și transport maritim
- **Intrare directă Basilur** — producătorul operează deja basilurtea.ro; risc de eliminare a intermediarului
- **Concurență premium** — Twinings, Yogi Tea, Teekanne câștigă teren
- **Presiunea retailerilor** — Kaufland, Carrefour pot impune condiții dure unui furnizor mic

### 4.7 Concluzii & observații cheie (din cercetarea de birou)

1. **Torb Logistic este un operator mono-grup** — toată activitatea gravitează în jurul ecosistemului Basilur Tea. Această concentrare este principalul risc strategic. *(Corectat ulterior de datele reale: multi-brand, 38% mărci proprii.)*
2. **Basilur în România este un brand de nișă premium**, nu un competitor de volum. Segmentul său natural este consumatorul urban cu venituri medii-ridicate și cumpărătorul de cadouri.
3. **Creșterea de 17,6%** a cifrei de afaceri în 2024 indică o expansiune activă, probabil corelată cu listarea în noi rețele de retail — dar dublarea datoriilor sugerează că această expansiune se finanțează pe credit.
4. **DistribNET este un ERP adecvat dimensiunii actuale** a Torb, dar va deveni o limitare pe măsura digitalizării canalelor de vânzare (integrări API eMAG, Shopify, EDI retaileri).
5. **Cel mai important imperativ strategic** pe termen mediu: diversificarea portofoliului de branduri pentru a reduce dependența față de Basilur și creșterea prezenței în HoReCa și online.

---

## 5. AI opportunities — prioritized

AI/agentic automation opportunities identified for Torb Logistic, ordered by impact and effort. Open items are also tracked in `docs/BACKLOG.md` §Product backlog.

### Priority 1 — Quick wins (data already exists, just needs pipeline)

**A. Auto-populate dashboards from Baza** — ✅ delivered as the Flask webapp dashboard.
Connect vanzari Baza sheet → TORB_Dashboard_Managerial_FMCG.xlsx INPUT sheets automatically each month.
Stack: Python + openpyxl/pandas + Claude API for narrative commentary.
Why: Dashboard was empty. Data exists. This was a missing pipe, not a missing feature.

**B. Automate bonus calculation** — ✅ delivered 2026-06-16 (config-driven bonus module, see `context/STATUS.md`).
Read actuals from Baza → compute KPI scores per role → fill 06_Centralizare.
Bonus system was fully designed (05_Calcul_Bonus had complete payout logic). Just needed to be connected to actual sales data.

### Priority 2 — Strategic, medium effort

**C. Weekly sales rep AI brief**
Auto-generate Monday morning email per rep: YTD vs. target, clients at risk (no recent order), top SKUs, suggested focus.
Stack: Python + Claude API + email/WhatsApp delivery.

**D. Client churn/reactivation detector**
Flag clients from 3,297 active who haven't ordered in 60/90 days.
Generate prioritized call list per TT agent with context.

**E. Sales plan pre-population**
Pre-fill model_livrabil_plan_vanzari_RON.xlsx for each rep from historical Baza data.
Suggest phasing based on 2025 monthly pattern, pre-populate client opportunities.

### Priority 3 — Higher value, more setup

**F. Demand forecasting** — ✅ delivered 2026-04-19 (AutoETS per SKU, safety stock reorder, `/forecast` UI, Excel export).
2+ years of monthly data by SKU/brand/client. Clear seasonality (Oct-Dec peak).
Output: recommended stock orders per brand 4-6 weeks ahead.
Addresses the debt issue (overstock financing).

**G. Kaufland order monitoring**
Weekly alert on Kaufland order volume trend vs. same period last year.
41.4% dependency = early warning system is critical.

**H. eMAG/online competitive intelligence**
Monitor competitor pricing and listing quality on eMAG for Basilur.
Auto-generate improved product copy for underperforming listings.

### Delivered

- **Shopify stock sync** (2026-06-03) — `/stocuri` unified page, GraphQL Admin API, OAuth client credentials, request logging.
- **eMAG stock sync** — upload Excel → diff preview → sync via eMAG Marketplace API v4.5.1.
- **Demand forecasting** (F above, 2026-04-19) — AutoETS per SKU, safety stock reorder, `/forecast` UI, Excel export.
- **Automated bonus module** (B above, 2026-06-16) — config-driven monthly objectives, payout grid, month-close flow.

### Not yet explored

- HoReCa lead generation agent
- Supply chain risk monitor (Sri Lanka / USD/RON)
- basilurtea.ro D2C relansare (Shopify vs WooCommerce decision pending)

---

## 6. Raport: optimizarea Torb Logistic prin AI (2026-04-13)

### Situația actuală — ce spun datele

Torb are **infrastructura digitală** (Excel bine structurat, date istorice complete) dar **lipsa pipe-ului** care să transforme tranzacțiile în decizii. Totul e manual sau nu se face. *(Situație remediată parțial de atunci: webapp Flask + bonusare automată + forecast livrate.)*

Trei riscuri existențiale care trebuie adresate înainte de orice altceva — vezi tabelul din §3.

### Oportunități AI — în ordinea impactului real

**Nivelul 1 — Fundație (săptămânile 1-4)**

**1. Pipeline de date automat**
Acum: Baza → nimeni nu citește → dashboard gol.
Cu AI: Python job zilnic/săptămânal care extrage din `torb.db` → populează dashboardul managerial → Claude adaugă narativă automată („Vânzările Basilur au scăzut 12% față de luna trecută, main driver: Kaufland -200k RON").
Asta e fundația. Fără ea, tot restul e speculație.

**2. Automatizare bonus**
Sistemul de bonus e complet proiectat în `05_Calcul_Bonus` dar `06_Centralizare` e gol. Un script Python care citește actualele din `tranzactii` și calculează KPI-urile per agent elimină o zi de muncă manuală lunar și erorile umane.

**Nivelul 2 — Intelligence operațional (lunile 1-2)**

**3. Early warning Kaufland**
41.4% din revenue de la un singur client este risc existențial. Un agent AI care monitorizează săptămânal:
- Volumul de comenzi Kaufland vs. aceeași săptămână an trecut
- Dacă trend-ul scade > 15%, alertă imediată pe WhatsApp/email
- Context automat: ce SKU-uri pierd teren, ce magazine au scăzut

Kaufland nu dispare brusc — scade gradual. Detectezi din timp, poți acționa.

**4. Detector churn clienți TT**
3,297 de clienți activi, dar câți nu au mai comandat de 60+ zile? Nimeni nu știe acum. Un job săptămânal care:
- Identifică clienții inactivi per agent TT
- Prioritizează după valoarea istorică
- Generează lista de apeluri luni dimineața cu context: „Client X: ultima comandă acum 73 zile, comanda medie 1,200 RON, a cumpărat de obicei Celmar + Leonex"

Recuperarea unui client existent costă de 5-7x mai puțin decât un client nou.

**5. Brief săptămânal per agent**
Fiecare agent primește luni dimineața (automat, WhatsApp sau email):
- YTD actual vs. target
- Clienți în risc (nu au comandat recent)
- Top SKU-uri de propus în acea săptămână (bazat pe sezonalitate istorică)
- Comparație cu colegii (fără să fie invaziv)

Bogdan Dragnea generează 55.6% din revenue — dacă el nu știe zilnic unde stă față de target, pierzi bani. Dacă ceilalți 4 agenți primesc direcție concretă în loc de obiective vagi, productivitatea crește.

**Nivelul 3 — Predicție și strategie (lunile 2-4)**

**6. Demand forecasting**
Ai 2+ ani de date lunare per SKU/brand/client cu sezonalitate clară (Oct-Dec = peak). Un model simplu (chiar și Prophet sau ARIMA) poate genera:
- Recomandări stoc per brand cu 4-6 săptămâni înainte
- Alertă de sub-stoc potențial înainte de sezon gifting
- Optimizare cash flow (evitarea suprastocului iarna)

Datele există. Nimeni nu le folosește predictiv acum.

**7. Optimizare portofoliu brand**
Basilur = 31%, dar ce marjă? Toras = 22%, Leonex = 20% — mai ieftine sau mai profitabile? Fără date de cost în sistem, AI poate cel puțin identifica:
- Care branduri cresc vs. scad trend multi-an
- Care clienți cumpără un singur brand (risc de concentrare)
- Cross-sell opportunities: clienți Basilur care nu cumpără Celmar

**8. eMAG + online competitive intelligence**
Basilur.ro + eMAG = 0.6% + 0.5% din revenue = 1.1% din total. E dramatic de mic pentru o companie cu brand recunoscut. Un agent AI care:
- Monitorizează zilnic prețurile concurenților pe eMAG pentru categoriile Basilur/Tipson
- Alertează dacă Torb e mai scump cu > 10%
- Generează copy îmbunătățit pentru listinguri cu performanță slabă

**Nivelul 4 — Expansiune (luna 4+)**

**9. HoReCa lead generation**
România are mii de cafenele, restaurante, hoteluri care ar putea vinde Basilur/Delaviuda. Un agent AI care:
- Scrape-uiește Google Maps pentru HoReCa în zonele agenților TT
- Prioritizează după recenzii, tip, capacitate
- Generează script de apel personalizat per tip de client

**10. Reducerea dependenței de Bogdan Dragnea**
Acesta e cel mai important risc structural. Câteva direcții AI:
- Documentare automată a relațiilor: ce a negociat Bogdan cu fiecare client, la ce prețuri, ce condiții speciale
- Transfer knowledge: dacă pleacă mâine, ce știe el și nu există nicăieri altundeva?
- Urmărire pipeline KA: alertă dacă un client major din portofoliul lui nu a comandat conform pattern-ului normal

### Ordinea recomandată

```
Luna 1:  Pipeline date → Dashboard activ → Bonus automat
Luna 2:  Churn detector → Brief agent → Early warning Kaufland
Luna 3:  Demand forecasting → Brand portfolio analysis
Luna 4+: eMAG intelligence → HoReCa leads → Knowledge capture Bogdan
```

Totul e construibil cu `torb.db` existent + Python + Claude API. Nu e nevoie de integrări externe complexe sau date noi — datele există deja, lipsesc uneltele care le transformă în acțiuni.

**Cel mai important:** primele 3 livrabile sunt pipe-uri, nu AI sofisticat. Nu are rost să construiești forecasting dacă managementul nu vede nici vânzările de ieri.

---

## 7. Plan Strategic 2026–2030 (v1.0)

**Data elaborării:** 19 aprilie 2026
**Orizont:** 5 ani (2026–2030)
**Autor:** AI consulting (Claude) + input Torb Logistic
**Statut document:** v1.0 — plan strategic cadru. Revizuire recomandată: trimestrial pe 2026, apoi semestrial 2027–2030. Proprietar: conducere Torb Logistic. Elaborat cu: AI consulting (Claude Opus 4.7, April 2026).
**Statusul execuției:** `context/STATUS.md` (actualizat la fiecare schimbare de stare).

### 7.1 Mandatul și obiectivul

Consolidarea Torb Logistic SRL ca **distribuitor FMCG de specialitate, multi-brand, multi-canal**, cu poziție de lider regional în segmentele premium (ceai, confectionery, beauty, cadouri corporate) în România și prezență secundară în piețele CEE apropiate (Ungaria, Bulgaria, Republica Moldova, Polonia).

#### Țintă financiară 2030

| KPI | 2025 (baseline) | 2030 (țintă) | Variație |
|---|---|---|---|
| Cifră de afaceri | ~15M RON (~€3M) | **€15M (~75M RON)** | **5×** / CAGR 37.97% |
| Marjă netă (PAT) | neclar, probabil 1–3% | **3–6%** | menținere + îmbunătățire |
| EBITDA% | probabil 4–7% | **15–20%** | **+10–13pp** |
| EBITDA absolut | ~0.6–1M RON | **€2.25–3.0M (~11–15M RON)** | **15–25×** |

**Interpretare critică:** Cifrele de mai sus NU descriu economia unui distribuitor FMCG pur. Un distribuitor tradițional în CEE face 2–5% EBITDA. Ținta de 15–20% EBITDA este plauzibilă pentru Torb **pentru că Torb este deja un hibrid brand house + distribuitor**: Celmar și Leonex sunt mărci proprii și reprezintă împreună ~38% din CA 2025 (5.66M RON). Aceasta este o fundație economică valoroasă care urcă EBITDA% de bază peste media distribuitorilor puri. Strategia pe 5 ani nu este o migrare de la zero spre brand house — este **accelerarea și internaționalizarea mărcilor proprii existente** + adăugarea de 1–2 mărci noi (organic sau achiziție) + extindere a canalelor directe. Toate deciziile din planul următor trebuie să protejeze mix-ul de marjă, nu doar volumul.

### 7.2 Diagnostic baseline (aprilie 2026)

#### Ce face Torb astăzi

- **Hibrid brand house + distribuitor FMCG premium.** Deține două mărci proprii (Celmar și Leonex) = **38% din CA 2025** (5.66M RON) și distribuie alte 10 mărci, dintre care Basilur este cea mai importantă (31%).
- 15M RON CA 2025, 3,297 clienți activi, 5 roluri comerciale active.
- Canale: IKA (Kaufland 41%, Carrefour, Mega, Auchan, Profi), TT (agenți de teren), Pharma (Dr.Max, Tei, Fildas), Cash&Carry (Selgros, Metro), Online (site propriu + eMAG — sub 1.5% din CA), Export minor (HUN-TRADE, BRANDMIX).
- Echipa: **concentrare periculoasă** — Bogdan Dragnea 55.6% din CA, Kaufland 41.4% din CA.

#### Asset strategic insuficient exploatat: mărcile proprii

Celmar și Leonex sunt **cel mai valoros activ al Torb** și sunt probabil sub-investite din perspectiva marketing, internațională și D2C. Fiecare euro investit în aceste mărci capturează economia de brand owner (marjă brută 45–55%), nu doar comisionul de distribuție (15–25%). Planul 2026–2030 pune aceste mărci pe poziția centrală a strategiei.

#### Ce știm că este spart

1. **Pipeline-ul de date lipsește.** Dashboardul managerial este gol. Bonusarea nu se calculează automat. Raportarea e manuală → lentă → decizie oarbă.
2. **Concentrarea de risc.** Un singur om (Bogdan) și un singur retailer (Kaufland) dețin majoritatea afacerii. Plecarea lui Bogdan sau delistarea din Kaufland = eveniment existențial.
3. **Online subexploatat.** 1.5% din CA în online (site + eMAG) este sub pragul oricărui brand premium modern. Aici e cash lăsat pe masă.
4. **Margin management multi-brand.** 12 mărci cu marje diferite, fără vizibilitate la nivel de SKU × client × canal. Probabil există SKU-uri care se vând la marjă negativă fără ca nimeni să observe.
5. **Portofoliu cu dependențe externe.** Exclusivitățile sunt reînnoibile anual sau bi-anual → brand owner poate schimba distribuitorul. Fără mărci proprii, Torb nu are "moat".

#### Ce funcționează și trebuie păstrat

- Relația cu Kaufland — 41% din CA, dar e și cel mai dificil cont de câștigat. Scalabilă în alte categorii.
- Portofoliul Basilur → poziția de distribuitor exclusiv pe ceai premium e un activ real.
- Canalul pharma (Dr.Max, Fildas, Tei) — sub 10% din CA dar cu marjă bună și spațiu de creștere.
- Sezonalitatea Q4 (cadouri Octombrie–Decembrie) → oportunitate clară de corporate gifting.
- Infrastructura administrativă și logistica — funcțională la 15M RON, trebuie doar scalată.

### 7.3 Teza strategică

**"Torb 2030" = un holding FMCG de specialitate cu trei motoare de creștere:**

1. **Distribuție tradițională premium în România** (bază stabilă, marjă brută 20–25%, EBITDA 5–8%) — rămâne motorul de volum, dar scade ca pondere relativă.
2. **Brand house propriu** — scalare Celmar și Leonex + 1–2 mărci noi (organic sau achiziție), cu extindere internațională (marjă brută 40–55%, EBITDA 18–25%).
3. **Canale directe cu valoare adăugată** — D2C online, HoReCa, corporate gifting B2B (marjă brută 30–45%, EBITDA 15–22%).

**Mix 2025 (baseline): 62% distribuție / 38% mărci proprii / <2% canale directe.**
**Mix 2030 (țintă): 45% distribuție / 35% mărci proprii / 20% canale directe.**

Media ponderată, la mix-ul țintă 45/35/20, produce matematic EBITDA blended de 14–19% — în banda țintă de 15–20%.

**Geografia:** România rămâne 65–75% din CA 2030. Export CEE (HU, BG, MD, PL) devine 25–35%, predominant pe Celmar, Leonex și eventual mărci noi (Torb controlează exclusivitatea geografică), nu pe redistribuire de mărci care au deja distribuitori locali.

### 7.4 Cei 5 piloni strategici

#### Pilon 1 — Consolidare operațională România (foundation, 2026)

**Logica:** Nu poți scala ce nu măsori. Înainte de creștere agresivă, trebuie să ai P&L pe brand × canal × client × agent, în timp aproape real.

**Inițiative:**
- **1.1.** Pipeline automat Baza → Dashboard managerial (ownership: AI, 30 zile).
- **1.2.** Bonusare automată lunară cu score per KPI și roll-up pe echipă (60 zile).
- **1.3.** CRM operațional pe cei 3,297 clienți — ultimă comandă, status, agent responsabil, scor de activitate (90 zile).
- **1.4.** Margin dashboard SKU × client × lună — identificare lineitems negative și renegociere (120 zile).
- **1.5.** Plan de dezcentralizare Dragnea — contract de retenție + plan de succesiune, transfer gradual al unor conturi către Oana/Claudiu în 12–24 luni (reducere de la 55% la <40% din CA by 2027).
- **1.6.** Plan Kaufland "hedge" — creștere accelerată în Carrefour, Mega Image, Profi pentru a reduce share-ul Kaufland de la 41% la <30% by 2028 **prin creștere, nu prin scădere în Kaufland**.

**Target 2026:** CA 19–22M RON (+27–47% organic). EBITDA 6–8%.

#### Pilon 2 — Scalarea mărcilor proprii (Celmar, Leonex) și extindere portofoliu (2026–2030)

**Logica:** Torb are deja 38% din CA în economia de brand owner. Asta este fundația EBITDA-ului țintit. Prioritatea #1 nu este crearea de mărci noi, ci **maximizarea potențialului Celmar și Leonex** prin poziționare, distribuție internațională, canale noi și extindere SKU — apoi adăugarea de 1–2 mărci complementare.

**2A. Scalare Celmar și Leonex (2026–2030) — inițiativă centrală**

- **2A.1. Audit de poziționare și SKU (2026 Q2–Q3).** Ce vinde efectiv Celmar și Leonex? Pe ce SKU-uri se face marja și pe care se pierde? Ce percep clienții finali? Task: interviuri cu 30 de clienți B2B + 100 de consumatori finali + analiza Nielsen/retail.
- **2A.2. Rebranding / refresh (2026–2027).** Dacă auditul arată gap de percepție premium, redesign packaging, naming architecture, brand guidelines. Buget indicativ: 40–80k EUR per brand.
- **2A.3. Extinderea SKU (2026–2028).** Lansare de 4–8 SKU-uri noi per brand în 24 luni, pe adiacențe (ex: dacă Celmar e cosmetică, extinderea în wellness/aromatherapy; dacă Leonex e îngrijire personală, extinderea în baby/natural).
- **2A.4. Listing IKA suplimentar (2026–2027).** Celmar și Leonex în Kaufland, Carrefour, Mega, Profi — acolo unde nu sunt deja. Obiectiv: +30–40% distribuție numerică în 18 luni.
- **2A.5. Export CEE (2027–2030).** Celmar și Leonex sunt primele mărci de lansat în Ungaria, Bulgaria, Republica Moldova, Polonia. Nu necesită permisiune terță. Țintă: 25% din CA Celmar+Leonex din export până în 2030.
- **2A.6. D2C dedicat (2026–2027).** Site propriu pentru fiecare marcă (sau umbrella torbbrands.ro), content marketing, programe de fidelitate, bundles.
- **2A.7. KAM dedicat pe mărcile proprii (2026).** O persoană cu P&L ownership pe Celmar + Leonex, separat de distribuția Basilur.

**Țintă 2030 pentru mărcile proprii:** creștere de la 5.66M RON (€1.13M) la ~26M RON (€5.2M) — ~4.6× în 5 ani, CAGR ~36%. Share în mix: de la 38% → ~35% (relativ stabil, dar în absolut 4×+).

**2B. Adăugare de mărci noi (2027–2029)**

- **2B.1. O marcă nouă organică — private label pe tea & infusions (2026–2027 pilot).** Torb creează sub un brand propriu un ceai premium, folosind expertiza din distribuția Basilur. Pilot 2 SKU, scale la 8 SKU în 18 luni dacă validarea ține.
- **2B.2. Achiziția unei mărci mici locale (2027–2028).** O marcă românească de specialitate în categorie adiacentă (gourmet food, miere, cafea artizanală) cu CA 1–3M RON, achiziționată la 4–6× EBITDA. Integrare distribuțională + acceleration prin canalele Torb.

**2C. Curățare portofoliu distribuit (2026)**

- **2C.1. Evaluare margin per marcă distribuită.** Dacă o marcă distribuită are marjă brută <18% și nu aduce volum strategic pentru IKA, se renegociază sau se elimină.
- **2C.2. Rationalizare SKU general.** Delistare SKU-uri long-tail cu rotație <6×/an indiferent de marcă.

**2D. Corporate gifting și bundling cross-brand (2026)**

- **2D.1.** Coșuri cadou corporate B2B care combină Basilur + Celmar + Leonex + Delaviuda + produsele noi. Marja pe coș este mai mare decât pe SKU-uri individuale. Personalizare ambalaj pentru corporații (500+ companii medii în RO).

**Target combinat Pilon 2, 2028:** Mărci proprii + private label nou = 22% din CA. Contribuție la EBITDA blended: +3–5pp față de baseline.

#### Pilon 3 — Expansiune canal direct (2026–2030)

**Logica:** Canalele directe (D2C, HoReCa, corporate) au marjă dublă față de IKA și nu depind de negocierile anuale de listing.

**Inițiative:**
- **3.1. basilurtea.ro relansare (2026).** Site cu checkout Shopify/WooCommerce, SEO, content marketing (cultură ceai, rețete, rituale), program de fidelitate, abonament ceai lunar. Target: 3% din CA 2026, 6% din CA 2028, 10% din CA 2030. Marjă 40%+.
- **3.2. eMAG + marketplace-uri (2026–2027).** Creștere de la 0.5% la 4% din CA prin listings optimizate, PPC controlat, bundling. Extindere pe eMAG.hu, emag.bg.
- **3.3. HoReCa dedicat (2027).** Angajare 1 key account manager HoReCa. Target: hoteluri 4–5*, cafenele specialty, restaurante fine dining. Portofoliu: ceai premium, cafea, gourmet gifting pentru camere/minibar. Obiectiv 2028: 4% din CA. Obiectiv 2030: 8%.
- **3.4. B2B corporate gifting (2026).** Platformă online dedicată (torbgifts.ro sau echivalent) pentru cadouri corporate de Crăciun, Paști, aniversări. Integrări cu HR-uri din corporații (400–500 companii medii în RO). Obiectiv Q4 2026: 800k RON. Obiectiv 2030: 6–8M RON.
- **3.5. Magazin concept/pop-up Basilur (2028).** Un flagship Basilur în București (Afi, AFI Cotroceni, Baneasa, Mega Mall) ca showcase brand + canal vânzare. Evaluat opțional după datele D2C.

**Target 2030:** Canalele directe = 25–30% din CA, contribuind disproporționat la marjă.

#### Pilon 4 — Expansiune geografică CEE (2027–2030)

**Logica:** CEE FMCG este fragmentat, marjele sunt mai bune decât în România pentru premium importat, și Torb poate replica playbook-ul de distribuție.

**Prioritizare:**
- **Ungaria (2027).** Deja cont activ HUN-TRADE KFT. Aprofundare: angajare 1 sales manager, listing direct în Spar Hungary, Auchan HU, dm.hu. **Focus principal: Celmar + Leonex** (mărci proprii, Torb controlează pricing și exclusivitate) + private label nou. Target 2030: 1.5M EUR.
- **Republica Moldova (2027).** Limbaj, cultură, piață mică dar fără bariere. Focus: Celmar + Leonex cu distribuitor local. Target 2030: 0.3M EUR.
- **Bulgaria (2028).** Piață similară RO, consumator premium în creștere. Parteneriat distribuțional sau filială proprie. Focus: mărci proprii. Target 2030: 0.8M EUR.
- **Polonia (2029).** Piață mare, competitivă. Intrare doar pe o nișă (mărci proprii pe canalele specialty și cadouri). Target 2030: 0.5M EUR.
- **Germania/Austria (2029–2030, evaluat opțional).** Doar prin parteneri distributori selectivi, exclusiv pentru mărcile proprii. Nu prin filială.

**De ce Celmar și Leonex sunt vehiculul ideal de export:** nu există constrângeri contractuale de exclusivitate geografică de la un brand owner terț. Torb poate decide oricând să vândă în orice țară. Pentru mărcile distribuite (Basilur etc.), exportul depinde de negocierea cu brand owner — de multe ori există deja distribuitori locali și nu se poate.

**Total export 2030:** 3–4.5M EUR din 15M EUR total = 20–30%, majoritatea pe mărci proprii.

#### Pilon 5 — Tehnologie, date, AI (continuu, 2026–2030)

**Logica:** Torb nu va avea niciodată bugetul de IT al unui Carrefour. Dar AI-ul permite o echipă de 15–20 oameni să opereze cu eficiența unei echipe de 40.

**Inițiative:**
- **5.1.** Data warehouse propriu (SQLite → Postgres la 30M RON CA) cu pipeline din SmartBill/ERP → data model → BI (Metabase/Superset).
- **5.2.** AI Sales Brief — generare săptămânală pe fiecare agent, cu clienți at-risk, oportunități, forecast personal.
- **5.3.** Forecast demand per SKU × lună × canal pentru reducerea stocurilor și a datoriei de trezorerie.
- **5.4.** Client Health Score — flag automat pentru clienți cu risc de churn, pe toate segmentele.
- **5.5.** AI Copywriter — generare descrieri produs eMAG/Shopify, bundling recomandări, content de blog.
- **5.6.** RPA pe procesele back-office — facturare, reconciliere bancă, comenzi automate.
- **5.7.** Bonus calculator live — fiecare agent vede scorul lui în orice moment al lunii. Tip de schimbare de comportament.

**Buget IT/AI estimat:** 1.5–2% din CA anual (moderat, dar cu ROI la 12–18 luni).

### 7.5 Roadmap anual 2026–2030

**2026 — Foundation & Organic Scale**
- CA: 19–22M RON (~€3.8–4.4M) — +27 până la +47% vs 2025
- Focus: pipeline de date, bonusare automată, CRM, D2C start, corporate gifting pilot, angajare 1 KAM suplimentar
- Risc major: dacă Dragnea pleacă înainte de plan de tranziție → −30% CA
- EBITDA țintă: 6–8%

**2027 — Portfolio & Export Start**
- CA: 28–32M RON (~€5.6–6.4M) — +45% vs 2026
- Lansare private label (tea). Intrare formală HU + MD. Achiziție brand local. HoReCa KAM.
- EBITDA țintă: 9–11%

**2028 — Scale & Brand House Emerge**
- CA: 42–48M RON (~€8.4–9.6M) — +50%
- Private label + brand propriu = 12–15% CA. Bulgaria lansare. Kaufland sub 30% din CA.
- EBITDA țintă: 12–14%

**2029 — Consolidation & Polonia**
- CA: 58–65M RON (~€11.6–13M) — +35%
- Polonia pilot. Portfolio optimization. Second private label. Possible acquisition #2.
- EBITDA țintă: 14–17%

**2030 — Target State**
- CA: 75M RON (~€15M) — +15–25%
- Mix: 50% distribuție tradițională, 30% brand house/private label, 20% canale directe.
- EBITDA țintă: 15–20%. Net margin: 3–6%.

### 7.6 Model financiar indicativ (RON milioane)

| Linie | 2025 | 2026 | 2027 | 2028 | 2029 | 2030 |
|---|---|---|---|---|---|---|
| **CA net** | 15.0 | 20.5 | 30.0 | 45.0 | 62.0 | 75.0 |
| Creștere % | — | +37% | +46% | +50% | +38% | +21% |
| **Marjă brută %** | ~22% | 23% | 25% | 28% | 30% | 32% |
| Marjă brută (abs) | 3.3 | 4.7 | 7.5 | 12.6 | 18.6 | 24.0 |
| **OpEx %** | ~18% | 17% | 16% | 15.5% | 15% | 14.5% |
| OpEx absolut | 2.7 | 3.5 | 4.8 | 7.0 | 9.3 | 10.9 |
| **EBITDA** | 0.6–1.0 | 1.2–1.6 | 2.7–3.0 | 5.0–5.8 | 9.0–10.0 | **11–15** |
| **EBITDA %** | 4–7% | 6–8% | 9–10% | 11–13% | 14–16% | **15–20%** |
| D&A + Dob + Tax | ~2% | 2% | 3% | 5% | 8% | 11–14% |
| **Net profit %** | 1–3% | 3–4% | 3–5% | 3–5% | 3–5% | **3–6%** |

**Ipoteze cheie care fac ca țintele să țină:**
1. **Baseline mai solid decât un distribuitor tipic**: Torb are deja 38% din CA în economia de brand owner prin Celmar și Leonex. EBITDA% actual este probabil în banda 7–11%, nu 4–7% ca la un distribuitor pur.
2. Mixul de marjă evoluează: în 2030, ~35% din CA vine din mărci proprii (marjă brută 45–50%), 20% din canale directe (marjă brută 35%+), 45% din distribuție tradițională (marjă brută 22%).
3. OpEx crește sub-liniar (scale + AI) — de la 18% la 14.5%.
4. D&A urcă (scale mărci proprii, achiziție brand #3, infrastructură IT, flotă extinsă, eventual flagship retail) — reducând diferența EBITDA → net la banda 3–6%.

### 7.7 Investiții necesare și finanțare

#### CapEx & M&A cumulat 2026–2030: **~€3.5–5M**

| Buget | Estimare (EUR) |
|---|---|
| Private label setup (R&D, mold-uri, prima producție, registrare marcă) | 150–250k |
| Achiziție brand local (an 2027) | 400–800k |
| Infrastructură IT & data (5 ani) | 200–300k |
| Warehouse extension (când CA > 40M RON) | 300–500k |
| Vehicle fleet expansion | 200–400k |
| Marketing D2C & brand building | 500–800k (pe 5 ani) |
| Corporate gifting platform & inventory | 150–250k |
| Expansiune geografică (HU/BG/MD/PL) | 500–900k |
| Eventual flagship retail (opțional) | 300–500k |
| Achiziție #2 brand (2029, opțional) | 500–1,500k |
| **Total estimat** | **€3.2–6.2M** |

#### Surse de finanțare
1. **Reinvestirea profitului** (cash flow operațional + EBITDA în creștere)
2. **Credit bancar** pentru stoc / CapEx (Torb are track record bancar bun ca distribuitor)
3. **Fonduri europene** POR/PNRR pentru digitalizare, expansiune export (până la 50% nerambursabil)
4. **Posibilă intrare minoritară de capital extern** (private equity CEE sau family office) în 2028–2029 pentru a finanța expansiunea internațională și achiziția #2 — diluție 15–25% în schimbul €2–3M. Opțional, nu obligatoriu.

### 7.8 Riscuri majore și măsuri de mitigare

| Risc | Probabilitate | Impact | Mitigare |
|---|---|---|---|
| Plecarea Bogdan Dragnea | Medie | Existențial | Plan de retenție (compensație, bonus long-term, posibil partenership minoritar). Tranziție treptată conturi către Oana/Claudiu. |
| Delistare Kaufland | Mică-Medie | Foarte mare | Diversificare activă: Carrefour, Mega, Profi să crească 2× pe termen mediu. Nu reduce Kaufland, dar reduce share relativ. |
| Ruptură cu Basilur (brand owner) | Mică | Mare | Contract multi-anual (3+ ani). Dezvoltare private label care reduce dependența. |
| Eșec private label | Medie | Mediu | Pilot mic (2 SKU, 3 clienți), scale doar după validare 6 luni. Pregătit plan de exit dacă marja brută < 40%. |
| Recesiune RO 2027–2028 | Medie | Mediu | FMCG premium e mai rezilient decât luxury, dar corporate gifting scade primul. Mix echilibrat. |
| USD/RON volatilitate (import Sri Lanka) | Medie | Mediu | Hedging valutar pentru comenzi > 200k EUR. Surse alternative de aprovizionare (ceai turcesc/kenyan). |
| Eșec expansiune CEE | Medie | Mic-Mediu | Intrare graduală: MD și HU primele (cost mic), BG și PL dacă primele merg. Nu angajare mare de CapEx upfront. |
| Concurență nouă în România (retail specialty chains) | Mare | Mediu | Diferențiere prin premium branding + D2C + corporate gifting (segmente mai puțin accesibile pentru chains). |
| Cash flow crisis / stoc supradimensionat | Medie | Mare | Forecasting de cerere AI-based, rotație stoc < 60 zile pe toate mărcile până 2027. |

### 7.9 Indicatori cheie de urmărit (OKR-uri anuale)

#### North Star Metrics (monitorizare lunară)
- CA lunară vs buget
- EBITDA rolling 12 luni
- Share Kaufland / share top-5 clienți
- Share Bogdan / share top-3 agenți
- % CA din canalele directe (D2C + HoReCa + corporate gifting)
- % CA din private label + brand propriu
- DSO (zile creanțe) și DPO (zile datorii) — managementul capitalului
- Rotația stocului (zile)

#### Ținte pe KPI by 2030
- Share Kaufland: < 25% (vs 41% în 2025)
- Share Dragnea: < 30% (vs 55.6% în 2025)
- CA online + D2C: > €1.5M (vs €30k în 2025 — 50×)
- CA private label + brand propriu: > €3M (vs €0 în 2025)
- CA export CEE: > €3M (vs €100k în 2025 — 30×)
- Headcount total: 25–30 (vs ~10 în 2025)

### 7.10 Acțiuni concrete în următoarele 90 de zile (aprilie–iulie 2026)

**Aceste acțiuni sunt non-negociabile, cu cost mic și impact mare. Fără ele, planul rămâne slideware.** Statusul per acțiune se ține în `context/STATUS.md`.

1. **Pipeline date: Baza → Dashboard** (deadline: 15 mai 2026).
   Connect vanzari_01.03.2026.xlsx / SQLite `data/torb.db` → dashboard managerial auto-refreshed săptămânal. Owner: AI/IT.

2. **Bonusare automată lunară** (deadline: 31 mai 2026).
   Pornind de la datele Baza, completare automată 06_Centralizare din bonusare_torb_structura_echipa.xlsx. Email săptămânal către fiecare agent cu scorul lui curent.

3. **Margin audit SKU × client** (deadline: 15 iunie 2026).
   Identificare SKU-uri cu marjă brută < 15% și plan de renegociere / delistare / rework packaging.

4. **Retention deal Bogdan Dragnea** (deadline: 30 iunie 2026).
   Contract cu pachet compensație + bonus long-term + plan de tranziție pentru a reduce concentrarea lui de la 55% la 45% în 18 luni, fără a-l demotiva.

5. **basilurtea.ro audit + plan relansare** (deadline: 30 iunie 2026).
   Decizie: Shopify sau WooCommerce. Buget 20–30k RON pentru relansare cu SEO + content marketing pe 6 luni.

6. **Corporate gifting pilot Q4 2026** (deadline preparare: 31 iulie 2026).
   Catalog B2B ready pentru campania septembrie–decembrie 2026. Target minim: 500k RON CA pe corporate gifting în Q4 2026.

7. **Audit strategic Celmar + Leonex** (deadline: 31 iulie 2026) — **prioritate top**.
   P&L per marcă (ideal per SKU × canal), benchmark cu competitorii de categorie, interviuri cu 20–30 clienți B2B și 50–100 consumatori finali. Livrabil: raport cu decizii go/no-go pe (a) rebranding, (b) extindere SKU, (c) KAM dedicat, (d) export HU/MD ca prim test. Aceasta este cea mai valoroasă investiție de 90 de zile — mărcile proprii sunt activul central al strategiei pe 5 ani.

8. **Kick-off private label R&D (marcă nouă de tea)** (deadline: 31 iulie 2026).
   Short list 3 producători (2 din Sri Lanka, 1 european). Briefing pe ambalaj și pozitionare. Decizie go/no-go până în septembrie 2026.

9. **Documentarea proceselor critice** (deadline: 31 iulie 2026).
   Flow-urile de comandă, facturare, colectare, listing IKA scrise în manuale → reducerea riscului de "knowledge în capul unei singure persoane".

### 7.11 Principiu de decizie pe 5 ani

La fiecare decizie strategică (nou brand, nou canal, nouă piață), aplică filtrul:

> **"Această decizie crește EBITDA% blended al Torb, sau doar cifra de afaceri?"**

Creșterea CA fără creșterea EBITDA% este irelevantă pentru ținta 2030. Dacă o oportunitate generează +10% CA dar scade EBITDA blended cu 0.5pp, se respinge. Dacă o oportunitate generează +5% CA dar urcă EBITDA cu 1pp, se acceptă.

Distribuitori "mari și subțiri" sunt expuși. Ținta Torb 2030 este **specialty FMCG house**, nu grosist de volum.

### 7.12 Anexe de lucru (de elaborat în fazele următoare)

- **A1.** Model financiar detaliat în Excel cu scenarii base/bear/bull.
- **A2.** Business case separat pentru private label (producător, volum minim, pricing, break-even).
- **A3.** Due diligence template pentru achiziție brand local.
- **A4.** Playbook expansiune HU/BG (pricing, listing, distribuție).
- **A5.** Plan de migrare ERP/CRM dacă CA trece de 30M RON.
- **A6.** Plan de guvernanță și board advisory (când CA > 40M RON).
