# MySolido — Datamodel-notitie MyTerms-demo (subtaak 2, 3 en 4)

| | |
|---|---|
| **Datum** | 20 september 2026 |
| **Status** | Werkafspraak: de namen hieronder zijn leidend voor subtaak 2 (gegevensselectie), 3 (ODRL-policy) en 4 (acceptatie en consentrecord). Subtaak 2 bouwt punt 1 en 2; punt 3 wordt nu alleen vastgelegd. |
| **Vervolg op** | `docs/mysolido_verslag_myterms-demo-inventarisatie_19-09-2026.md` (§6, "datamodel-notitie") |
| **Besluiten 20-09 die hierin verwerkt zijn** | open Offer als standaard maar `offerMode` nu al in het model; vier scenariovelden vast maar generiek gebouwd (één constante); snapshot boven verwijzing; Bridge-variant A |
| **DPV-PD-controle** | DPV-PD 2.1 (16 maart 2025, w3c-cg.github.io/dpv/2.1/pd/), alleen de termen in de tabellen bij punt 1 gecontroleerd |

---

## 1. Attributen

Eén bron van waarheid: de constante `PROFILE_ATTRIBUTES` in `app.py`, bij de andere profielconstanten (vóór `INTENTION_CATEGORIES`). Elke sleutel is Engels; de UI toont het Nederlandse `label`. De urn is altijd `urn:mysolido:attribute:<key>`. Per attribuut staan vastgelegd: `label`, `group`, `input` (select / text / int / bool / composite / list), `options`, `dpv` (geverifieerde DPV-PD-term of `mysolido:<key>`), `path` (waar de waarde in `profiel/profiel.jsonld` staat) en bij composite de `fields`. Een vijfde attribuut is later één regel in deze constante; formulier, selectie, snapshot en (in subtaak 3 en 4) policy-targets en `dpv:hasPersonalData` volgen daaruit.

De vier scenario-attributen:

| key | urn | Label | Groep | Invoer | Opslag in `profiel.jsonld` | DPV-PD |
|---|---|---|---|---|---|---|
| `age_category` | `urn:mysolido:attribute:age_category` | Leeftijdscategorie | `personal` (nieuw, "Persoonlijk") | keuzelijst `18-24` / `25-34` / `35-44` / `45-54` / `55-64` / `65+` | `pd:AgeRange` (string) | `pd:AgeRange`, geverifieerd (subklasse van `pd:Age`) |
| `postal_area` | `urn:mysolido:attribute:postal_area` | Postcodegebied (4 cijfers) | `housing`, naast het bestaande vrije veld "Regio / provincie" dat blijft | tekst, precies 4 cijfers | `pd:PostalCode` (string) | `pd:PostalCode`, geverifieerd (subklasse van `pd:PhysicalAddress`) |
| `vehicle_type` | `urn:mysolido:attribute:vehicle_type` | Voertuigtype | `vehicle` (bestaand veld) | keuzelijst auto / motor / scooter / fiets / geen (ongewijzigd) | `pd:Vehicle[0].type` (ongewijzigd) | `pd:Vehicle`, geverifieerd |
| `claims_history` | `urn:mysolido:attribute:claims_history` | Schadeverleden | `insurance` | composite: `claim_free_years` (geheel getal, "Schadevrije jaren") en `claims_last_3_years` (ja/nee, "Schade geclaimd in de laatste 3 jaar") | `mysolido:claimsHistory: {"claimFreeYears": int, "claimsLast3Years": bool}` | `pd:Insurance`, geverifieerd maar als **naaste bredere term**: DPV-PD 2.1 kent geen claims- of schadeverledenterm (`pd:InsuranceClaim` en `pd:ClaimsHistory` bestaan niet) |

Bestaande velden worden ook in de constante opgenomen zodat de per-veldselectie compleet is; hun opslag en formulier veranderen niet:

| key | Groep | Opslag (ongewijzigd) | DPV-PD |
|---|---|---|---|
| `housing_ownership` | housing | `pd:HousingOwnership` | `mysolido:housing_ownership` (`pd:HousingOwnership` bestaat niet in DPV-PD 2.1; `pd:HouseOwned` wel, maar dekt huur/koop niet) |
| `housing_type` | housing | `mysolido:housingType` | `mysolido:housing_type` |
| `region` | housing | `pd:Location` | `pd:Location`, geverifieerd |
| `household_size` | household | `pd:HouseholdSize` | `mysolido:household_size` (`pd:HouseholdSize` bestaat niet) |
| `children` (lijst) | household | `pd:FamilyStructure.children` | `pd:FamilyStructure`, geverifieerd |
| `vehicle_fuel`, `vehicle_year` | vehicle | `pd:Vehicle[0].fuel` / `.yearBuilt` | `pd:Vehicle`, geverifieerd |
| `insurances` (lijst) | insurance | `pd:Insurance` | `pd:Insurance`, geverifieerd |
| `work_sector`, `employment_type` | occupation | `pd:Occupation.sector` / `.employmentType` | `pd:Professional`, geverifieerd (`pd:Occupation` bestaat niet) |
| `smoking_status` | health | `pd:HealthData.smokingStatus` | `pd:Health`, geverifieerd (`pd:HealthData` bestaat niet) |

De huisartspraktijk (`gpPractice`) blijft bewust buiten de constante, zoals `extract_profile_groups()` die nu ook al niet deelt. De JSON-sleutels `pd:HousingOwnership`, `pd:HouseholdSize`, `pd:Occupation` en `pd:HealthData` in `profiel.jsonld` zijn dus geen DPV-PD-termen; ze blijven staan tot een latere migratie (buiten subtaak 2).

