# MySolido — Verslag MyTerms-demo, subtaak 4b: consentrecord (ISO/IEC TS 27560) en intrekken

| | |
|---|---|
| **Datum** | 20 september 2026 (vierde sessie van die dag) |
| **Softwareversie** | branch `myterms-demo`, uitgangspunt commit `e8a95ab` ("MyTerms-demo subtaak 4a: acceptatie van de Offer, Agreement en response beperkt tot de vier velden"). Alle wijzigingen hieronder zijn **niet gecommit** |
| **Omgeving** | Windows 10, hoofdcheckout `C:\Users\Wim\mysolido`; CSS 7.2.0 draaide al op `http://127.0.0.1:3000` (niet herstart); Flask voor de tests gestart met `python app.py` op `127.0.0.1:5000` (twee keer, zie §1 punt 7) en daarna gestopt; Python 3.13.2. DPV-controle tegen de DPV-27560-gids (`w3c-cg.github.io/dpv/guides/consent-27560.html`), DPV 2.1, DPV-LOC 2.1 en DPV-EU-GDPR 2.1 |
| **Gewijzigd** | `app.py`, `translations.py`, `templates/consent_detail.html`, `templates/consent_list.html`, `templates/intentie_detail.html`, `templates/verzoek_detail.html`, `templates/verzoek_intentie.html`, `templates/verzoek_response.html`, `templates/verzoek_status.html`, `templates/verzoeken.html`, `scripts/regressietest.py`, `scripts/regressietest.md`, `docs/mysolido_notitie_datamodel-myterms_20-09-2026.md` |
| **Aangemaakt** | dit verslag |
| **Pod na deze sessie** | Demodata ongewijzigd; `intenties/` bevat jouw `a0ac025c` (ingetrokken, met de acceptatie `9e44614f` van "Jan Jansen / groenteboer" inclusief Agreement en response, zonder consentrecord, zoals besloten) en `fb9189cb` (concept); `verzoeken/` bevat die ene acceptatie en `.policy.jsonld`; `toestemmingen/` bestaat nu als lege map (door de tests aangemaakt). Alle testrecords en het voorbeeld uit §3 zijn opgeruimd |
| **Vervolg op** | `docs/mysolido_verslag_myterms-demo-subtaak4a_20-09-2026.md`; regelnummers "oud" verwijzen naar `e8a95ab`, "nieuw" naar de werkboom van dit verslag |
| **Niet gedaan** | geen git-wijzigingen, geen ClickUp, geen Bridge-run, geen consentrecord voor generieke goedkeuringen, geen wijziging aan `build_policy()`, `build_intention_policy()`, `build_agreement()`, het generieke `/verzoek`-formulier, `REQUEST_CATEGORIES`, `APPROVAL_VALIDITY`, `consent_new()` (behalve de statusterm), `consent_form.html`, README, trustpagina, profiel, seed, CSS, startscripts, `.env` |

---

## 1. Correcties op notitie, verslagen, inventarisatie §4 en deze opdracht

1. **`pod_write()` schreef tekst in cp1252, alle lezers lezen UTF-8.** `open(full_path, 'w')` zonder `encoding` (oud `app.py:172`) gebruikt op Windows de systeemcodering. Het eerste consentrecord had een gedachtestreepje in `dct:title` en was daarna onleesbaar (`UnicodeDecodeError`). Dezelfde latente fout raakte elk record met een niet-ASCII-teken: een intentie met "één" in de omschrijving zou het overzicht *Mijn intenties* met een 500 laten stoppen, want `load_all_intentions()` vangt alleen `JSONDecodeError`/`IOError`. Hersteld met één regel (`app.py:172-174`, `encoding='utf-8'` voor tekst). Bestaande bestanden zijn niet herschreven; in de huidige Pod staan geen bestanden met niet-ASCII-tekens, dus er is nu niets stuk. Wie oudere Pods heeft met accenten in intenties of verzoeken, ziet die records pas na herschrijven correct.

2. **`dpv:hasExpiry` en `dpv:hasExpiryTime` bestaan niet in DPV 2.1.** Het zijn DPV 1-termen die `consent_new()` sinds v1.2 schrijft. De opdracht vroeg `retention_period` als `dpv:hasExpiry`; volgens de regel "alleen geverifieerde termen" is de gids-mapping gevolgd: `dpv:hasStorageCondition` met `dpv:StorageDuration` en `dpv:hasDuration` (`dpv:TemporalDuration`, allemaal in 2.1), en omdat DPV geen geverifieerde eigenschap voor de concrete einddatum heeft: `mysolido:validUntil`, `mysolido:days`, `mysolido:iso8601`. De statusafleiding (`consent_expiry_time()`) leest beide vormen, zodat handmatige records met `hasExpiry` "Verlopen" blijven tonen (getest met een fixture).

3. **`dpv:RightToWithdrawConsent` is niet in DPV 2.1 gevonden.** De opdracht zei "zoals nu"; volgens dezelfde regel schrijft het nieuwe record `dpv:hasRight: "eu-gdpr:A7-3"` (DPV-EU-GDPR 2.1: "A7-3 Right to Withdraw Consent", geverifieerd). `consent_new()` blijft `dpv:RightToWithdrawConsent` schrijven (niet aangeraakt).

4. **`dpv:isImplementedByEntity`** staat in de DPV-27560-gids als mapping voor `entity_id`; mijn letterlijke zoekactie in de DPV 2.1-tekst vond de term niet terug (wel `isImplementedUsingTechnology`). Gebruikt op gezag van de gids; als je het strikt wilt: `mysolido:entity`. Genoteerd in de tabel in §4.

5. **`event_type` heeft geen eigen veld.** De gids beeldt `event_type` af op `dpv:hasLegalBasis` met een consenttype; `dpv:ExplicitlyExpressedConsent` (2.1) dekt dus `lawful_basis` én `event_type`. `mysolido:events` volgt de vorm uit de opdracht (`"@type": "given"|"withdrawn"`); de gids zelf gebruikt `dct:date` per statuswijziging. `dct:identifier` (gids: `record_id`) is naast `@id` toegevoegd.

6. **Het acceptatieblok van 4a ruimde zijn consentrecords niet op.** Sinds `conclude_agreement()` een record schrijft, liet de fase "Acceptatie en Agreement" per run twee records achter (`20260920-001/002` na de eerste demo-run; handmatig verwijderd). Opruiming uitgebreid (`regressietest.py:1580-1592`).

7. **De verzoeklimiet breekt twee runs achter elkaar.** `is_rate_limited()` (oud `4359`) staat per IP tien POSTs per uur toe op `/verzoek` en `/verzoek/intentie/<uuid>`, geteld in het geheugen van het Flask-proces. De demo-fase en de volledige run doen samen achttien van zulke POSTs; de eerste volledige run had daardoor één rode regel ("gericht: acceptatie geregistreerd — status 302") en het voorbeeld voor dit verslag mislukte. Na herstart van Flask: alles groen. Niet aan de limiet gesleuteld (verzoekcode buiten de opdracht); wel een waarschuwing in `regressietest.md`. Voor de demo is tien acceptaties per uur ruim.

8. **Partijlabel.** Nieuwe acceptaties krijgen `rdfs:label` = organisatie (of naam als die ontbreekt) en `mysolido:contactName` = naam, in verzoek, Agreement, consentrecord en zin ("Verzekeraar X BV mag …"). Vier verwachtingen in de 4a-testfase aangepast (`regressietest.py:1466-1468`, `1490`, `1509`, `1523`). Jouw bestaande acceptatie van Jan Jansen houdt het oude label; de intentiepagina en het eigenaarsdetail tonen bij oude records naam en organisatie zoals voorheen.

9. **Bestandsopmaak na intrekken.** `consent_withdraw()` schrijft, zoals voorheen, met `indent=4`; `build_consent_record()` schrijft via `pod_write` met `indent=2`. Na intrekken is het bestand dus anders ingesprongen (zie §3). Inhoudelijk gelijk; niet gelijkgetrokken om `consent_withdraw` niet verder te raken.

10. **Regelnummers.** De verwijzingen in de opdracht klopten voor `e8a95ab`. Nieuw: acceptatieblok `2643-2953` (met `build_consent_record` op `2791`), consentmodule `2954-3339`, `count_new_requests` `4401`, `verzoek_status` `4555`, `verzoek_response` `4587`, `verzoek_detail_owner` `4672`, `verzoek_approve` `4733` (vervangen comment `4797-4801`), `_acceptance_party` `4879`.

11. **Inventarisatie §4 klopte** op alle punten; twee toevoegingen: het record van `consent_new()` gebruikt naast de foute statustermen ook DPV 1-eigenschappen (`hasExpiry`, `hasExpiryTime`, `hasPersonalDataCategory`) die in 2.1 niet meer bestaan (punt 2), en `event_time` heeft in de gids geen eigen eigenschap maar loopt via `dct:date`.

---

## 2. Per bestand: wat en waarom

### `docs/mysolido_notitie_datamodel-myterms_20-09-2026.md`
Kop: statusregel. §3: rij Consentrecord volledig uitgeschreven (velden per 27560-deel, welke termen geverifieerd zijn, welke `mysolido:`-termen en waarom, intrekgedrag); rij Verzoek (partijlabel, `mysolido:consent`, status `ingetrokken`, `withdrawnAt`, zin over ongeverifieerde identiteit); rij Agreement (partijlabel). §4: rij consentrecord vervangen, rij voor `mysolido:consent`/`ingetrokken` toegevoegd.

