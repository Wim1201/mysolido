# MySolido — Datamodel-notitie MyTerms-demo (subtaak 2, 3 en 4)

| | |
|---|---|
| **Datum** | 20 september 2026 |
| **Status** | Werkafspraak: de namen hieronder zijn leidend voor subtaak 2 (gegevensselectie), 3 (ODRL-policy) en 4 (acceptatie en consentrecord). Subtaak 2 bouwde punt 1 en 2; subtaak 3 (20-09, later op de dag) bouwde de intentiepolicy uit punt 3 en voegde `mysolido:policy` en `targetedParty.@id` toe aan punt 2. Subtaak 4a (20-09, derde sessie) bouwde acceptatie, verzoekvelden en Agreement uit punt 3 en `mysolido:acceptedBy` in punt 2. Het consentrecord (4b) is nog niet gebouwd. |
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
"mysolido:targetedParty": { "@id": "urn:mysolido:party:9f3a1c2b", "name": "Verzekeraar X" },
"mysolido:policy": "urn:mysolido:policy:intention:<uuid>"
```

- `sharedAttributes` is een **snapshot**: `value` is de ruwe opgeslagen waarde op het moment van aanmaken (string, getal, boolean, object bij composite, lijst bij list), `valueLabel` de leesbare weergave, `capturedAt` het tijdstip (ISO-8601, UTC). De detailpagina toont het snapshot, niet het actuele profiel. Alleen attributen die op dat moment gevuld waren komen in de lijst.
- `purpose` komt uit de constante `INTENTION_PURPOSES`; voor nu één code `quote_calculation` ("Offerteberekening", DPV `dpv:ServiceProvision`, zelfde koppelwijze als `PURPOSE_MAP`).
- `noOnwardTransfer`: `true` betekent doorlevering aan derden niet toegestaan (standaard).
- `offerMode`: `"open"` (iedereen die de voorwaarden accepteert) of `"targeted"`; alleen bij targeted staat `targetedParty` in het record, met `@id` = `urn:mysolido:party:<hex>` (gegenereerd zoals `consent_new()` dat doet, `secrets.token_hex(4)`) en `name`. Dezelfde `@id` is de `assignee` in de Offer en wordt in subtaak 4 hergebruikt voor Agreement en consentrecord.
- `policy`: de uid van de bij deze intentie horende Offer (`urn:mysolido:policy:intention:<uuid>`), expliciete koppeling record → policy. Toegevoegd 20-09 (subtaak 3). Records van vóór subtaak 3 missen dit veld; de detailpagina biedt dan "Voorwaarden opstellen" aan, die de Offer alsnog maakt en het veld zet.
- Een intentie zonder één gevuld, aangevinkt attribuut wordt geweigerd (sinds subtaak 3): een Offer zonder targets is leeg.
- `acceptedBy` (sinds subtaak 4a): lijst van verzoek-`@id`'s (`urn:mysolido:request:<uuid>`) waarvoor een Agreement is gesloten; een open aanbod kan vaker geaccepteerd worden. Een intentie met een niet-lege lijst kan niet meer verwijderd worden, want de Agreement rust erop. Alleen een intentie met status `actief` is te accepteren.
- `mysolido:sharedProfileData` (per groep, met datakopie) wordt in nieuwe records niet meer geschreven. Oude records met dat veld blijven leesbaar: de detailpagina valt daarvoor terug op de groepsweergave.

## 3. Namen voor subtaak 3 en 4 (nu vastgelegd, nu niet gebouwd)

| Object | Identifier / bestand | Vorm |
|---|---|---|
| Intentiepolicy (gebouwd in subtaak 3) | uid `urn:mysolido:policy:intention:<intentie-uuid>`, bestand `intenties/<uuid>.policy.jsonld`, gemaakt door `build_intention_policy(record)` direct na het schrijven van het record in `intentie_new()`; leesroute `GET /intenties/<uuid>/policy.jsonld` (`application/ld+json`, ook in Bridge-modus); herstelroute `POST /intenties/<uuid>/policy/create` voor records zonder bestand | Zelfde JSON-LD-context als de mappolicies (ODRL-context plus `dpv`, aangevuld met `rdfs` voor het partijlabel). `@type` `Offer`, `profile` ODRL core, `assigner` = `WEBID` uit `.env`. Eén `permission`: `action` `use`, `target` = lijst attribuut-urn's in de volgorde van `sharedAttributes`, twee `constraint`s: `purpose eq {"@id": <purpose-@id>}` en `dateTime lteq {"@type": "xsd:dateTime", "@value": <schema:validThrough>}`. Bij `noOnwardTransfer` true één `prohibition` met dezelfde targets en `action` `["distribute", "transfer"]`; bij false geen prohibition. Bij `offerMode` open geen `assignee`; bij targeted `assignee` `{"@id": <targetedParty.@id>, "rdfs:label": <naam>}` op permission en prohibition. Alleen standaard ODRL 2.2-termen, korte namen binnen de ODRL-context zoals de mappolicies. Geen eigen status: "aangeboden" volgt uit `mysolido:status` van de intentie; de Offer wordt niet herschreven bij activeren, intrekken of verlopen. Samenvatting via `intention_policy_summary_nl(policy, record)`: "<Wie> mag <labels> gebruiken, uitsluitend voor <doel>, tot <dd-mm-jjjj>, en mag ze niet doorleveren." |
| Agreement (gebouwd in 4a) | uid `urn:mysolido:agreement:<verzoek-uuid>`, bestand `verzoeken/<verzoek-uuid>.agreement.jsonld`, geschreven door `conclude_agreement(request_record, intention_record)` via `build_agreement(offer, request, party)`; leesroute `GET /verzoeken/<uuid>/agreement.jsonld` (eigenaarslogin, `application/ld+json`, ook in Bridge-modus) | Zelfde context als de Offer. `@type` `Agreement`, `profile` ODRL core, `assigner` = WebID; `permission` en `prohibition` letterlijk gekopieerd uit de Offer met op elke regel `assignee` = de partij `{"@id": urn:mysolido:party:<hex>, "rdfs:label": naam}`; plus `mysolido:offer` (Offer-uid), `mysolido:request` (verzoek-`@id`), `mysolido:acceptedAt` en `mysolido:offerHash` (`sha256:<hex>` van het Offer-bestand op het moment van acceptatie). Geen eigen status. Sluitmoment: bij `offerMode` open direct bij acceptatie door de wederpartij; bij targeted pas na bevestiging door de eigenaar in `verzoek_approve()`. Eén functie, twee aanroepplekken. In 4b komt het consentrecord als één toevoeging in `conclude_agreement()` |
| Verzoek (`mysolido:ConsentRequest`, gebouwd in 4a) | bestaand `verzoeken/<uuid>.jsonld`, aangemaakt door de nieuwe route `GET/POST /verzoek/intentie/<intentie-uuid>` (het generieke `/verzoek` blijft ongewijzigd) | nieuwe velden `mysolido:intention` (intentie-`@id`), `mysolido:acceptedPolicy` (policy-uid), `mysolido:acceptedAt` (ISO-8601 UTC, hele seconden), `mysolido:acceptedPolicyHash` (`sha256:<hex>`), `mysolido:party` `{"@id", "rdfs:label" (naam), "mysolido:organisation", "mysolido:contact" (e-mail)}` en na het sluiten `mysolido:agreement` (Agreement-uid). Partij-id: bij open nieuw via `generate_party_id()`, bij targeted = `intention['mysolido:targetedParty']['@id']` met de zelfverklaarde naam ernaast. Status: `geaccepteerd` (open: direct; targeted: na bevestiging) of `wacht-op-bevestiging` (targeted, tot `verzoek_approve()`); de bestaande statussen `nieuw`/`goedgekeurd`/`afgewezen` blijven voor het generieke formulier. `responseLink` en `validUntil` (= `schema:validThrough` van de intentie) worden bij het sluiten gezet; `<uuid>_response.json` bevat uitsluitend de `sharedAttributes` van de intentie (`@id`, `label`, `valueLabel`). Identiteit van de wederpartij is zelfverklaard (geen verificatie) |
| Consentrecord (`dpv:ConsentRecord`) | bestaand `urn:mysolido:consent:YYYYMMDD-NNN` | nieuwe velden `mysolido:agreement`, `mysolido:intention`, `mysolido:request`, en `dpv:hasPersonalData` = lijst met dezelfde attribuut-urn's (met `dpv`-term uit `PROFILE_ATTRIBUTES`) |
| Wederpartij | `urn:mysolido:party:<hex>` zoals `consent_new()` nu doet | per verzoek bewaard als `mysolido:party` in het verzoekrecord (4a), zodat Agreement (`assignee`) en consentrecord (4b, `dpv:hasDataController`) dezelfde partij-id gebruiken |

## 4. Wie schrijft, wie leest

| Veld | Waar het staat | Wie het schrijft | Wie het leest |
|---|---|---|---|
| `PROFILE_ATTRIBUTES`, `INTENTION_PURPOSES` | `app.py` (constanten) | code (subtaak 2) | profielformulier, intentieformulier en -detail (2); policygenerator (3); consentrecord (4); `scripts/seed_demo.py` |
| `pd:AgeRange`, `pd:PostalCode`, `mysolido:claimsHistory` | `profiel/profiel.jsonld` | `profiel_data_save()` (2), `seed_demo.py` | `extract_profile_groups()` en `extract_profile_attributes()` (2) |
| `mysolido:sharedAttributes` | `intenties/<uuid>.jsonld` | `intentie_new()` (2) | `intentie_detail` (2); policygenerator als targets (3); `verzoek_approve()` voor response en consentrecord (4) |
| `mysolido:purpose`, `noOnwardTransfer`, `offerMode`, `targetedParty` | `intenties/<uuid>.jsonld` | `intentie_new()` (2) | detailpagina (2); policygenerator (3); consentrecord (4) |
| `urn:mysolido:policy:intention:<uuid>` (Offer) | `intenties/<uuid>.policy.jsonld` | `intentie_new()` via `build_intention_policy()` en de herstelroute `intentie_policy_create()` (3) | `intentie_detail` en `GET /intenties/<uuid>/policy.jsonld` (3); verzoekformulier en `verzoek_approve()` (4); Bridge-leesweergave (5) |
| `mysolido:policy`, `mysolido:targetedParty.@id` | `intenties/<uuid>.jsonld` | `intentie_new()` (3) | detailpagina (3); `verzoek_approve()` voor Agreement-`assignee` en consentrecord (4) |
| `mysolido:intention`, `acceptedPolicy`, `acceptedAt`, `acceptedPolicyHash`, `party` | `verzoeken/<uuid>.jsonld` | route `/verzoek/intentie/<uuid>` (4a) | `conclude_agreement()`, `verzoek_detail_owner`, `verzoek_response` (4a); consentrecord (4b) |
| `mysolido:agreement`, `responseLink`, `validUntil`, status `geaccepteerd` | `verzoeken/<uuid>.jsonld` | `conclude_agreement()` (4a), aangeroepen door de route (open) of `verzoek_approve()` (targeted) | statuspagina, responspagina, eigenaarsdetail (4a); intrekken (4b) |
| `urn:mysolido:agreement:<uuid>` (Agreement) | `verzoeken/<uuid>.agreement.jsonld` | `conclude_agreement()` via `build_agreement()` (4a) | `GET /verzoeken/<uuid>/agreement.jsonld`, eigenaarsdetail, responspagina (4a); consentrecord (4b); Bridge (5) |
| `<uuid>_response.json` (alleen `sharedAttributes`) | `verzoeken/` | `conclude_agreement()` (4a) | `verzoek_response` (4a) |
| `mysolido:acceptedBy` | `intenties/<uuid>.jsonld` | `conclude_agreement()` (4a) | `intentie_detail` ("Geaccepteerd door"), `intentie_delete` (blokkade) (4a); intrekken (4b) |
| `mysolido:agreement`, `intention`, `request`, `dpv:hasPersonalData` | `toestemmingen/<id>.jsonld` | `verzoek_approve()` (4) | `consent_detail` (4), Bridge (5) |
