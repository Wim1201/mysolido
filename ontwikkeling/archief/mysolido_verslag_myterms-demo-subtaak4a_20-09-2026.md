# MySolido — Verslag MyTerms-demo, subtaak 4a: acceptatie en Agreement

| | |
|---|---|
| **Datum** | 20 september 2026 (derde sessie van die dag) |
| **Softwareversie** | branch `myterms-demo`, uitgangspunt commit `47666e2` ("MyTerms-demo subtaak 3: ODRL-Offer per intentie, samenvatting en leesroute"). Alle wijzigingen hieronder zijn **niet gecommit** |
| **Omgeving** | Windows 10, hoofdcheckout `C:\Users\Wim\mysolido`; CSS 7.2.0 draaide al op `http://127.0.0.1:3000` (niet herstart); Flask voor de tests gestart met `python app.py` op `127.0.0.1:5000` en daarna gestopt; Python 3.13.2 |
| **Gewijzigd** | `app.py`, `templates/intentie_detail.html`, `templates/verzoek_detail.html`, `templates/verzoek_response.html`, `templates/verzoek_status.html`, `templates/verzoek_bevestiging.html`, `templates/verzoeken.html`, `static/css/style.css`, `translations.py`, `scripts/regressietest.py`, `scripts/regressietest.md`, `docs/mysolido_notitie_datamodel-myterms_20-09-2026.md` |
| **Aangemaakt** | `templates/verzoek_intentie.html`, dit verslag |
| **Pod na deze sessie** | Demodata ongewijzigd; `intenties/` bevat jouw twee concept-intenties `a0ac025c` en `fb9189cb`, elk met Offer, niet aangeraakt; `verzoeken/` bevat alleen `.policy.jsonld` (door de test aangemaakt). Alle testintenties, verzoeken, Agreements en responses, ook die van het voorbeeld in §3, zijn opgeruimd |
| **Vervolg op** | `docs/mysolido_verslag_myterms-demo-subtaak3_20-09-2026.md`; regelnummers "oud" verwijzen naar `47666e2`, "nieuw" naar de werkboom van dit verslag |
| **Niet gedaan** | geen git-wijzigingen, geen ClickUp, geen Bridge-run, geen consentrecord (4b), geen wijziging aan `build_policy()`, `build_intention_policy()`, het generieke `/verzoek`-formulier, `REQUEST_CATEGORIES`, `APPROVAL_VALIDITY`, consentmodule, profiel, seed, CSS, startscripts, `.env`, README, trustpagina |

---

## 1. Correcties op notitie, verslag 3, inventarisatie en deze opdracht

1. **De verzoekladers lazen het Agreement-bestand als verzoek.** Zoals de opdracht al vermoedde: `load_all_requests()` (oud `3980`) en ook `find_request_by_status_token()` (oud `4011`, niet genoemd) filteren op `.jsonld` zonder punt vooraan. `verzoeken/<uuid>.agreement.jsonld` zou in het overzicht *Inkomende verzoeken* als leeg verzoek "Onbekend" verschijnen. Beide uitgesloten (`app.py:4179-4180`, `4210`), plus de drie bestandssysteemplekken (`244`, `277`, `333`).

2. **Status- en responspagina kenden alleen `goedgekeurd`.** `verzoek_status()` en `verzoek_response()` gaven voor elke andere status "niet gevonden"/geen vervalcontrole. Zonder aanpassing zou een open acceptatie (status `geaccepteerd`) nooit een responspagina krijgen. Beide routes werken nu met `REQUEST_STATUSES_WITH_RESPONSE = ('goedgekeurd', 'geaccepteerd')` (`app.py:4357`, `4387`). `verzoek_status()` stond niet in de opdracht; de wijziging is één regel plus twee takken in `verzoek_status.html` voor de nieuwe statussen.

3. **Statuswaarde met koppeltekens.** De opdracht schrijft "wacht op bevestiging"; opgeslagen is `wacht-op-bevestiging`, omdat de status overal als CSS-klasse (`badge-<status>`) en als vergelijkingswaarde in templates wordt gebruikt en spaties daar niet werken. Het label op het scherm is "Wacht op bevestiging". `geaccepteerd` is letterlijk overgenomen.

4. **Eén regel Bridge-code toch aangeraakt.** `check_bridge_auth()` laat op de Bridge alleen endpoints uit `public_routes` zonder login door. Zonder toevoeging van `verzoek_intentie` (`app.py:750`) zou een wederpartij op de Bridge eerst het Bridge-wachtwoord van de eigenaar nodig hebben om de voorwaarden te lezen, en klopte "toont in BRIDGE_MODE de voorwaarden" niet. De blokkade van het accepteren zit, zoals gevraagd, in de nieuwe route zelf (GET zonder formulier, POST met flash). Als je dit niet wilt: de ene regel verwijderen. Niet gedraaid met `--bridge`.