### `app.py` (5033 → 5258 regels)
- **`pod_write()`** (`172-174`): UTF-8 voor tekst (§1 punt 1).
- **Acceptatieblok** (`2643-2953`): constante `REQUEST_STATUS_WITHDRAWN` (`2655`); `CONSENT_RECORD_CONTEXT`, `CONSENT_RECORD_SCHEMA(_VERSION)` (`2768-2779`); `_days_between()` (`2782`); **`build_consent_record(request_record, intention_record, agreement)`** (`2791-2878`, de vier 27560-delen als commentaarblokken); `write_consent_record()` (`2880`); in `conclude_agreement()` de aanroep op de plek van het 4b-haakje, `mysolido:consent` in het verzoek en de logregel `consent_create` (`2912-2915`, `2927-2928`); `accepted_requests_for()` levert `contact_name`, `consent`, `withdrawn`, `withdrawn_at` (`2940-2950`).
- **Consentmodule** (`2954-3339`): normalisatie van oude statuswaarden in `load_all_consents()` (`2996-2998`); constanten `CONSENT_STATUS_GIVEN/WITHDRAWN/EXPIRED` en `normalize_consent_status()`, `consent_expiry_time()`, `consent_is_expired()`, `get_consent_status_display()` met `term` (`3010-3059`); `consent_list()` toont `rdfs:label`/`dct:title` en de intentiecategorie (`3104-3116`); `consent_new()` schrijft `dpv:ConsentGiven` (`3171`, enige wijziging daar); `consent_detail()` normaliseert en geeft `links` en `expiry_date` door (`3222-3236`); **`consent_withdraw()`** (`3263-3286`): `dpv:ConsentWithdrawn`, event `withdrawn` door WEBID (alleen bij records met events of `dct:conformsTo`), `dct:modified`, gekoppeld verzoek op `ingetrokken` met `withdrawnAt`.
- **`count_new_requests()`** (`4405-4406`): telt `wacht-op-bevestiging` mee.
- **`verzoek_status()`** (`4581`) en **`verzoek_response()`** (`4596-4599`): status `ingetrokken` → intrekdatum, geen gegevens.
- **`verzoek_detail_owner()`** (`4718-4721`): gedeelde waarden uit de response, consent-id, intrekdatum.
- **`verzoek_approve()`** (`4797-4801`): dode comment vervangen door commentaar plus logregel `request_approve_generic`; het groepspad zelf ongewijzigd.
- **`_acceptance_party()`** (`4885-4888`): label = organisatie of naam, `contactName`.

### Templates
- `consent_detail.html` (`22-101`): voor records met `dct:conformsTo` een 27560-tabel (id, conform, wederpartij met contactpersoon, doel met dpv-term, gedeelde gegevens met waarde en pd-term, geldigheid met dagen, doorlevering, status-term, gebeurtenissen, rechtsgrond en recht, jurisdictie, koppelingen als links naar intentie, verzoek en Agreement-JSON, plus policy-uid en hash, created/modified); de oude tabel blijft voor handmatige records; de ruwe JSON blijft; op de Bridge geen verzoeklink (die route is daar 403).
- `consent_list.html` (`29`): intentiecategorie.
- `verzoek_status.html` (`21-26`) en `verzoek_response.html` (`13-19`): "Toestemming ingetrokken op <dd-mm-jjjj>" zonder gegevens.
- `verzoek_detail.html`: badge `ingetrokken` (`41`); in de acceptatiekaart "Gevraagde gegevens" (labels), "Gedeelde waarden" (uit de response) en de link "Bekijk consentrecord" met intrekbadge (`128-151`); het generieke blok "Gevraagde gegevens" alleen nog voor verzoeken zonder intentie (`73-84`); partijregel toont contactpersoon in plaats van organisatie tussen haakjes (`101`).
- `verzoek_intentie.html`: inleiding zonder "Na acceptatie ontvangt u de waarden" bij een niet-actieve intentie (`48`); zin over ongeverifieerde identiteit boven het vinkje (`100`).
- `intentie_detail.html`: "(toestemming ingetrokken op <datum>)" per acceptatie en contactpersoon in plaats van organisatie (`123-124`); knop **Aanbod intrekken** met nieuwe bevestigingstekst (`186-190`).
- `verzoeken.html` (`27`): badge `ingetrokken`.

### `translations.py`
NL `415-449` en EN `1139-1173`: intrekteksten voor wederpartij en eigenaar, consentrecord-link, "Gedeelde waarden", identiteitszin, inactieve inleiding, "Aanbod intrekken" met uitleg, "(toestemming ingetrokken op …)", intentiecategorie in de lijst en alle labels van de 27560-weergave.

### `scripts/regressietest.py` (1667 → 1932 regels)
- Fase "Toestemmingen en consentrequests": verwacht `dpv:ConsentGiven` en `dpv:ConsentWithdrawn` (`706`, `723`).
- Fase "Acceptatie en Agreement": partijlabel = organisatie (`1466-1468`, `1490`, `1509`, `1523`); opruiming van consentrecords (`1580-1592`).
- Nieuwe fase **`phase_consent_record`** (`1607-1880`, 30 checks): alles uit de opdracht (kop, verwerking, gebeurtenis, koppelingen, lijst en detail, eigenaarsdetail, intrekken met alle gevolgen, Agreement ongewijzigd, gericht aanbod met label = naam, twee fixtures voor oude statusterm en verstreken `hasExpiry`, opruimen inclusief consentrecords en fixtures).
- `--phase demo` (`1891`) en de volledige run (`1907`) nemen de fase mee.

### `scripts/regressietest.md`
Rij 13f (`69`); paragraaf `--phase demo` noemt 13a t/m 13f en de verzoeklimiet (`93-101`).

---

## 3. Voorbeeld: één consentrecord vóór en ná intrekken

Testintentie (open aanbod, autoverzekering, vier attributen, doorleververbod, 2 weken), geactiveerd en geaccepteerd door "Jan Jansen" namens "Verzekeraar X BV"; daarna ingetrokken via *Toestemmingen → Intrekken*. Alles is na afloop opgeruimd; jouw intenties zijn niet gebruikt.

**`toestemmingen/20260920-001.jsonld` direct na acceptatie:**

```json
{
  "@context": {
    "dpv": "https://w3id.org/dpv#",
    "pd": "https://w3id.org/dpv/pd#",
    "loc": "https://w3id.org/dpv/loc#",
    "eu-gdpr": "https://w3id.org/dpv/legal/eu/gdpr#",
    "dct": "http://purl.org/dc/terms/",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
    "mysolido": "https://mysolido.com/vocab#"
  },
  "@type": "dpv:ConsentRecord",
  "@id": "urn:mysolido:consent:20260920-001",
  "dct:conformsTo": "ISO/IEC TS 27560:2023",
  "mysolido:recordSchemaVersion": "1.0",
  "dct:identifier": "20260920-001",
  "dct:title": "Autoverzekering — Verzekeraar X BV",
  "dct:description": "Verzekeraar X BV mag leeftijdscategorie, postcodegebied, voertuigtype en schadeverleden gebruiken, uitsluitend voor offerteberekening, tot 04-10-2026, en mag ze niet doorleveren.",
  "dct:created": "2026-09-20T13:04:11+00:00",
  "dct:modified": "2026-09-20T13:04:11+00:00",
  "dpv:hasDataSubject": {
    "@id": "http://127.0.0.1:3000/mysolido/profile/card#me",
    "@type": "dpv:DataSubject"
  },
  "dpv:hasPurpose": {
    "@id": "urn:mysolido:purpose:quote_calculation",
    "@type": "dpv:ServiceProvision",
    "rdfs:label": "Offerteberekening"
  },
  "dpv:hasLegalBasis": "dpv:ExplicitlyExpressedConsent",
  "dpv:hasPersonalData": [
    {
      "@id": "urn:mysolido:attribute:age_category",
      "@type": "pd:AgeRange",
      "rdfs:label": "Leeftijdscategorie",
      "mysolido:value": "35-44"
    },
    {
      "@id": "urn:mysolido:attribute:postal_area",
      "@type": "pd:PostalCode",
      "rdfs:label": "Postcodegebied (4 cijfers)",
      "mysolido:value": "5611"
    },
    {
      "@id": "urn:mysolido:attribute:vehicle_type",
      "@type": "pd:Vehicle",
      "rdfs:label": "Voertuigtype",
      "mysolido:value": "Auto"
    },
    {
      "@id": "urn:mysolido:attribute:claims_history",
      "@type": "pd:Insurance",
      "rdfs:label": "Schadeverleden",
      "mysolido:value": "Schadevrije jaren: 5, Schade geclaimd in de laatste 3 jaar: nee"
    }
  ],
  "dpv:hasDataController": {
    "@id": "urn:mysolido:party:1e0b34c0",
    "@type": "dpv:DataController",
    "rdfs:label": "Verzekeraar X BV",
    "dct:title": "Verzekeraar X BV",
    "mysolido:contactName": "Jan Jansen",
    "mysolido:contact": "offerte@verzekeraar-x.test"
  },
  "dpv:hasStorageCondition": {
    "@type": "dpv:StorageDuration",
    "dpv:hasDuration": {
      "@type": "dpv:TemporalDuration",
      "mysolido:days": 14,
      "mysolido:iso8601": "P14D"
    },
    "mysolido:validUntil": "2026-10-04T13:04:11+00:00"
  },
  "dpv:hasRecipient": [],
  "mysolido:onwardTransfer": "prohibited",
  "dpv:hasJurisdiction": {
    "@id": "loc:NL"
  },
  "dpv:hasConsentStatus": "dpv:ConsentGiven",
  "mysolido:events": [
    {
      "@type": "given",
      "at": "2026-09-20T13:04:11+00:00",
      "by": "urn:mysolido:party:1e0b34c0"
    }
  ],
  "dpv:isImplementedByEntity": {
    "@id": "http://127.0.0.1:3000/mysolido/profile/card#me"
  },
  "mysolido:agreement": "urn:mysolido:agreement:2a2e3846-3552-4bb4-82e5-11efd9f48344",
  "mysolido:intention": "urn:mysolido:intention:b0d5764c-8cce-4d70-8eb9-e83d4122beb4",
  "mysolido:request": "urn:mysolido:request:2a2e3846-3552-4bb4-82e5-11efd9f48344",
  "mysolido:acceptedPolicy": "urn:mysolido:policy:intention:b0d5764c-8cce-4d70-8eb9-e83d4122beb4",
  "mysolido:offerHash": "sha256:ef75a0cc8915bb7248a2558582a1e0e45e8e9f8d7396bf0f17026940077336a2",
  "mysolido:intentionCategoryLabel": "Autoverzekering",
  "dpv:hasRight": "eu-gdpr:A7-3",
  "mysolido:onwardTransferProhibition": "urn:mysolido:agreement:2a2e3846-3552-4bb4-82e5-11efd9f48344"
}
```