## 2. Intentierecord (`mysolido:Intention`, `intenties/<uuid>.jsonld`)

Nieuwe velden naast de bestaande (`@id` `urn:mysolido:intention:<uuid>`, `mysolido:category`, `schema:description`, `mysolido:status`, `schema:dateCreated`, `schema:validThrough`):

```json
"mysolido:sharedAttributes": [
  { "@id": "urn:mysolido:attribute:age_category", "label": "Leeftijdscategorie",
    "value": "35-44", "valueLabel": "35-44", "capturedAt": "2026-09-20T10:15:00+00:00" }
],
"mysolido:purpose": { "@id": "urn:mysolido:purpose:quote_calculation", "label": "Offerteberekening", "dpv": "dpv:ServiceProvision" },
"mysolido:noOnwardTransfer": true,
"mysolido:offerMode": "open",
"mysolido:targetedParty": { "name": "Verzekeraar X" }
```

- `sharedAttributes` is een **snapshot**: `value` is de ruwe opgeslagen waarde op het moment van aanmaken (string, getal, boolean, object bij composite, lijst bij list), `valueLabel` de leesbare weergave, `capturedAt` het tijdstip (ISO-8601, UTC). De detailpagina toont het snapshot, niet het actuele profiel. Alleen attributen die op dat moment gevuld waren komen in de lijst.
- `purpose` komt uit de constante `INTENTION_PURPOSES`; voor nu één code `quote_calculation` ("Offerteberekening", DPV `dpv:ServiceProvision`, zelfde koppelwijze als `PURPOSE_MAP`).
- `noOnwardTransfer`: `true` betekent doorlevering aan derden niet toegestaan (standaard).
- `offerMode`: `"open"` (iedereen die de voorwaarden accepteert) of `"targeted"`; alleen bij targeted staat `targetedParty` in het record, met nu alleen `name`. Geen gedrag in subtaak 2.
- `mysolido:sharedProfileData` (per groep, met datakopie) wordt in nieuwe records niet meer geschreven. Oude records met dat veld blijven leesbaar: de detailpagina valt daarvoor terug op de groepsweergave.

## 3. Namen voor subtaak 3 en 4 (nu vastgelegd, nu niet gebouwd)

| Object | Identifier / bestand | Vorm |
|---|---|---|
| Intentiepolicy | uid `urn:mysolido:policy:intention:<intentie-uuid>`, bestand `intenties/<uuid>.policy.jsonld` | `odrl:Offer`; `assigner` = WebID eigenaar; `target` = de attribuut-urn's uit `sharedAttributes`; `constraint` purpose = `urn:mysolido:purpose:<code>` en `dateTime lteq validThrough`; `prohibition` `distribute` als `noOnwardTransfer` waar is; bij `targeted` een `assignee` `urn:mysolido:party:<hex>` |
| Agreement | uid `urn:mysolido:agreement:<verzoek-uuid>` | `odrl:Agreement`, afgeleid van de Offer, `assignee` = wederpartij |
| Verzoek (`mysolido:ConsentRequest`) | bestaand `verzoeken/<uuid>.jsonld` | nieuwe velden `mysolido:intention` (intentie-`@id`), `mysolido:acceptedPolicy` (policy-uid), `mysolido:acceptedAt` (ISO-8601) |
| Consentrecord (`dpv:ConsentRecord`) | bestaand `urn:mysolido:consent:YYYYMMDD-NNN` | nieuwe velden `mysolido:agreement`, `mysolido:intention`, `mysolido:request`, en `dpv:hasPersonalData` = lijst met dezelfde attribuut-urn's (met `dpv`-term uit `PROFILE_ATTRIBUTES`) |
| Wederpartij | `urn:mysolido:party:<hex>` zoals `consent_new()` nu doet | per verzoek bewaard in het verzoekrecord, zodat Agreement en consentrecord dezelfde partij-id gebruiken |

## 4. Wie schrijft, wie leest

| Veld | Waar het staat | Wie het schrijft | Wie het leest |
|---|---|---|---|
| `PROFILE_ATTRIBUTES`, `INTENTION_PURPOSES` | `app.py` (constanten) | code (subtaak 2) | profielformulier, intentieformulier en -detail (2); policygenerator (3); consentrecord (4); `scripts/seed_demo.py` |
| `pd:AgeRange`, `pd:PostalCode`, `mysolido:claimsHistory` | `profiel/profiel.jsonld` | `profiel_data_save()` (2), `seed_demo.py` | `extract_profile_groups()` en `extract_profile_attributes()` (2) |
| `mysolido:sharedAttributes` | `intenties/<uuid>.jsonld` | `intentie_new()` (2) | `intentie_detail` (2); policygenerator als targets (3); `verzoek_approve()` voor response en consentrecord (4) |
| `mysolido:purpose`, `noOnwardTransfer`, `offerMode`, `targetedParty` | `intenties/<uuid>.jsonld` | `intentie_new()` (2) | detailpagina (2); policygenerator (3); consentrecord (4) |
| `urn:mysolido:policy:intention:<uuid>` | `intenties/<uuid>.policy.jsonld` | policygenerator (3) | verzoekformulier en `verzoek_approve()` (4); Bridge-leesweergave (5) |
| `mysolido:intention`, `acceptedPolicy`, `acceptedAt` | `verzoeken/<uuid>.jsonld` | `verzoek_submit()` (4) | `verzoek_approve()` (4) |
| `mysolido:agreement`, `intention`, `request`, `dpv:hasPersonalData` | `toestemmingen/<id>.jsonld` | `verzoek_approve()` (4) | `consent_detail` (4), Bridge (5) |