5. **Het verzoekrecord houdt de oude velden.** Naast de nieuwe velden uit het datamodel vult de route ook `mysolido:requester`, `mysolido:category`/`categoryLabel`, `mysolido:requestedData` (de attribuut-urn's), `mysolido:purpose` (doellabel), `mysolido:agreedToTerms` en `mysolido:approvedData`, zodat overzicht, statuspagina en de bestaande templates zonder verbouwing blijven werken. Het overzicht toont voor intentiegebonden verzoeken de labels in plaats van de urn's (`app.py:4451-4453`). Toevoeging aan het datamodel, in de notitie opgenomen.

6. **`<uuid>_response.json` heeft voor intentiegebonden verzoeken een andere vorm** dan de groepsvorm van het generieke pad: `{"mysolido:intention", "mysolido:agreement", "mysolido:validUntil", "attributes": [{"@id", "label", "valueLabel"}]}`. `verzoek_response.html` kiest de weergave op aanwezigheid van `attributes`; de groepsweergave blijft voor oude responses.

7. **Sleutelvolgorde in de Agreement.** `assignee` staat op elke regel tussen `target` en `action` (leesbaarheid); inhoudelijk zijn permission en prohibition gelijk aan de Offer, wat de test controleert "op assignee na". Bij een gericht aanbod bevat de Offer zelf al een `assignee` met de door de eigenaar ingevulde naam; de Agreement zet daar de zelfverklaarde naam van de wederpartij bij dezelfde `@id`. In het voorbeeld (§3) zijn beide "Verzekeraar X"; ze kunnen verschillen en dat is zichtbaar bedoeld.

8. **`validThrough` zonder microseconden: gedaan**, als `now = datetime.now(timezone.utc).replace(microsecond=0)` in `intentie_new()` (`app.py:3863`), één regel. Daarmee hebben ook `schema:dateCreated` en `capturedAt` hele seconden. Bestaande records (jouw twee intenties) houden hun microseconden; dat is onschadelijk.

9. **Verzoek-badge in de navigatie telt alleen `nieuw`.** `count_new_requests()` (oud `4002`) negeert `wacht-op-bevestiging`; de eigenaar ziet dus geen teller voor een gerichte acceptatie die op bevestiging wacht. Niet aangepast (verzoekhelper buiten de opdracht), zie §6.

10. **Regelnummers.** De verwijzingen in de opdracht klopten voor `47666e2`. Door het nieuwe blok (`2642-2820`, 179 regels) en de routes (`4634-4802`) is alles daarna verschoven: `intentie_detail` `3946`, `intentie_delete` `4099`, `verzoek_approve` `4515`, dode comment `4579`.

11. **Regressietestfase "Toestemmingen en consentrequests"** bleef ongewijzigd groen: het generieke `/verzoek`-pad is niet geraakt. De nieuwe fase gebruikt een anonieme sessie voor de wederpartij en de eigenaarssessie voor goedkeuren, zoals het scenario dat scheidt.

---

## 2. Per bestand: wat en waarom

### `docs/mysolido_notitie_datamodel-myterms_20-09-2026.md`
Kop: statusregel. §2: nieuw veld `acceptedBy` met de regel dat een geaccepteerde intentie niet verwijderd kan worden en alleen `actief` te accepteren is. §3: rijen Agreement en Verzoek uitgeschreven met alle velden, statussen, route en het sluitmoment; rij Wederpartij verwijst naar `mysolido:party`. §4: rij verzoekvelden bijgewerkt en vier rijen toegevoegd (agreement/status, Agreement-bestand, response, `acceptedBy`).

### `app.py` (4627 → 5033 regels)
- **Verbergregel `.agreement.jsonld`** in `list_folder_filesystem()` (`244`), `search_pod_filesystem()` (`277`), `get_pod_stats_filesystem()` (`333`), `load_all_requests()` (`4179-4180`) en `find_request_by_status_token()` (`4210`).
- **`check_bridge_auth()`** (`750`): `verzoek_intentie` in `public_routes` (§1 punt 4).
- **Nieuw blok `=== ACCEPTATIE EN AGREEMENT ===` (`2642-2820`)**, direct na het intentiepolicyblok:
  - Constanten `AGREEMENT_UID_PREFIX`, `REQUEST_STATUS_ACCEPTED`, `REQUEST_STATUS_AWAITING`, `REQUEST_STATUSES_WITH_RESPONSE` (`2649-2652`).
  - Kleine helpers: `agreement_uid()` (`2655`), `agreement_relpath()` (`2659`), `request_response_relpath()` (`2663`), `utc_now_iso_seconds()` (`2667`), `sha256_of_pod_file()` (`2672`, `"sha256:<hex>"`), `save_pod_json()`/`load_pod_json()` (`2682`, `2688`), `load_intention_record()`/`load_request_record()`/`load_agreement()` (`2700-2710`), `attribute_label_from_urn()` (`2712`).
  - `build_agreement(offer, request_record, party)` (`2731-2749`): kopie van permission en prohibition met de partij als `assignee` per regel, plus `mysolido:offer`, `request`, `acceptedAt`, `offerHash`.
  - `build_response_data()` (`2752`): uitsluitend de `sharedAttributes`.
  - `conclude_agreement(request_record, intention_record)` (`2765-2800`): schrijft Agreement en response, zet status/`agreement`/`responseLink`/`validUntil` (= `validThrough`), voegt het verzoek toe aan `acceptedBy`, logt `request_accept` en `agreement_create`. Regel `2799` is het haakje voor 4b.
  - `accepted_requests_for()` (`2803`): weergavelijst voor de intentiepagina.
- **`intentie_new()`** (`3863`): hele seconden.
- **`intentie_detail()`** (`3986-3997`): `accepted_by` naar de template.
- **`intentie_delete()`** (`4114-4119`): blokkade met flash bij niet-lege `acceptedBy`.
- **`verzoek_status()`** (`4357`) en **`verzoek_response()`** (`4387`, `4411-4425`): status `geaccepteerd` en de attribuutweergave met Agreement-zin en -uid.
- **`verzoeken_overview()`** (`4451-4453`): labels in plaats van urn's.
- **`verzoek_detail_owner()`** (`4483-4507`): `acceptance`-object met intentie, samenvatting, partij, tijdstip, geaccepteerde policy-uid, hash, Agreement en attribuutlabels.
- **`verzoek_approve()`** (`4534-4539`): één vertakking bovenaan naar `confirm_targeted_acceptance()`; het bestaande groepspad en de dode comment (`4579`) ongewijzigd.
- **Nieuw blok `=== ACCEPTATIE VIA INTENTIE: routes ===` (`4634-4802`)**: `_intention_form_context()` (`4638`), `_acceptance_party()` (`4657`, nieuw id bij open, benoemd id bij targeted), `_build_acceptance_request()` (`4666`), route `verzoek_intentie()` GET/POST (`4705-4765`: 404-pagina, Bridge-blokkade van de POST, controle op Offer en status `actief`, rate limit, validatie van naam/e-mail/vinkje, bij open direct `conclude_agreement()`, bij targeted opslaan met `wacht-op-bevestiging`), `confirm_targeted_acceptance()` (`4768-4791`: alleen vanuit status `wacht-op-bevestiging`, alleen bij een gerichte, actieve intentie), route `verzoek_agreement_file()` (`4794-4802`, `application/ld+json`, niet geblokkeerd op de Bridge).

### `templates/verzoek_intentie.html` (nieuw)
Kaart met samenvattingszin, uitklapbare JSON-LD, policy-uid en einddatum; kaart met de attribuutlabels zonder waarden; bij een actieve intentie (en niet op de Bridge) het formulier met naam, organisatie, e-mail en het verplichte vinkje "Ik accepteer deze voorwaarden (<uid>)"; anders de melding (niet actief / Bridge / geen voorwaarden). Bij een gericht aanbod een regel dat de eigenaar nog bevestigt.

### `templates/verzoek_bevestiging.html`
Tak voor `accepted`: kop "Voorwaarden geaccepteerd", tekst voor direct (met knop naar de gegevens) of wachtend op bevestiging; de statuslink blijft.

### `templates/verzoek_status.html`
Takken voor `wacht-op-bevestiging` en `geaccepteerd` (laatste gedeeld met `goedgekeurd`, met eigen kop en badge).

### `templates/verzoek_response.html`
Nieuwe tak als de response `attributes` bevat (`20-52`): badge "Geaccepteerd", kaart **Voorwaarden** met de Agreement-zin en -uid, daarna per attribuut label en waarde. De groepsweergave blijft voor het generieke pad.

### `templates/verzoek_detail.html`
Badge-takken voor de twee statussen (`38-41`); kaart **Acceptatie en Agreement** (`88-146`) met intentie (link + status), partij (naam, organisatie, `@id`), tijdstip (leesbaar én ruw), geaccepteerde voorwaarden, hash, Agreement-uid met link naar de JSON-LD (of "wacht op uw bevestiging"), gedeelde attributen, geldigheid en response-link. Bij `wacht-op-bevestiging` (`148-176`) een bevestigknop op de bestaande `verzoek_approve`-route plus de bestaande afwijsoptie. Het oude goedkeuringsformulier (`179` e.v.) ongewijzigd voor verzoeken zonder intentie.

### `templates/verzoeken.html`, `templates/intentie_detail.html`, `static/css/style.css`
Overzicht: badge-labels voor de twee statussen. Intentiepagina: kaart **Geaccepteerd door** (`117-131`) met per verzoek partij, datum en link naar het verzoek (op de Bridge de Agreement-uid), en de knop Verwijderen verborgen zodra `accepted_by` gevuld is (`183`, `195`). CSS: `.badge-geaccepteerd` (groen) en `.badge-wacht-op-bevestiging` (geel), licht en donker (`1700-1712`).

### `translations.py`
NL `374-414` en EN `1065-1105`: acceptatieformulier, statussen, meldingen, eigenaarsdetail, "Geaccepteerd door". Bestaande sleutels hergebruikt waar dat kon (`req_your_*`, `req_status_view_btn`, `policy_raw`).

### `scripts/regressietest.py` (1450 → 1667 regels)
Nieuwe fase `phase_acceptance` (`1378-1615`): 31 checks, precies de lijst uit de opdracht (open aanbod: formulier, weigering zonder vinkje, verzoek met alle velden en kloppende sha256, Agreement-vorm en gelijkheid met de Offer, response met precies vier attributen zonder brandstof/bouwjaar, statuspagina, `acceptedBy`, "Geaccepteerd door", verwijderblokkade, eigenaarsdetail, GET agreement.jsonld; concept: voorwaarden zonder formulier, POST geweigerd; gericht: `wacht-op-bevestiging` zonder Agreement, bevestigknop, na goedkeuren Agreement met `assignee` = `targetedParty.@id`, tweede goedkeuring geweigerd; listing/zoeken/overzicht; opruimen inclusief Agreements en responses). `--phase demo` (`1627`) en de volledige run (`1642`) nemen de fase mee.

### `scripts/regressietest.md`
Rij 13e (`68`); paragraaf `--phase demo` noemt 13a t/m 13e (`92-95`).

---

## 3. Voorbeeld: één geaccepteerde testintentie

Aangemaakt tijdens deze sessie (open aanbod, autoverzekering, vier attributen, doorleververbod, 2 weken), geactiveerd, geaccepteerd door "Verzekeraar X" via het formulier, en daarna weer opgeruimd. Jouw intenties zijn hiervoor niet gebruikt.

**Scherm van de wederpartij vóór acceptatie** (`GET /verzoek/intentie/02432e99-…`, als tekst):

```
Voorwaarden accepteren: Autoverzekering
De eigenaar van deze kluis biedt onderstaande gegevens aan onder deze voorwaarden. Na acceptatie ontvangt u de waarden.

Voorwaarden (ODRL-aanbod)
Iedereen die deze voorwaarden accepteert mag leeftijdscategorie, postcodegebied, voertuigtype en
schadeverleden gebruiken, uitsluitend voor offerteberekening, tot 04-10-2026, en mag ze niet doorleveren.
[uitklapbaar: ruwe ODRL policy (JSON-LD)]
urn:mysolido:policy:intention:02432e99-6445-4022-93f1-39945ca21780 · geldig tot 04-10-2026

Gegevens in dit aanbod
Leeftijdscategorie   Postcodegebied (4 cijfers)   Voertuigtype   Schadeverleden
De waarden worden pas na acceptatie getoond.

Uw gegevens
Naam *            [Uw volledige naam]
Organisatie       [Optioneel]
E-mailadres *     [uw@email.nl]
[ ] Ik accepteer deze voorwaarden (urn:mysolido:policy:intention:02432e99-6445-4022-93f1-39945ca21780)
[Voorwaarden accepteren]
```

**Verzoekrecord** `verzoeken/d1da5cec-08b9-4311-8595-7fd732b1c0be.jsonld`:

```json
{
  "@context": {
    "mysolido": "https://mysolido.com/vocab#",
    "dpv": "https://w3id.org/dpv#",
    "schema": "https://schema.org/",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "xsd": "http://www.w3.org/2001/XMLSchema#"
  },
  "@type": "mysolido:ConsentRequest",
  "@id": "urn:mysolido:request:d1da5cec-08b9-4311-8595-7fd732b1c0be",
  "mysolido:statusToken": "a6652486-5f7a-4e5d-985e-2434d76220a7",
  "mysolido:status": "geaccepteerd",
  "schema:dateCreated": "2026-09-20T10:58:37+00:00",
  "mysolido:requester": {
    "schema:name": "Verzekeraar X",
    "schema:worksFor": "Verzekeraar X BV",
    "schema:email": "offerte@verzekeraar-x.test"
  },
  "mysolido:category": "autoverzekering",
  "mysolido:categoryLabel": "Autoverzekering",
  "mysolido:requestedData": [
    "urn:mysolido:attribute:age_category",
    "urn:mysolido:attribute:postal_area",
    "urn:mysolido:attribute:vehicle_type",
    "urn:mysolido:attribute:claims_history"
  ],
  "mysolido:purpose": "Offerteberekening",
  "mysolido:agreedToTerms": true,
  "mysolido:intention": "urn:mysolido:intention:02432e99-6445-4022-93f1-39945ca21780",
  "mysolido:acceptedPolicy": "urn:mysolido:policy:intention:02432e99-6445-4022-93f1-39945ca21780",
  "mysolido:acceptedAt": "2026-09-20T10:58:37+00:00",
  "mysolido:acceptedPolicyHash": "sha256:1477206b142ec5e2a99fde7ab5fd582a4b9cd53fb48a28e19ac33e744053a17d",
  "mysolido:party": {
    "@id": "urn:mysolido:party:2e10e089",
    "rdfs:label": "Verzekeraar X",
    "mysolido:organisation": "Verzekeraar X BV",
    "mysolido:contact": "offerte@verzekeraar-x.test"
  },
  "mysolido:approvedData": [
    "urn:mysolido:attribute:age_category",
    "urn:mysolido:attribute:postal_area",
    "urn:mysolido:attribute:vehicle_type",
    "urn:mysolido:attribute:claims_history"
  ],
  "mysolido:responseLink": "/verzoek/response/a6652486-5f7a-4e5d-985e-2434d76220a7",
  "mysolido:validUntil": "2026-10-04T10:58:37+00:00",
  "mysolido:rejectionReason": null,
  "mysolido:agreement": "urn:mysolido:agreement:d1da5cec-08b9-4311-8595-7fd732b1c0be"
}
```

**Agreement** `verzoeken/d1da5cec-08b9-4311-8595-7fd732b1c0be.agreement.jsonld`:

```json
{
  "@context": [
    "http://www.w3.org/ns/odrl.jsonld",
    {
      "dpv": "https://w3id.org/dpv#",
      "rdfs": "http://www.w3.org/2000/01/rdf-schema#"
    }
  ],
  "@type": "Agreement",
  "uid": "urn:mysolido:agreement:d1da5cec-08b9-4311-8595-7fd732b1c0be",
  "profile": "http://www.w3.org/ns/odrl/2/core",
  "assigner": "http://127.0.0.1:3000/mysolido/profile/card#me",
  "permission": [
    {
      "target": [
        "urn:mysolido:attribute:age_category",
        "urn:mysolido:attribute:postal_area",
        "urn:mysolido:attribute:vehicle_type",
        "urn:mysolido:attribute:claims_history"
      ],
      "assignee": {
        "@id": "urn:mysolido:party:2e10e089",
        "rdfs:label": "Verzekeraar X"
      },
      "action": "use",
      "constraint": [
        {
          "leftOperand": "purpose",
          "operator": "eq",
          "rightOperand": {
            "@id": "urn:mysolido:purpose:quote_calculation"
          }
        },
        {
          "leftOperand": "dateTime",
          "operator": "lteq",
          "rightOperand": {
            "@type": "xsd:dateTime",
            "@value": "2026-10-04T10:58:37+00:00"
          }
        }
      ]
    }
  ],
  "prohibition": [
    {
      "target": [
        "urn:mysolido:attribute:age_category",
        "urn:mysolido:attribute:postal_area",
        "urn:mysolido:attribute:vehicle_type",
        "urn:mysolido:attribute:claims_history"
      ],
      "assignee": {
        "@id": "urn:mysolido:party:2e10e089",
        "rdfs:label": "Verzekeraar X"
      },
      "action": [
        "distribute",
        "transfer"
      ]
    }
  ],
  "mysolido:offer": "urn:mysolido:policy:intention:02432e99-6445-4022-93f1-39945ca21780",
  "mysolido:request": "urn:mysolido:request:d1da5cec-08b9-4311-8595-7fd732b1c0be",
  "mysolido:acceptedAt": "2026-09-20T10:58:37+00:00",
  "mysolido:offerHash": "sha256:1477206b142ec5e2a99fde7ab5fd582a4b9cd53fb48a28e19ac33e744053a17d"
}
```

**Response** `verzoeken/d1da5cec-08b9-4311-8595-7fd732b1c0be_response.json`:

```json
{
  "mysolido:intention": "urn:mysolido:intention:02432e99-6445-4022-93f1-39945ca21780",
  "mysolido:agreement": "urn:mysolido:agreement:d1da5cec-08b9-4311-8595-7fd732b1c0be",
  "mysolido:validUntil": "2026-10-04T10:58:37+00:00",
  "attributes": [
    {"@id": "urn:mysolido:attribute:age_category", "label": "Leeftijdscategorie", "valueLabel": "35-44"},
    {"@id": "urn:mysolido:attribute:postal_area", "label": "Postcodegebied (4 cijfers)", "valueLabel": "5611"},
    {"@id": "urn:mysolido:attribute:vehicle_type", "label": "Voertuigtype", "valueLabel": "Auto"},
    {"@id": "urn:mysolido:attribute:claims_history", "label": "Schadeverleden",
     "valueLabel": "Schadevrije jaren: 5, Schade geclaimd in de laatste 3 jaar: nee"}
  ]
}
```

**Scherm van de wederpartij na acceptatie** (`GET /verzoek/response/a6652486-…`, als tekst):

```
Gedeelde gegevens                                   [Geaccepteerd]
Deze gegevens zijn gedeeld via MySolido — geldig tot 2026-10-04

Voorwaarden
Verzekeraar X mag leeftijdscategorie, postcodegebied, voertuigtype en schadeverleden gebruiken,
uitsluitend voor offerteberekening, tot 04-10-2026, en mag ze niet doorleveren.
Agreement: urn:mysolido:agreement:d1da5cec-08b9-4311-8595-7fd732b1c0be

Leeftijdscategorie            35-44
Postcodegebied (4 cijfers)    5611
Voertuigtype                  Auto
Schadeverleden                Schadevrije jaren: 5, Schade geclaimd in de laatste 3 jaar: nee

Deze gegevens zijn gedeeld via MySolido — een persoonlijke datakluis.
```

Brandstof (benzine) en bouwjaar (2019) staan in het profiel maar niet op deze pagina.

---

## 4. Uitkomst regressietest

Tegen de lopende CSS 7.2.0 en een voor de test gestarte Flask, scenario U.

| Run | Opdracht | Resultaat |
|---|---|---|
| 1 | `--phase demo` (13a t/m 13e) | **79 geslaagd, 0 gefaald**, 2 info, 3 s; de nieuwe fase 31 van 31 groen bij de eerste run |
| 2 | volledige run `--scenario U` | **171 geslaagd, 0 gefaald**, 2 niet automatiseerbaar (bekend: WebID-token op http, scp naar Bridge), 32 info, 9 s. Alle bestaande fasen groen, ook "Toestemmingen en consentrequests" (generiek verzoekpad) |

Fasen van run 2: Preflight, Accountcreatie, WebID en credentials, Bestanden en roundtrip, Identifier-normalisatie, WAC/ACL, Deellinks, ODRL-beleid, Toestemmingen en consentrequests, Demodata, Profielvelden, Intentie, Intentiepolicy, **Acceptatie en Agreement**, Backup en restore, /debug, Probes 7.2.0, Bridge-sync module, Persistentie aanmaken, Opruimen. Ruwe uitvoer in de bijlage. Flask-log zonder fouten of tracebacks.

---

## 5. Handmatige controle (niet uitgevoerd, voor jou)

Start Flask (`python app.py`), open `http://127.0.0.1:5000`. Gebruik voor de wederpartij een privévenster of een tweede browser, zodat je ziet dat daar geen eigenaarslogin nodig is.

1. **Activeren en het formulier lezen.** *Profiel → Mijn intenties → a0ac025c* ("allrisk … voor de duur van een jaar"): klik **Activeren**. Open in het privévenster `http://127.0.0.1:5000/verzoek/intentie/a0ac025c-0521-42cc-bb0e-d68f943cff70`. Verwacht: de zin "Iedereen die deze voorwaarden accepteert mag … tot 04-10-2026, en mag ze niet doorleveren.", de uitklapbare JSON, vier labels zonder waarden, en het formulier met het vinkje "Ik accepteer deze voorwaarden (urn:mysolido:policy:intention:a0ac025c-…)". Doe hetzelfde met `fb9189cb` (nog concept): dezelfde voorwaarden, maar de melding "niet actief (status: concept)" in plaats van het formulier.
2. **Accepteren (open aanbod).** In het privévenster: naam "Verzekeraar X", organisatie "Verzekeraar X BV", e-mail, klik eerst zonder vinkje (de browser houdt het tegen; wie het vinkje in de HTML weghaalt krijgt de flash "Vink aan dat u de voorwaarden accepteert."), dan met vinkje. Verwacht: pagina "Voorwaarden geaccepteerd" met knop **Gegevens bekijken** en de statuslink. Klik de knop: precies vier regels met waarden, daarboven de zin nu beginnend met "Verzekeraar X mag …" en de Agreement-uid. Op schijf: `verzoeken\<uuid>.jsonld`, `<uuid>.agreement.jsonld`, `<uuid>_response.json`.
3. **Eigenaarskant.** *Profiel → Verzoeken*: het verzoek met badge **Geaccepteerd** en de vier labels. Open het: kaart **Acceptatie en Agreement** met partij en `urn:mysolido:party:…`, tijdstip, geaccepteerde policy-uid, de sha256-hash en de link **Bekijk Agreement (JSON-LD)** (opent als `application/ld+json`). Terug naar de intentie a0ac025c: kaart **Geaccepteerd door** met "Verzekeraar X op 20-09-2026"; de knop Verwijderen is weg. Wie toch `POST /intenties/a0ac025c-…/delete` afvuurt, krijgt de flash dat verwijderen niet kan.
4. **Gericht aanbod.** Maak een nieuwe intentie *Autoverzekering* met **Gericht aanbod** aan "Verzekeraar Y", activeer, en accepteer in het privévenster als "Verzekeraar Y". Verwacht: "wacht op bevestiging" op de bevestigingspagina en de statuspagina; in *Verzoeken* badge **Wacht op bevestiging**, in het detail de tekst "Bevestig dat deze partij de benoemde partij is (Verzekeraar Y)" met knop **Bevestigen (goedkeuren)**. Klik: badge wordt Geaccepteerd, Agreement-link verschijnt, in de JSON staat `assignee.@id` gelijk aan `mysolido:targetedParty.@id` van de intentie. De statuspagina van de wederpartij toont nu de knop naar de gegevens. Nog eens op Bevestigen (via herladen van het POST) geeft "al afgehandeld". Deze testintentie kun je niet meer verwijderen; verwijder desgewenst handmatig de drie verzoekbestanden en daarna de intentie via de knop (of laat alles staan als demostand).

---

## 6. Buiten dit verslag

**Bewust niet gedaan.** Geen consentrecord: `conclude_agreement()` heeft op regel `2799` het haakje; de dode comment in `verzoek_approve()` (`4579`) staat er nog. Geen intrekken van een Agreement (4b). Geen verificatie van de identiteit van de wederpartij: naam, organisatie en e-mail zijn zelfverklaard; de partij-id is een willekeurige hex (open) of de door de eigenaar vooraf benoemde id (gericht), en bij gericht bevestigt de eigenaar handmatig dat de zelfverklaarde naam de benoemde partij is. Bekende beperking van de demo, staat ook op het formulier niet vermeld. Geen Bridge-run. Geen ODRL-validator. Herhaald accepteren van hetzelfde open aanbod door dezelfde partij is niet begrensd (alleen de rate limit per IP): elke acceptatie geeft een nieuw verzoek, een nieuwe partij-id en een nieuwe Agreement.

**Tegengekomen, voor 4b (consentrecord).**
- Alles voor het record staat in `conclude_agreement()` bij elkaar: `request_record['mysolido:party']` (controller met `@id`, label, organisatie, contact), `intention_record['mysolido:sharedAttributes']` (met `PROFILE_ATTRIBUTES[key]['dpv']` voor `dpv:hasPersonalData`), `intention_record['mysolido:purpose']['dpv']`, `validThrough` (bewaartermijn), `agreement['uid']`, `request_record['@id']`, `noOnwardTransfer` (geen derden). Eén aanroep op de plek van de comment.
- Intrekken: een ingetrokken intentie (`intentie_withdraw`) raakt nu verzoek, response en `acceptedBy` niet; de responspagina blijft tot `validUntil` werken. 4b moet bepalen of intrekken van de intentie of van het consentrecord de response sluit (statuswaarde, bijv. `ingetrokken`, en de vervalcontrole in `verzoek_response`/`verzoek_status` uitbreiden).
- `count_new_requests()` telt alleen `nieuw`; een gerichte acceptatie die wacht op bevestiging geeft geen teller in de navigatie (§1 punt 9). Eén regel als je dat wilt.
- `verzoek_reject()` werkt ongewijzigd ook op `wacht-op-bevestiging` (status wordt `afgewezen`); de statuspagina van de wederpartij toont dan "afgewezen". Geen Agreement, geen `acceptedBy`. Lijkt juist, niet apart getest.
- Datumnotatie: de responspagina toont "geldig tot 2026-10-04" (bestaande template) naast "tot 04-10-2026" in de zin. Zelfde gemengde notatie als op de intentiepagina; hoort bij de app-brede afspraak.

**Tegengekomen, voor 5 (Bridge).**
- Op de Bridge is `/verzoek/intentie/<uuid>` nu publiek leesbaar (§1 punt 4); accepteren wordt geblokkeerd met de melding dat dat via de lokale kluis loopt. De eigenaarsroutes `/verzoeken/*` geven op de Bridge 403 zoals voorheen, behalve de nieuwe `agreement.jsonld` (na Bridge-login). De intentiepagina toont "Geaccepteerd door" alleen-lezen met de Agreement-uid in plaats van de verzoeklink.
- `sync_bridge.py` neemt `<uuid>.agreement.jsonld` en `_response.json` mee als gewone bestanden; na een acceptatie op de pc is één sync nodig voordat de telefoon de Agreement ziet (variant A).

**Tegengekomen, voor de andere lijsten.**
- De `.policy.jsonld` van `verzoeken/` blijft na de testrun staan (de opruimfase verwijdert de map alleen als die vóór de run niet bestond; dat was nu wel het geval door de eerdere demo-run). Onschadelijk; de app maakt hem anders zelf.
- `mysolido:requestedData` bevat bij intentiegebonden verzoeken urn's, bij generieke verzoeken groepsnamen. Het overzicht vertaalt de urn's; `verzoek_detail.html` toont voor intentiegebonden verzoeken de attribuutlabels in de acceptatiekaart en daarnaast nog steeds de bestaande "Gevraagde gegevens"-regel met `profile_groups.get(urn)` → kale urn's als badges. Cosmetisch, niet aangepast om het generieke deel van de template niet te raken.
- Het bestand `tatus --short` uit het vorige verslag is inmiddels weg uit de repo-root.

**Vragen die alleen jij kunt beantwoorden.**
1. Akkoord met de ene regel in `check_bridge_auth()` (`verzoek_intentie` publiek op de Bridge)? Zonder die regel kan een wederpartij de voorwaarden op de Bridge niet lezen.
2. Moet een intentie met `acceptedBy` ook niet meer **ingetrokken** kunnen worden, of is intrekken juist de weg naar "response sluiten" in 4b?
3. Mag dezelfde partij een open aanbod vaker accepteren (nu onbegrensd), of wil je een grens per e-mailadres per intentie?
4. Wil je op het formulier een zichtbare zin dat de identiteit niet geverifieerd wordt (eerlijk voor de demo), of laat je dat in de mondelinge toelichting?
5. Moet de navigatieteller ook `wacht-op-bevestiging` meetellen (één regel in `count_new_requests()`)?

---

## Bijlage: ruwe uitvoer

### Run 2: `python scripts/regressietest.py --scenario U` (volledige run)

```
MySolido regressietest 2026-09-20 12:58 -- scenario U, fase all, CSS http://127.0.0.1:3000 (7.2.0), Flask http://127.0.0.1:5000, Pod http://127.0.0.1:3000/mysolido/

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
  [PASS] Test-Pod aanmaken  -- http://127.0.0.1:3000/regressietest-pod-b7db99/
  [PASS] Test-Pod staat op schijf als .data/<podnaam>/  -- C:\Users\Wim\mysolido\.data\regressietest-pod-b7db99
  [PASS] Test-WebID publiek bereikbaar met solid:oidcIssuer  -- http://127.0.0.1:3000/regressietest-pod-b7db99/profile/card#me
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
  [PASS] Toestemming: intrekken zet status Withdrawn
  [PASS] Toestemming: verwijderen
  [PASS] Consentrequest: verzoek via publiek formulier weggeschreven
  [PASS] Consentrequest: JSON-LD velden correct en statustoken in bevestiging  -- 0d42e477-8f5a-4c7b-a2bc-2f251c9c894a
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
  [PASS] Intentiepolicy: intenties/<uuid>.policy.jsonld geschreven  -- 7cf118d4-4653-4759-8ec6-524e01be0213.policy.jsonld
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
  [PASS] Acceptatie: testintenties, verzoeken, Agreements en responses opgeruimd

== Backup en restore ==
  [PASS] Backup: zip-export  -- 7875 bytes
  [PASS] Backup: bevat testbestand met juiste inhoud  -- regressietest/ldp/roundtrip.txt
  [INFO] Backup: .policy.jsonld en .acl in zip  -- ja
  [INFO] Backup: .mysolido/share_links.json in zip  -- nee
  [PASS] Restore: bestand uit zip teruggezet en via CSS leesbaar

== Flask /debug (HTTP-laag) ==
  [PASS] Flask /debug: HTTP-lezing van Pod-root via CSS (root is publiek)

== Probes 7.2.0-changelog ==
  [INFO] Probe dubbele slug: twee POSTs met Slug slug-test.txt  -- 201 http://127.0.0.1:3000/mysolido/regressietest/ldp/slug-test.txt | 201 http://127.0.0.1:3000/mysolido/regressietest/ldp/a7792c38-ccd7-4c40-9102-b509871f0829; op schijf ['slug-test.txt']
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
  [PASS] Opruimen: toestemmingen/ verwijderd (bestond niet voor de test)
  [PASS] Opruimen: .mysolido/ verwijderd (bestond niet voor de test)
  [INFO] Opruimen: testaccount verwijderen via account-API  -- geen account-URL in controls
  [PASS] Opruimen: test-Pod-map van schijf verwijderd  -- C:\Users\Wim\mysolido\.data\regressietest-pod-b7db99
  [INFO] Opruimen: runtime-bestanden in projectmap (trash.json, shares.json, audit_log.json, notifications.json)  -- blijven staan, vallen onder .gitignore

Resultaat: 171 geslaagd, 0 gefaald, 2 niet automatiseerbaar, 32 info (9s)
```

### Run 1: `python scripts/regressietest.py --phase demo` (13a t/m 13e)

```
MySolido regressietest 2026-09-20 12:57 -- scenario U, fase demo, CSS http://127.0.0.1:3000 (7.2.0), Flask http://127.0.0.1:5000, Pod http://127.0.0.1:3000/mysolido/

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
  [PASS] Intentiepolicy: intenties/<uuid>.policy.jsonld geschreven  -- 305c792e-8169-4078-8500-e489e5a865e8.policy.jsonld
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
  [PASS] Acceptatie: testintenties, verzoeken, Agreements en responses opgeruimd

Resultaat: 79 geslaagd, 0 gefaald, 0 niet automatiseerbaar, 2 info (3s)
```