**Hetzelfde record ná intrekken** (alleen de gewijzigde velden; de rest is letterlijk gelijk, het bestand is door `consent_withdraw()` met vier spaties ingesprongen):

```json
{
    "dct:modified": "2026-09-20T13:04:12+00:00",
    "dpv:hasConsentStatus": "dpv:ConsentWithdrawn",
    "mysolido:events": [
        {
            "@type": "given",
            "at": "2026-09-20T13:04:11+00:00",
            "by": "urn:mysolido:party:1e0b34c0"
        },
        {
            "@type": "withdrawn",
            "at": "2026-09-20T13:04:12+00:00",
            "by": "http://127.0.0.1:3000/mysolido/profile/card#me"
        }
    ]
}
```

Het gekoppelde verzoek kreeg `"mysolido:status": "ingetrokken"`, `"mysolido:withdrawnAt": "2026-09-20T13:04:12+00:00"` en had al `"mysolido:consent": "urn:mysolido:consent:20260920-001"`. De Agreement `2a2e3846-….agreement.jsonld` is niet gewijzigd.

**Scherm van de wederpartij ná intrekken** (`GET /verzoek/response/<token>`, als tekst; de statuspagina toont dezelfde tekst met de badge "Toestemming ingetrokken"):

```
🚫
Toestemming ingetrokken op 20-09-2026
De eigenaar van de kluis heeft de toestemming ingetrokken. De gegevens zijn niet meer
beschikbaar; de afspraak (Agreement) blijft als bewijs bestaan.
```

Geen van de vier waarden staat nog op de pagina.

---

## 4. Per 27560-veld: welke term en waarom

| 27560-veld | In het record | Bron van de term | Opmerking |
|---|---|---|---|
| schema_version | `dct:conformsTo` `"ISO/IEC TS 27560:2023"`, `mysolido:recordSchemaVersion` `"1.0"` | gids (`dct:conformsTo`); eigen versie `mysolido:` | de gids gebruikt een profiel-IRI (`dpv-27560#record`); hier de norm als tekst |
| record_id | `@id` `urn:mysolido:consent:YYYYMMDD-NNN`, `dct:identifier` | gids (`dct:identifier`) | bestaande id-vorm behouden |
| pii_principal_id | `dpv:hasDataSubject` `{WEBID, dpv:DataSubject}` | gids, DPV 2.1 | tot nu `urn:mysolido:owner` in handmatige records |
| privacy_notice, language | weggelaten | gids (`dpv:hasNotice`, `dct:language`) | optioneel volgens opdracht |
| purpose | `dpv:hasPurpose` `{urn, dpv:ServiceProvision, label}` | DPV 2.1 | `purpose_type` (gids: `skos:broader`) weggelaten |
| lawful_basis | `dpv:hasLegalBasis` `dpv:ExplicitlyExpressedConsent` | DPV 2.1, gids | specifieker dan `dpv:Consent`; `eu-gdpr:A6-1-a-explicit-consent` bestaat ook, niet toegevoegd |
| pii_information | `dpv:hasPersonalData` lijst `{attribuut-urn, pd-term, label, mysolido:value}` | DPV 2.1 (`hasPersonalData`), DPV-PD 2.1 (termen) | urn = identiteit, pd-term = categorie; de waarde is `mysolido:` (geen DPV-eigenschap voor de waarde zelf) |
| pii_controllers | `dpv:hasDataController` `{partij-@id, dpv:DataController, rdfs:label, dct:title, mysolido:contactName, mysolido:contact}` | DPV 2.1, gids | contactvelden `mysolido:` |
| retention_period | `dpv:hasStorageCondition` `{dpv:StorageDuration, dpv:hasDuration {dpv:TemporalDuration, mysolido:days, mysolido:iso8601}, mysolido:validUntil}` | gids, DPV 2.1 | **afwijking** van de opdracht (`dpv:hasExpiry` bestaat niet in 2.1); einddatum en getallen `mysolido:` |
| storage_locations | weggelaten | gids (`dpv:StorageLocation`) | niet gevraagd |
| recipient_third_parties | `dpv:hasRecipient` `[]`, `mysolido:onwardTransfer`, `mysolido:onwardTransferProhibition` (Agreement-uid) | DPV 2.1 (`hasRecipient`); verbod `mysolido:` | DPV heeft geen eigenschap voor "doorlevering verboden"; de prohibition staat in de Agreement |
| jurisdiction | `dpv:hasJurisdiction` `{"@id": "loc:NL"}` | DPV 2.1, DPV-LOC 2.1 | geverifieerd |
| event_time | `mysolido:events` `[{@type given/withdrawn, at, by}]` | vorm uit de opdracht | gids: `dct:date` per statuswijziging; hier één lijst met actor |
| event_type / consent_type | via `dpv:hasLegalBasis` | gids | geen apart veld |
| event_state | `dpv:hasConsentStatus` `dpv:ConsentGiven` / `dpv:ConsentWithdrawn`; `dpv:ConsentExpired` alleen afgeleid | DPV 2.1, gids | de oude `dpv:ConsentStatus*`-waarden worden bij lezen genormaliseerd |
| entity_id | `dpv:isImplementedByEntity` `{WEBID}` | gids | niet teruggevonden in mijn zoekactie in de 2.1-tekst (§1 punt 4) |
| rechten | `dpv:hasRight` `eu-gdpr:A7-3` | DPV 2.1 (`hasRight`), DPV-EU-GDPR 2.1 | **afwijking** van "zoals nu" (`dpv:RightToWithdrawConsent` niet in 2.1) |
| koppelingen | `mysolido:agreement`, `intention`, `request`, `acceptedPolicy`, `offerHash`, `intentionCategoryLabel` | eigen | buiten 27560 |

---

## 5. Wat de claim "conform ISO 27560" nu dekt en wat niet

**Dekt.** Elke toestemming die via een intentie tot stand komt (open aanbod direct, gericht aanbod na bevestiging) krijgt een record met de vier 27560-delen: kop (schema, id, betrokkene), verwerking (doel, rechtsgrond, gegevens met waarden, verwerkingsverantwoordelijke, bewaartermijn, ontvangers, jurisdictie), gebeurtenis (status, tijdstippen met actor, uitvoerende entiteit) en partijen (in betrokkene en verantwoordelijke). Het record is gekoppeld aan intentie, verzoek, Offer (uid + hash) en Agreement, en intrekken is als tweede gebeurtenis vastgelegd met zichtbaar gevolg voor de wederpartij. Het vocabulaire volgt de DPV-27560-gids; waar DPV geen term heeft staat een `mysolido:`-term, expliciet benoemd in §4.

**Dekt niet.**
- Generieke goedkeuringen via het oude `/verzoek`-formulier: bewust geen record (comment en logregel in `verzoek_approve()`). De README-zin "elke toestemming wordt geregistreerd conform ISO 27560" is dus waar voor intentiegebonden toestemmingen en onwaar voor generieke. README en trustpagina zijn niet aangepast; dat is een keuze voor jou.
- Handmatige records via `/consent/new`: nog de oude vorm (DPV 1-eigenschappen, één datacategorie, geen koppelingen); alleen de statusterm is gecorrigeerd. Oude bestanden op schijf houden de oude statuswaarde.
- Optionele 27560-velden `privacy_notice`, `language`, `storage_locations`, `purpose_type` ontbreken.
- Geen machinale validatie tegen een 27560-JSON-schema of het DPV-27560-profiel; `dct:conformsTo` is een tekstclaim.
- Geen handtekening of integriteitsbewijs buiten de sha256-hash van de Offer; de identiteit van de wederpartij is zelfverklaard.
- `dpv:isImplementedByEntity` en de bruikbaarheid van `mysolido:`-termen voor een externe lezer zijn niet met een DPV-validator getoetst.

