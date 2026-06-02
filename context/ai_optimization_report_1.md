# Raport: Optimizarea Torb Logistic prin AI
*Generat: 2026-04-13*

---

## Situația actuală — ce spun datele

Torb are **infrastructura digitală** (Excel bine structurat, date istorice complete) dar **lipsa pipe-ului** care să transforme tranzacțiile în decizii. Totul e manual sau nu se face.

Trei riscuri existențiale care trebuie adresate înainte de orice altceva:

| Risc | Magnitudine | Consecință |
|---|---|---|
| Bogdan Dragnea pleacă | 55.6% din revenue = 8.35M RON | Business în pericol |
| Kaufland delistează | 41.4% din revenue = 6.2M RON | Business în pericol |
| Niciun dashboard activ | Management orb în timp real | Decizii tardive |

---

## Oportunități AI — în ordinea impactului real

### Nivelul 1 — Fundație (săptămânile 1-4)

**1. Pipeline de date automat**

Acum: Baza → nimeni nu citește → dashboard gol.
Cu AI: Python job zilnic/săptămânal care extrage din `torb.db` → populează dashboardul managerial → Claude adaugă narativă automată ("Vânzările Basilur au scăzut 12% față de luna trecută, main driver: Kaufland -200k RON").

Asta e fundația. Fără ea, tot restul e speculație.

**2. Automatizare bonus**

Sistemul de bonus e complet proiectat în `05_Calcul_Bonus` dar `06_Centralizare` e gol. Un script Python care citește actualele din `tranzactii` și calculează KPI-urile per agent elimină o zi de muncă manuală lunar și erorile umane.

---

### Nivelul 2 — Intelligence operațional (lunile 1-2)

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
- Generează lista de apeluri luni dimineața cu context: "Client X: ultima comandă acum 73 zile, comanda medie 1,200 RON, a cumpărat de obicei Celmar + Leonex"

Recuperarea unui client existent costă de 5-7x mai puțin decât un client nou.

**5. Brief săptămânal per agent**

Fiecare agent primește luni dimineața (automat, WhatsApp sau email):
- YTD actual vs. target
- Clienți în risc (nu au comandat recent)
- Top SKU-uri de propus în acea săptămână (bazat pe sezonalitate istorică)
- Comparație cu colegii (fără să fie invaziv)

Bogdan Dragnea generează 55.6% din revenue — dacă el nu știe zilnic unde stă față de target, pierzi bani. Dacă ceilalți 4 agenți primesc direcție concretă în loc de obiective vagi, productivitatea crește.

---

### Nivelul 3 — Predicție și strategie (lunile 2-4)

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

---

### Nivelul 4 — Expansiune (luna 4+)

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

---

## Ordinea recomandată

```
Luna 1:  Pipeline date → Dashboard activ → Bonus automat
Luna 2:  Churn detector → Brief agent → Early warning Kaufland  
Luna 3:  Demand forecasting → Brand portfolio analysis
Luna 4+: eMAG intelligence → HoReCa leads → Knowledge capture Bogdan
```

Totul e construibil cu `torb.db` existent + Python + Claude API. Nu e nevoie de integrări externe complexe sau date noi — datele există deja, lipsesc uneltele care le transformă în acțiuni.

**Cel mai important:** primele 3 livrabile sunt pipe-uri, nu AI sofisticat. Nu are rost să construiești forecasting dacă managementul nu vede nici vânzările de ieri.