---

## 6. Uitkomst regressietest

| Run | Opdracht | Resultaat |
|---|---|---|
| 1 | `--phase demo` (eerste keer) | 1 fase brak op de cp1252-fout (§1 punt 1); na de fix en opruimen van twee achtergebleven records: |
| 2 | `--phase demo` (13a t/m 13f) | **109 geslaagd, 0 gefaald**, 2 info, 4 s; de nieuwe fase 30 van 30 groen |
| 3 | volledige run `--scenario U` (zelfde Flask-proces als run 2) | 196 geslaagd, **1 gefaald**: verzoeklimiet van tien per uur bereikt (§1 punt 7) |
| 4 | volledige run `--scenario U` (vers Flask-proces) | **200 geslaagd, 0 gefaald**, 2 niet automatiseerbaar (bekend), 32 info, 10 s. Alle bestaande fasen groen, inclusief "Toestemmingen en consentrequests" met de nieuwe statustermen |

Fasen van run 4: Preflight, Accountcreatie, WebID en credentials, Bestanden en roundtrip, Identifier-normalisatie, WAC/ACL, Deellinks, ODRL-beleid, Toestemmingen en consentrequests, Demodata, Profielvelden, Intentie, Intentiepolicy, Acceptatie en Agreement, **Consentrecord (27560)**, Backup en restore, /debug, Probes 7.2.0, Bridge-sync module, Persistentie aanmaken, Opruimen. Ruwe uitvoer van run 4 en run 2 in de bijlage. Flask-log zonder fouten.

---

## 7. Handmatige controle (niet uitgevoerd, voor jou): de keten van stap 6 en 8

Start Flask (`python app.py`); gebruik voor de wederpartij een privévenster. Jouw intentie `a0ac025c` is ingetrokken en dus niet meer te accepteren; gebruik `fb9189cb` ("allrisk voor twee jaar").

1. **Acceptatie met consentrecord (stap 6).** *Mijn intenties → fb9189cb → Activeren.* In het privévenster `http://127.0.0.1:5000/verzoek/intentie/fb9189cb-7e53-4d80-930d-a2681b1a494a`: onder het formulier staat nu de zin dat de identiteit niet wordt geverifieerd. Accepteer als naam "Jan Jansen", organisatie "Verzekeraar X BV". Verwacht: *Toestemmingen* toont één record **Autoverzekering — Verzekeraar X BV**, status Actief, met "Intentie: Autoverzekering". Open het: kop "Toestemming (ISO/IEC TS 27560)"-tabel met wederpartij en contactpersoon Jan Jansen, doel Offerteberekening, vier gegevens mét waarden en pd-term, geldigheid met "14 dagen vanaf acceptatie", doorlevering "Niet toegestaan (prohibition in de Agreement)", status `dpv:ConsentGiven`, één gebeurtenis "Toestemming gegeven", rechtsgrond `dpv:ExplicitlyExpressedConsent` en recht `eu-gdpr:A7-3`, jurisdictie `loc:NL`, drie koppelingen (intentie, verzoek, Agreement-JSON). Op schijf: `toestemmingen\20260920-001.jsonld`. Het verzoek onder *Verzoeken* linkt met "Bekijk consentrecord" en toont de gedeelde waarden; de zin begint met "Verzekeraar X BV mag …".
2. **De wederpartij ziet de gegevens.** In het privévenster de knop *Gegevens bekijken* (of de statuslink): de vier waarden met de zin en de Agreement-uid.
3. **Toestemming intrekken (stap 8).** *Toestemmingen → Intrekken* op het record. Verwacht: status Ingetrokken, in het detail status `dpv:ConsentWithdrawn` en een tweede gebeurtenis "Toestemming ingetrokken" door je WebID, `dct:modified` bijgewerkt. In het privévenster: responspagina én statuspagina tonen alleen "Toestemming ingetrokken op 20-09-2026", geen waarden meer. *Verzoeken*: badge "Toestemming ingetrokken", in het detail dezelfde badge naast de consentlink. *Mijn intenties → fb9189cb*: onder "Geaccepteerd door" staat "Verzekeraar X BV op 20-09-2026 · Jan Jansen (toestemming ingetrokken op 20-09-2026)". `verzoeken\<uuid>.agreement.jsonld` is ongewijzigd.
4. **Aanbod intrekken, los van de toestemming.** Op dezelfde intentie heet de knop nu **Aanbod intrekken**; de bevestiging legt uit dat lopende afspraken blijven. Klik: status Ingetrokken. In het privévenster laadt het acceptatieformulier nog wel de voorwaarden, maar met de inleiding zonder "Na acceptatie ontvangt u de waarden" en de melding "niet actief (status: ingetrokken)". Het consentrecord en het verzoek veranderen hierdoor niet. Ter vergelijking: maak via *Toestemmingen → Nieuwe toestemming* een handmatig record aan; het toont de oude tabel met status Actief en in de ruwe JSON `dpv:ConsentGiven` (nieuwe term), terwijl het record uit stap 1 de 27560-tabel toont.

---

## 8. Buiten dit verslag

**Bewust niet gedaan.** Geen consentrecord voor generieke goedkeuringen; `consent_new()` en `consent_form.html` alleen de statusterm; geen migratie van oude statuswaarden op schijf (normalisatie bij lezen); geen wijziging aan de verzoeklimiet; geen DPV- of 27560-validator; geen Bridge-run; jouw acceptatie `9e44614f` niet met terugwerkende kracht van een record voorzien; README en trustpagina ongewijzigd (§5). Intrekken van een intentie met `acceptedBy` blijft mogelijk (besluit), en raakt verzoek, response en consentrecord niet: "Aanbod intrekken" en "Toestemming intrekken" zijn nu twee gescheiden handelingen met eigen tekst.

**Tegengekomen, voor subtaak 5 (Bridge).**
- `consent_detail.html` toont op de Bridge de 27560-tabel alleen-lezen; de verzoeklink is daar weggelaten (route 403), de intentielink en de Agreement-link werken na Bridge-login. `toestemmingen/` gaat met `scp -r` mee. Niet gedraaid met `--bridge`.
- De demo van stap 8 op de telefoon: na "Toestemming intrekken" op de pc is één sync nodig; de responspagina op de Bridge toont daarna "Toestemming ingetrokken op …" omdat het verzoekrecord meegaat.

**Tegengekomen, voor de andere lijsten.**
- De cp1252-fout in `pod_write()` (§1 punt 1) gold voor alle Pod-schrijfacties sinds de overstap op het bestandssysteem; ook `sync_bridge`-kopieën van zulke bestanden zouden op de VPS (Linux, UTF-8) onleesbaar zijn geweest. Waard om te noemen in `docs/css-koppelvlakken.md` bij de klasse-C-tabel.
- `consent_withdraw()` en `consent_new()` schrijven met `open(...)` en `indent=4`, de rest via `pod_write` met `indent=2`; en `consent_new()` gebruikt `datetime.utcnow()` met `Z`-notatie waar de rest `+00:00` schrijft. Kandidaat voor de kleine-puntenlijst, samen met de gemengde datumnotatie.
- Handmatige records via `/consent/new` gebruiken DPV 1-eigenschappen (`hasExpiry`, `hasExpiryTime`, `hasPersonalDataCategory`) en `dpv:RightToWithdrawConsent`. Als het formulier blijft, hoort het op dezelfde 27560-bouwer (`build_consent_record()` met een handmatige partij) in plaats van een eigen record.
- De verzoeklimiet (tien per uur per IP, in het geheugen) geldt ook voor het generieke formulier en reset bij herstart; voor een demo met meerdere acceptaties vanaf één laptop is dat de bovengrens.
- `dpv:hasRecipient: []` is een lege lijst; een strikte JSON-LD-verwerker laat een lege waarde weg. De betekenis "geen ontvangers" zit dan alleen in `mysolido:onwardTransfer`.
- `mysolido:value` zet de gedeelde waarden in het consentrecord (bewijs van wat gedeeld is, zoals besloten); daarmee bevat `toestemmingen/` persoonsgegevens, net als `verzoeken/<uuid>_response.json`. Relevant voor de backup-export en de Bridge-sync.

**Vragen die alleen jij kunt beantwoorden.**
1. Akkoord met `dpv:hasStorageCondition` + `mysolido:validUntil` in plaats van het (niet-bestaande) `dpv:hasExpiry`, en met `eu-gdpr:A7-3` in plaats van `dpv:RightToWithdrawConsent`? Beide zijn één regel om terug te draaien.
2. Wil je `dpv:isImplementedByEntity` (gids) houden, of het strikt `mysolido:entity` maken omdat ik het niet in de 2.1-tekst heb teruggevonden?
3. Moet het handmatige formulier `/consent/new` nog bestaan in de demo? Zolang het er is, zijn er twee recordvormen naast elkaar.
4. Moet de README-claim worden aangepast naar "toestemmingen die via een intentie tot stand komen", of verdwijnt het generieke goedkeuringspad vóór de demo?
5. Wil je op de responspagina na intrekken de Agreement-uid nog tonen (nu alleen de zin en de datum), zodat de wederpartij het bewijs kan terugvinden?

---

## Bijlage: ruwe uitvoer

### Run 4: `python scripts/regressietest.py --scenario U` (volledige run, vers Flask-proces)

```
MySolido regressietest 2026-09-20 15:04 -- scenario U, fase all, CSS http://127.0.0.1:3000 (7.2.0), Flask http://127.0.0.1:5000, Pod http://127.0.0.1:3000/mysolido/

== Preflight ==
  [PASS] .env gevonden met CLIENT_ID en CLIENT_SECRET  -- Pod http://127.0.0.1:3000/mysolido/
  [PASS] Pod-map op schijf aanwezig  -- C:\Users\Wim\mysolido\.data\mysolido
  [PASS] CSS antwoordt op poort 3000  -- status 200, X-Powered-By: Community Solid Server
  [INFO] CSS-versie volgens .data/.internal/setup  -- 7.2.0
  [INFO] README van het Pod-template op schijf  -- ['README$.markdown', 'README.acl']
  [PASS] Flask antwoordt op poort 5000  -- status 200
  [INFO] Welkomstscherm op dashboard  -- nee, dashboard getoond
  [PASS] Testmap bestaat nog niet  -- regressietest

== Accountcreatie en test-Pod (CSS account-API) ==
  [PASS] Account-API bereikbaar (/.account/)  -- status 200
  [PASS] controls.account.create aanwezig  -- http://127.0.0.1:3000/.account/account/
  [PASS] Account aanmaken  -- status 200
  [PASS] controls bevatten password.create, account.pod en account.clientCredentials
  [PASS] E-mail/wachtwoord registreren  -- status 200
  [PASS] Test-Pod aanmaken  -- http://127.0.0.1:3000/regressietest-pod-0a9099/
  [PASS] Test-Pod staat op schijf als .data/<podnaam>/  -- C:\Users\Wim\mysolido\.data\regressietest-pod-0a9099
  [PASS] Test-WebID publiek bereikbaar met solid:oidcIssuer  -- http://127.0.0.1:3000/regressietest-pod-0a9099/profile/card#me
  [PASS] Test-Pod-root bereikbaar  -- status 200
  [PASS] Client credentials aanmaken  -- id en secret ontvangen
  [PASS] Testaccount: token via /.oidc/token met webid-claim  -- iss http://127.0.0.1:3000/

== WebID en credentials ==
  [PASS] WebID-document publiek leesbaar  -- status 200
  [PASS] WebID bevat solid:oidcIssuer
  [INFO] WebID bevat pim:storage (7.2.0-changelog)  -- nee
  [PASS] Client credentials uit .env leveren een access token met webid-claim  -- iss http://127.0.0.1:3000/, client_id mysolido-app_c2514575-0de6-4d8a-9814-898fdb936112
  [PASS] Pod-root publiek leesbaar (CSS-pod-template geeft foaf:Agent Read op de root)  -- status 200

== Bestanden en roundtrip Flask <-> CSS ==
  [PASS] Flask: map aanmaken  -- regressietest
  [PASS] Nieuwe map erft eigenaar-ACL: anoniem 401  -- status 401
  [INFO] Bearer-token (client credentials) op beschermde map  -- status 401; css.log: geen melding
  [PASS] Flask: submap aanmaken  -- regressietest/ldp
  [PASS] Flask: submap publiek lees/schrijfbaar via deelfunctie (.acl in map)  -- ldp/.acl
  [PASS] CSS ziet de Flask-map als LDP-container  -- status 200
  [PASS] Flask: bestand uploaden  -- roundtrip.txt
  [PASS] Roundtrip Flask -> CSS: upload via CSS leesbaar  -- status 200
  [PASS] CSS geeft text/plain voor .txt  -- text/plain
  [PASS] CSS: PUT bestand  -- status 201
  [PASS] Roundtrip CSS -> Flask: PUT staat op schijf  -- van-css.txt
  [PASS] Roundtrip CSS -> Flask: bestand in MySolido-listing
  [PASS] CSS: DELETE bestand  -- status 205
  [PASS] Flask: bestand bekijken
  [PASS] Flask: bestand downloaden
  [PASS] Flask: zoeken vindt testbestand
  [PASS] Flask: bestand verplaatsen  -- ldp/sub/verplaats.txt
  [PASS] CSS ziet verplaatst bestand op nieuwe plek  -- status 200
  [PASS] Flask: verwijderen naar prullenbak  -- _trash/
  [PASS] Flask: herstellen uit prullenbak  -- prullenbak.txt
  [PASS] Flask: definitief verwijderen uit prullenbak

== Identifier-normalisatie ==
  [INFO] Normalisatie: upload "Bestand Met Spatie.txt" via Flask  -- op schijf ['Bestand Met Spatie.txt']; CSS GET %20-gecodeerd 200, ongecodeerd 200; listing toont naam: True; listing-URL gecodeerd: True
  [PASS] Normalisatie: Flask opent bestand met spatie
  [INFO] Normalisatie: Flask-map "Map Met Spatie"  -- op schijf ['map-met-spatie/']
  [INFO] Normalisatie: CSS PUT container "map%20via%20css/"  -- PUT 201, GET 200; op schijf ['map via css/']; listing toont "map via css": True
  [INFO] Normalisatie: upload via Flask in map met spatie, GET via CSS  -- status 200
  [PASS] Normalisatie: dubbele extensie via Flask, CSS leest als text/plain  -- text/plain
  [INFO] Normalisatie: CSS PUT "rapport.pdf.txt" als text/plain  -- PUT 201; op schijf ['rapport.pdf.txt']; GET 200 text/plain; listing toont ['rapport.pdf.txt']
  [INFO] Normalisatie: CSS PUT "data.txt.json" als application/json  -- PUT 201; op schijf ['data.txt.json']; GET 200 application/json; listing toont ['data.txt.json']
  [INFO] Normalisatie: CSS PUT "mismatch.txt" als application/json  -- PUT 201; op schijf ['mismatch.txt$.json']; GET 200 application/json; listing toont ['mismatch.txt$.json']
  [INFO] Normalisatie: "HoofdLetters.TXT" via Flask  -- op schijf ['HoofdLetters.TXT']; CSS GET exact 200 text/plain; GET kleine letters 200
  [INFO] Normalisatie: CSS PUT "UPPER.txt"  -- PUT 201; op schijf ['UPPER.txt']; listing toont UPPER.txt: True
  [INFO] Normalisatie: CSS PUT "zonder-extensie" als text/plain  -- PUT 201; op schijf ['zonder-extensie$.txt']; GET 200 text/plain; listing toont ['zonder-extensie$.txt']
  [INFO] Normalisatie: GET met dubbele slash .../ldp//roundtrip.txt  -- status 200
  [INFO] Normalisatie: PUT met dubbele slash .../ldp//dubbel.txt  -- status 201, Location http://127.0.0.1:3000/mysolido/regressietest/ldp/dubbel.txt, op schijf: ['regressietest\\ldp\\dubbel.txt']
  [INFO] Normalisatie: PUT met dubbele slash na Pod-root .../mysolido//regressietest/...  -- status 201, op schijf: ['regressietest\\ldp\\dubbel-root.txt']

== WAC / ACL ==
  [PASS] WAC: bestand zonder eigen ACL is niet publiek  -- status 401
  [PASS] WAC: Flask schrijft .acl met publieke leesregel  -- wac-test.txt.acl
  [PASS] WAC: CSS past de ACL toe (publiek lezen = 200)  -- status 200
  [PASS] WAC: publiek schrijven blijft geweigerd  -- status 401
  [PASS] WAC: intrekken verwijdert .acl
  [PASS] WAC: na intrekken weer 401  -- status 401
  [PASS] WAC: delen met specifieke WebID schrijft acl:agent-regel, anoniem blijft 401
  [SKIP] WAC: positieve toegang met het WebID-token  -- status 401; client-credentials-tokens authenticeren niet op http (verifier eist https)
  [PASS] WAC: intrekken WebID-share verwijdert .acl

== Deellinks ==
  [PASS] Deellink: aanmaken met wachtwoord
  [PASS] Deellink: wachtwoordpagina getoond
  [PASS] Deellink: fout wachtwoord geeft geen bestand
  [PASS] Deellink: juist wachtwoord levert bestand
  [PASS] Deellink: na intrekken 404  -- status 404
  [PASS] Deellink-register niet publiek via CSS  -- status 401

== ODRL-beleid ==
  [PASS] ODRL: policy weggeschreven als .policy.jsonld
  [PASS] ODRL: regel "lezen, niet downloaden" correct opgebouwd
  [PASS] ODRL: policy teruggelezen in Flask
  [PASS] ODRL: .policy.jsonld verborgen in MySolido-listing
  [INFO] ODRL: .policy.jsonld via CSS opvraagbaar  -- status 200, Content-Type application/ld+json
  [INFO] ODRL: .policy.jsonld in ldp:contains van CSS  -- ja

== Toestemmingen en consentrequests ==
  [PASS] Toestemming: record weggeschreven
  [PASS] Toestemming: JSON-LD velden correct  -- 20260920-001
  [PASS] Toestemming: detailpagina leest record terug
  [PASS] Toestemming: record niet publiek via CSS  -- status 401
  [PASS] Toestemming: CSS serveert .jsonld als application/ld+json  -- application/ld+json
  [PASS] Toestemming: intrekken zet status dpv:ConsentWithdrawn
  [PASS] Toestemming: verwijderen
  [PASS] Consentrequest: verzoek via publiek formulier weggeschreven
  [PASS] Consentrequest: JSON-LD velden correct en statustoken in bevestiging  -- 9881342c-21a5-45f1-bf59-d844d7d06bb0
  [PASS] Consentrequest: policy voor verzoeken/ aangemaakt
  [PASS] Consentrequest: publieke statuspagina teruglezen
  [PASS] Consentrequest: eigenaar ziet verzoek
  [PASS] Consentrequest: afwijzen zet status afgewezen
  [PASS] Consentrequest: statuspagina toont afgewezen
  [PASS] Consentrequest: testverzoek opgeruimd

== Demodata (seed_demo.py) ==
  [INFO] Seed: profiel/profiel.jsonld bestond al; seed niet met --force gedraaid  -- C:\Users\Wim\mysolido\.data\mysolido\profiel\profiel.jsonld
  [INFO] Seed: standaardmappen op schijf  -- 20 van 20
  [PASS] Seed: profiel/profiel.jsonld aanwezig
  [PASS] Seed: profiel/.policy.jsonld aanwezig
  [PASS] Seed: tweede run zonder --force weigert (exit 1)
  [PASS] Seed: geweigerde run laat het profiel ongemoeid

== Profielvelden MyTerms-demo ==
  [PASS] Profiel: opslaan schrijft pd:AgeRange, pd:PostalCode en mysolido:claimsHistory
  [PASS] Profiel: bestaande velden blijven werken (pd:Vehicle, pd:Location)
  [PASS] Profiel: formulier leest de drie velden terug
  [PASS] Profiel: ongeldig postcodegebied wordt niet opgeslagen, de rest wel
  [PASS] Profiel: oorspronkelijk profiel teruggezet

== Intentie met per-veldselectie ==
  [PASS] Intentie: formulier toont attributen per veld en de MyTerms-velden
  [PASS] Intentie: record weggeschreven
  [PASS] Intentie: sharedAttributes bevat precies de vier attributen met de profielwaarden
  [PASS] Intentie: elk attribuut heeft label, valueLabel en hetzelfde capturedAt
  [PASS] Intentie: purpose quote_calculation (Offerteberekening, dpv:ServiceProvision)
  [PASS] Intentie: noOnwardTransfer true, offerMode open, geen targetedParty
  [PASS] Intentie: geen mysolido:sharedProfileData meer in nieuwe records
  [PASS] Intentie: geldigheid 2 weken = 14 dagen
  [PASS] Intentie: detailpagina toont snapshot met "Vastgelegd op" en de vier attribuut-urn's
  [PASS] Intentie: detailpagina toont het snapshot, niet het gewijzigde profiel
  [PASS] Intentie: gericht aanbod zonder naam wordt geweigerd
  [PASS] Intentie: gericht aanbod weggeschreven
  [PASS] Intentie: offerMode targeted met targetedParty (@id + name), noOnwardTransfer false zonder vinkje
  [PASS] Intentie: oud record met sharedProfileData blijft leesbaar (groepsweergave)
  [PASS] Intentie: testrecords (en hun policybestanden) opgeruimd

== Intentiepolicy (ODRL-Offer) ==
  [PASS] Intentiepolicy: intentie aangemaakt
  [PASS] Intentiepolicy: intenties/<uuid>.policy.jsonld geschreven  -- 90468803-4a72-487c-a2d3-7fe047f97af0.policy.jsonld
  [PASS] Intentiepolicy: @type Offer, uid, profile en assigner = WEBID
  [PASS] Intentiepolicy: één permission "use" met de vier targets in recordvolgorde
  [PASS] Intentiepolicy: constraint purpose eq urn:mysolido:purpose:quote_calculation
  [PASS] Intentiepolicy: constraint dateTime lteq schema:validThrough (xsd:dateTime)
  [PASS] Intentiepolicy: prohibition distribute + transfer op dezelfde targets (noOnwardTransfer true)
  [PASS] Intentiepolicy: open aanbod heeft geen assignee
  [PASS] Intentiepolicy: record bevat mysolido:policy = uid
  [PASS] Intentiepolicy: detailpagina toont de samenvatting met vier labels, doel en doorleverzin
  [PASS] Intentiepolicy: detailpagina toont de ruwe JSON-LD (uid zichtbaar)
  [PASS] Intentiepolicy: "Vastgelegd op" in dd-mm-jjjj
  [PASS] Intentiepolicy: GET /intenties/<uuid>/policy.jsonld geeft application/ld+json met de Offer  -- application/ld+json
  [PASS] Intentiepolicy: gericht aanbod aangemaakt
  [PASS] Intentiepolicy: assignee = targetedParty.@id met rdfs:label, targets in volgorde, geen prohibition
  [PASS] Intentiepolicy: samenvatting gericht aanbod begint met de partijnaam, zonder doorleverzin
  [PASS] Intentiepolicy: intentie zonder attributen wordt geweigerd met melding
  [PASS] Intentiepolicy: zonder policybestand toont de detailpagina "Voorwaarden opstellen"
  [PASS] Intentiepolicy: POST policy/create maakt de Offer opnieuw aan
  [PASS] Intentiepolicy: policybestand niet in de kluislisting
  [PASS] Intentiepolicy: policybestand niet in zoekresultaten
  [PASS] Intentiepolicy: policybestand niet als intentie in het overzicht
  [PASS] Intentiepolicy: verwijderen van de intentie verwijdert ook de Offer
  [PASS] Intentiepolicy: testrecords en policybestanden opgeruimd

== Acceptatie en Agreement ==
  [PASS] Acceptatie: open intentie aangemaakt
  [PASS] Acceptatie: intentie geactiveerd
  [PASS] Acceptatie: formulier toont samenvattingszin, JSON-LD en vier labels zonder waarden
  [PASS] Acceptatie: zonder vinkje geweigerd, geen verzoek
  [PASS] Acceptatie: verzoekrecord geschreven bij acceptatie
  [PASS] Acceptatie: verzoek bevat intention, acceptedPolicy, acceptedAt (hele seconden), hash en party
  [PASS] Acceptatie: status geaccepteerd, agreement-uid, responseLink en validUntil = validThrough
  [PASS] Acceptatie: Agreement met @type, uid, assigner, assignee op permission én prohibition
  [PASS] Acceptatie: permission en prohibition gelijk aan de Offer (op assignee na)
  [PASS] Acceptatie: Agreement bevat mysolido:offer, request, acceptedAt en offerHash
  [PASS] Acceptatie: response.json bevat precies de vier attributen met label en valueLabel
  [PASS] Acceptatie: responspagina toont zin, Agreement-uid en de vier waarden, niet brandstof of bouwjaar
  [PASS] Acceptatie: statuspagina toont geaccepteerd met link naar de gegevens
  [PASS] Acceptatie: intentierecord heeft acceptedBy met het verzoek
  [PASS] Acceptatie: detailpagina toont "Geaccepteerd door Verzekeraar X"
  [PASS] Acceptatie: verwijderen van een geaccepteerde intentie geblokkeerd
  [PASS] Acceptatie: eigenaarsdetail toont partij, tijdstip, hash en Agreement-link
  [PASS] Acceptatie: GET /verzoeken/<uuid>/agreement.jsonld geeft application/ld+json  -- application/ld+json
  [PASS] Acceptatie: concept-intentie aangemaakt
  [PASS] Acceptatie: concept toont voorwaarden maar geen acceptatieformulier
  [PASS] Acceptatie: POST op concept geweigerd
  [PASS] Acceptatie: gerichte intentie aangemaakt
  [PASS] Acceptatie: gericht aanbod: verzoek geregistreerd
  [PASS] Acceptatie: gericht: status wacht-op-bevestiging, partij-id = targetedParty.@id, nog geen Agreement
  [PASS] Acceptatie: gericht: eigenaarsdetail toont bevestigknop
  [PASS] Acceptatie: gericht: na goedkeuren status geaccepteerd en Agreement met assignee = targetedParty.@id
  [PASS] Acceptatie: gericht: tweede goedkeuring wordt geweigerd (al afgehandeld)
  [PASS] Acceptatie: .agreement.jsonld niet in de kluislisting
  [PASS] Acceptatie: .agreement.jsonld niet in zoekresultaten
  [PASS] Acceptatie: Agreement niet als verzoek in het overzicht; verzoeken tonen labels
  [PASS] Acceptatie: testintenties, verzoeken, Agreements, responses en consentrecords opgeruimd

== Consentrecord (27560) ==
  [PASS] Consentrecord: open intentie aangemaakt
  [PASS] Consentrecord: acceptatie geregistreerd
  [PASS] Consentrecord: verzoek heeft mysolido:consent en toestemmingen/<id>.jsonld bestaat  -- 20260920-001
  [PASS] Consentrecord: kop (dpv:ConsentRecord, dct:conformsTo 27560, schemaversie, identifier, hasDataSubject = WEBID)
  [PASS] Consentrecord: hasPurpose = purpose-urn met dpv:ServiceProvision en label; hasLegalBasis ExplicitlyExpressedConsent
  [PASS] Consentrecord: hasPersonalData precies vier, urn als @id, pd-term als @type, label en waarde uit het snapshot
  [PASS] Consentrecord: hasDataController = partij-@id met organisatie als label, contactpersoon en e-mail
  [PASS] Consentrecord: hasStorageCondition met validUntil = validThrough en 14 dagen
  [PASS] Consentrecord: hasRecipient leeg, onwardTransfer prohibited met verwijzing naar de Agreement, jurisdictie loc:NL
  [PASS] Consentrecord: status dpv:ConsentGiven, één event given op acceptedAt door de partij, isImplementedByEntity = WEBID
  [PASS] Consentrecord: vijf koppelingen (agreement, intention, request, acceptedPolicy, offerHash) en recht eu-gdpr:A7-3
  [PASS] Consentrecord: consentlijst toont het record met partijlabel en intentiecategorie
  [PASS] Consentrecord: detailpagina toont 27560-weergave met vier attributen, waarden, gebeurtenis en koppelingen
  [PASS] Consentrecord: eigenaarsdetail van het verzoek linkt naar het consentrecord en toont de gedeelde waarden
  [PASS] Consentrecord: intrekken zet dpv:ConsentWithdrawn, tweede event withdrawn door WEBID, dct:modified gezet
  [PASS] Consentrecord: gekoppeld verzoek op ingetrokken met withdrawnAt
  [PASS] Consentrecord: responspagina toont "Toestemming ingetrokken op" en geen gegevens meer
  [PASS] Consentrecord: statuspagina toont "Toestemming ingetrokken op" zonder link naar gegevens
  [PASS] Consentrecord: intentiepagina toont "(toestemming ingetrokken op"
  [PASS] Consentrecord: detailpagina toont status ConsentWithdrawn en het withdrawn-event
  [PASS] Consentrecord: Agreement blijft ongewijzigd bestaan na intrekken
  [PASS] Consentrecord: gerichte intentie aangemaakt
  [PASS] Consentrecord: gericht: acceptatie geregistreerd
  [PASS] Consentrecord: gericht: nog geen consentrecord vóór bevestiging
  [PASS] Consentrecord: gericht: na bevestiging consentrecord aanwezig
  [PASS] Consentrecord: gericht: label = naam (geen organisatie), controller = targetedParty.@id, onwardTransfer permitted
  [PASS] Consentrecord: oude statusterm dpv:ConsentStatusGiven leest terug als ConsentGiven / Actief
  [PASS] Consentrecord: verstreken hasExpiry toont Verlopen (afgeleid, niet geschreven)
  [PASS] Consentrecord: lijst toont beide fixtures met genormaliseerde status
  [PASS] Consentrecord: testintenties, verzoeken, Agreements, responses, consentrecords en fixtures opgeruimd

== Backup en restore ==
  [PASS] Backup: zip-export  -- 10280 bytes
  [PASS] Backup: bevat testbestand met juiste inhoud  -- regressietest/ldp/roundtrip.txt
  [INFO] Backup: .policy.jsonld en .acl in zip  -- ja
  [INFO] Backup: .mysolido/share_links.json in zip  -- nee
  [PASS] Restore: bestand uit zip teruggezet en via CSS leesbaar

== Flask /debug (HTTP-laag) ==
  [PASS] Flask /debug: HTTP-lezing van Pod-root via CSS (root is publiek)

== Probes 7.2.0-changelog ==
  [INFO] Probe dubbele slug: twee POSTs met Slug slug-test.txt  -- 201 http://127.0.0.1:3000/mysolido/regressietest/ldp/slug-test.txt | 201 http://127.0.0.1:3000/mysolido/regressietest/ldp/f577f790-caf5-461e-bde5-17a084500e14; op schijf ['slug-test.txt']
  [INFO] Probe Link-header op Pod-root  -- <http://www.w3.org/ns/pim/space#Storage>; rel="type", <http://www.w3.org/ns/ldp#Container>; rel="type", <http://www.w3.org/ns/ldp#BasicContainer>; rel="type", <http://www.w3.org/ns/ldp#Resource>; rel="type", <http://127.0.0.1:3000/mysolido/.meta>; rel="describedby", <http://127.0.0.1:3000/.notificat
  [INFO] Probe storage description  -- http://127.0.0.1:3000/mysolido/.well-known/solid -> status 200
  [INFO] Probe notificaties: GET /.notifications/  -- status 400
  [INFO] Probe webhook-kanaal: GET /.notifications/WebhookChannel2023/  -- status 200

== Bridge-sync module ==
  [PASS] Bridge-sync: module vindt de Pod-map  -- .data\mysolido
  [PASS] Bridge-sync: testmap valt binnen de sync-bron  -- regressietest
  [INFO] Bridge-sync: is_configured()  -- True
  [SKIP] Bridge-sync: daadwerkelijke scp naar de Bridge-VPS  -- extern systeem, bewust niet aangeraakt

== Persistentie: ACL- en policy-map aanmaken ==
  [PASS] Persistentie: submap met eigen .acl (publiek lezen) aangemaakt  -- regressietest/acl-map
  [PASS] Persistentie: CSS volgt de .acl (anoniem 200)  -- status 200
  [PASS] Persistentie: submap met .policy.jsonld (regel "read") aangemaakt  -- regressietest/policy-map
  [PASS] Persistentie: policy-map zonder .acl blijft eigenaar-only (anoniem 401)  -- status 401

== Opruimen ==
  [PASS] Opruimen: publieke share op submap ingetrokken
  [PASS] Opruimen: testmap verwijderd via Flask  -- regressietest
  [PASS] Opruimen: CSS geeft verwijderde submap niet meer terug  -- status 401
  [PASS] Opruimen: _trash/ verwijderd (bestond niet voor de test)
  [PASS] Opruimen: .mysolido/ verwijderd (bestond niet voor de test)
  [INFO] Opruimen: testaccount verwijderen via account-API  -- geen account-URL in controls
  [PASS] Opruimen: test-Pod-map van schijf verwijderd  -- C:\Users\Wim\mysolido\.data\regressietest-pod-0a9099
  [INFO] Opruimen: runtime-bestanden in projectmap (trash.json, shares.json, audit_log.json, notifications.json)  -- blijven staan, vallen onder .gitignore

Resultaat: 200 geslaagd, 0 gefaald, 2 niet automatiseerbaar, 32 info (10s)
```

### Run 2: `python scripts/regressietest.py --phase demo` (13a t/m 13f)

```
MySolido regressietest 2026-09-20 15:02 -- scenario U, fase demo, CSS http://127.0.0.1:3000 (7.2.0), Flask http://127.0.0.1:5000, Pod http://127.0.0.1:3000/mysolido/

== Demodata (seed_demo.py) ==
  [INFO] Seed: profiel/profiel.jsonld bestond al; seed niet met --force gedraaid  -- C:\Users\Wim\mysolido\.data\mysolido\profiel\profiel.jsonld
  [INFO] Seed: standaardmappen op schijf  -- 20 van 20
  [PASS] Seed: profiel/profiel.jsonld aanwezig
  [PASS] Seed: profiel/.policy.jsonld aanwezig
  [PASS] Seed: tweede run zonder --force weigert (exit 1)
  [PASS] Seed: geweigerde run laat het profiel ongemoeid

== Profielvelden MyTerms-demo ==
  [PASS] Profiel: opslaan schrijft pd:AgeRange, pd:PostalCode en mysolido:claimsHistory
  [PASS] Profiel: bestaande velden blijven werken (pd:Vehicle, pd:Location)
  [PASS] Profiel: formulier leest de drie velden terug
  [PASS] Profiel: ongeldig postcodegebied wordt niet opgeslagen, de rest wel
  [PASS] Profiel: oorspronkelijk profiel teruggezet

== Intentie met per-veldselectie ==
  [PASS] Intentie: formulier toont attributen per veld en de MyTerms-velden
  [PASS] Intentie: record weggeschreven
  [PASS] Intentie: sharedAttributes bevat precies de vier attributen met de profielwaarden
  [PASS] Intentie: elk attribuut heeft label, valueLabel en hetzelfde capturedAt
  [PASS] Intentie: purpose quote_calculation (Offerteberekening, dpv:ServiceProvision)
  [PASS] Intentie: noOnwardTransfer true, offerMode open, geen targetedParty
  [PASS] Intentie: geen mysolido:sharedProfileData meer in nieuwe records
  [PASS] Intentie: geldigheid 2 weken = 14 dagen
  [PASS] Intentie: detailpagina toont snapshot met "Vastgelegd op" en de vier attribuut-urn's
  [PASS] Intentie: detailpagina toont het snapshot, niet het gewijzigde profiel
  [PASS] Intentie: gericht aanbod zonder naam wordt geweigerd
  [PASS] Intentie: gericht aanbod weggeschreven
  [PASS] Intentie: offerMode targeted met targetedParty (@id + name), noOnwardTransfer false zonder vinkje
  [PASS] Intentie: oud record met sharedProfileData blijft leesbaar (groepsweergave)
  [PASS] Intentie: testrecords (en hun policybestanden) opgeruimd

== Intentiepolicy (ODRL-Offer) ==
  [PASS] Intentiepolicy: intentie aangemaakt
  [PASS] Intentiepolicy: intenties/<uuid>.policy.jsonld geschreven  -- eedea3ca-1376-4c9e-b3dd-821f9bdf6ee1.policy.jsonld
  [PASS] Intentiepolicy: @type Offer, uid, profile en assigner = WEBID
  [PASS] Intentiepolicy: één permission "use" met de vier targets in recordvolgorde
  [PASS] Intentiepolicy: constraint purpose eq urn:mysolido:purpose:quote_calculation
  [PASS] Intentiepolicy: constraint dateTime lteq schema:validThrough (xsd:dateTime)
  [PASS] Intentiepolicy: prohibition distribute + transfer op dezelfde targets (noOnwardTransfer true)
  [PASS] Intentiepolicy: open aanbod heeft geen assignee
  [PASS] Intentiepolicy: record bevat mysolido:policy = uid
  [PASS] Intentiepolicy: detailpagina toont de samenvatting met vier labels, doel en doorleverzin
  [PASS] Intentiepolicy: detailpagina toont de ruwe JSON-LD (uid zichtbaar)
  [PASS] Intentiepolicy: "Vastgelegd op" in dd-mm-jjjj
  [PASS] Intentiepolicy: GET /intenties/<uuid>/policy.jsonld geeft application/ld+json met de Offer  -- application/ld+json
  [PASS] Intentiepolicy: gericht aanbod aangemaakt
  [PASS] Intentiepolicy: assignee = targetedParty.@id met rdfs:label, targets in volgorde, geen prohibition
  [PASS] Intentiepolicy: samenvatting gericht aanbod begint met de partijnaam, zonder doorleverzin
  [PASS] Intentiepolicy: intentie zonder attributen wordt geweigerd met melding
  [PASS] Intentiepolicy: zonder policybestand toont de detailpagina "Voorwaarden opstellen"
  [PASS] Intentiepolicy: POST policy/create maakt de Offer opnieuw aan
  [PASS] Intentiepolicy: policybestand niet in de kluislisting
  [PASS] Intentiepolicy: policybestand niet in zoekresultaten
  [PASS] Intentiepolicy: policybestand niet als intentie in het overzicht
  [PASS] Intentiepolicy: verwijderen van de intentie verwijdert ook de Offer
  [PASS] Intentiepolicy: testrecords en policybestanden opgeruimd

== Acceptatie en Agreement ==
  [PASS] Acceptatie: open intentie aangemaakt
  [PASS] Acceptatie: intentie geactiveerd
  [PASS] Acceptatie: formulier toont samenvattingszin, JSON-LD en vier labels zonder waarden
  [PASS] Acceptatie: zonder vinkje geweigerd, geen verzoek
  [PASS] Acceptatie: verzoekrecord geschreven bij acceptatie
  [PASS] Acceptatie: verzoek bevat intention, acceptedPolicy, acceptedAt (hele seconden), hash en party
  [PASS] Acceptatie: status geaccepteerd, agreement-uid, responseLink en validUntil = validThrough
  [PASS] Acceptatie: Agreement met @type, uid, assigner, assignee op permission én prohibition
  [PASS] Acceptatie: permission en prohibition gelijk aan de Offer (op assignee na)
  [PASS] Acceptatie: Agreement bevat mysolido:offer, request, acceptedAt en offerHash
  [PASS] Acceptatie: response.json bevat precies de vier attributen met label en valueLabel
  [PASS] Acceptatie: responspagina toont zin, Agreement-uid en de vier waarden, niet brandstof of bouwjaar
  [PASS] Acceptatie: statuspagina toont geaccepteerd met link naar de gegevens
  [PASS] Acceptatie: intentierecord heeft acceptedBy met het verzoek
  [PASS] Acceptatie: detailpagina toont "Geaccepteerd door Verzekeraar X"
  [PASS] Acceptatie: verwijderen van een geaccepteerde intentie geblokkeerd
  [PASS] Acceptatie: eigenaarsdetail toont partij, tijdstip, hash en Agreement-link
  [PASS] Acceptatie: GET /verzoeken/<uuid>/agreement.jsonld geeft application/ld+json  -- application/ld+json
  [PASS] Acceptatie: concept-intentie aangemaakt
  [PASS] Acceptatie: concept toont voorwaarden maar geen acceptatieformulier
  [PASS] Acceptatie: POST op concept geweigerd
  [PASS] Acceptatie: gerichte intentie aangemaakt
  [PASS] Acceptatie: gericht aanbod: verzoek geregistreerd
  [PASS] Acceptatie: gericht: status wacht-op-bevestiging, partij-id = targetedParty.@id, nog geen Agreement
  [PASS] Acceptatie: gericht: eigenaarsdetail toont bevestigknop
  [PASS] Acceptatie: gericht: na goedkeuren status geaccepteerd en Agreement met assignee = targetedParty.@id
  [PASS] Acceptatie: gericht: tweede goedkeuring wordt geweigerd (al afgehandeld)
  [PASS] Acceptatie: .agreement.jsonld niet in de kluislisting
  [PASS] Acceptatie: .agreement.jsonld niet in zoekresultaten
  [PASS] Acceptatie: Agreement niet als verzoek in het overzicht; verzoeken tonen labels
  [PASS] Acceptatie: testintenties, verzoeken, Agreements, responses en consentrecords opgeruimd

== Consentrecord (27560) ==
  [PASS] Consentrecord: open intentie aangemaakt
  [PASS] Consentrecord: acceptatie geregistreerd
  [PASS] Consentrecord: verzoek heeft mysolido:consent en toestemmingen/<id>.jsonld bestaat  -- 20260920-001
  [PASS] Consentrecord: kop (dpv:ConsentRecord, dct:conformsTo 27560, schemaversie, identifier, hasDataSubject = WEBID)
  [PASS] Consentrecord: hasPurpose = purpose-urn met dpv:ServiceProvision en label; hasLegalBasis ExplicitlyExpressedConsent
  [PASS] Consentrecord: hasPersonalData precies vier, urn als @id, pd-term als @type, label en waarde uit het snapshot
  [PASS] Consentrecord: hasDataController = partij-@id met organisatie als label, contactpersoon en e-mail
  [PASS] Consentrecord: hasStorageCondition met validUntil = validThrough en 14 dagen
  [PASS] Consentrecord: hasRecipient leeg, onwardTransfer prohibited met verwijzing naar de Agreement, jurisdictie loc:NL
  [PASS] Consentrecord: status dpv:ConsentGiven, één event given op acceptedAt door de partij, isImplementedByEntity = WEBID
  [PASS] Consentrecord: vijf koppelingen (agreement, intention, request, acceptedPolicy, offerHash) en recht eu-gdpr:A7-3
  [PASS] Consentrecord: consentlijst toont het record met partijlabel en intentiecategorie
  [PASS] Consentrecord: detailpagina toont 27560-weergave met vier attributen, waarden, gebeurtenis en koppelingen
  [PASS] Consentrecord: eigenaarsdetail van het verzoek linkt naar het consentrecord en toont de gedeelde waarden
  [PASS] Consentrecord: intrekken zet dpv:ConsentWithdrawn, tweede event withdrawn door WEBID, dct:modified gezet
  [PASS] Consentrecord: gekoppeld verzoek op ingetrokken met withdrawnAt
  [PASS] Consentrecord: responspagina toont "Toestemming ingetrokken op" en geen gegevens meer
  [PASS] Consentrecord: statuspagina toont "Toestemming ingetrokken op" zonder link naar gegevens
  [PASS] Consentrecord: intentiepagina toont "(toestemming ingetrokken op"
  [PASS] Consentrecord: detailpagina toont status ConsentWithdrawn en het withdrawn-event
  [PASS] Consentrecord: Agreement blijft ongewijzigd bestaan na intrekken
  [PASS] Consentrecord: gerichte intentie aangemaakt
  [PASS] Consentrecord: gericht: acceptatie geregistreerd
  [PASS] Consentrecord: gericht: nog geen consentrecord vóór bevestiging
  [PASS] Consentrecord: gericht: na bevestiging consentrecord aanwezig
  [PASS] Consentrecord: gericht: label = naam (geen organisatie), controller = targetedParty.@id, onwardTransfer permitted
  [PASS] Consentrecord: oude statusterm dpv:ConsentStatusGiven leest terug als ConsentGiven / Actief
  [PASS] Consentrecord: verstreken hasExpiry toont Verlopen (afgeleid, niet geschreven)
  [PASS] Consentrecord: lijst toont beide fixtures met genormaliseerde status
  [PASS] Consentrecord: testintenties, verzoeken, Agreements, responses, consentrecords en fixtures opgeruimd

Resultaat: 109 geslaagd, 0 gefaald, 0 niet automatiseerbaar, 2 info (4s)
```
