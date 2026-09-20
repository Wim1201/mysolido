# MySolido — Verslag MyTerms-demo, subtaak 3: ODRL-policy genereren

| | |
|---|---|
| **Datum** | 20 september 2026 (tweede sessie van die dag) |
| **Softwareversie** | branch `myterms-demo`, uitgangspunt commit `b03f12c` ("MyTerms-demo subtaak 2: profielattributen, per-veldselectie in intentie, seed-script"). Alle wijzigingen hieronder zijn **niet gecommit** |
| **Omgeving** | Windows 10, hoofdcheckout `C:\Users\Wim\mysolido`; CSS 7.2.0 draaide al op `http://127.0.0.1:3000` (niet herstart); Flask voor de tests gestart met `python app.py` op `127.0.0.1:5000` en daarna gestopt; Python 3.13.2 |
| **Gewijzigd** | `app.py`, `templates/intentie_detail.html`, `templates/intentie_nieuw.html`, `translations.py`, `scripts/regressietest.py`, `scripts/regressietest.md`, `docs/mysolido_notitie_datamodel-myterms_20-09-2026.md` |
| **Aangemaakt** | dit verslag |
| **Pod na deze sessie** | Demodata van het seed-script ongewijzigd; `intenties/` bevat jouw concept-intentie `a0ac025c-…jsonld` (niet aangeraakt, dus nog **zonder** `.policy.jsonld` en zonder `mysolido:policy`) en `intenties/.policy.jsonld`. Alle testintenties en hun Offers zijn opgeruimd; geen verzoeken of toestemmingen |
| **Vervolg op** | `docs/mysolido_verslag_myterms-demo-subtaak2_20-09-2026.md`; regelnummers "oud" verwijzen naar `b03f12c`, "nieuw" naar de werkboom van dit verslag |
| **Niet gedaan** | geen git-wijzigingen, geen ClickUp, geen Bridge-run, geen wijziging aan `build_policy()`, `policy_summary_nl()`, `init_default_policies()`, mappolicies, `policy_edit.html`, verzoeken, consent, profielopslag, seed-script, CSS, startscripts, `.env`, README of trustpagina |

---

## 1. Correcties op notitie, verslag subtaak 2 en deze opdracht

1. **Het policybestand dook op vier plekken op als gewoon bestand of zelfs als intentie.** De verbergregel kende alleen dotfiles en `.acl`/`.meta`. `intenties/<uuid>.policy.jsonld` verscheen in `/browse/intenties`, in zoekresultaten, telde mee in de opslagstatistiek en, ernstiger, `load_all_intentions()` (oud `3394`) las het als intentierecord: het overzicht *Mijn intenties* zou de Offer als een tweede intentie "Anders" tonen. Alle vier aangepast op het suffix `.policy.jsonld` (`app.py:243-244`, `277`, `333`, `3567-3568`). De backup-export slaat dotfiles over maar neemt `<uuid>.policy.jsonld` wél mee; dat is gewenst en ongewijzigd gelaten.

2. **Notitie miste twee velden**, zoals de opdracht al aangaf: `mysolido:policy` op het record en `targetedParty.@id`. Toegevoegd in §2, plus de concrete Offer-vorm in §3 en twee rijen in de tabel van §4. Ook vastgelegd: een intentie zonder gevuld, aangevinkt attribuut wordt geweigerd.

3. **Afwijkingen van de Offer-vorm uit de opdracht, alle klein:**
   - **Context.** "Zelfde context als de bestaande policies" is gevolgd (ODRL-context plus `dpv`), maar uitgebreid met `rdfs` omdat het partijlabel als `rdfs:label` wordt geschreven. `xsd:dateTime` steunt, net als in `build_policy()`, op de `xsd`-declaratie in de ODRL-context zelf.
   - **Korte ODRL-namen.** De opdracht schrijft `odrl:use`, `odrl:distribute`, enzovoort. De mappolicies gebruiken binnen de ODRL-context korte namen (`"Set"`, `"read"`, `"distribute"`); de Offer doet hetzelfde (`"Offer"`, `"use"`, `"distribute"`, `"transfer"`, `"purpose"`, `"dateTime"`, `"eq"`, `"lteq"`). Het zijn dezelfde termen.
   - **Assignee op beide regels.** Bij een gericht aanbod staat de `assignee` op de permission én op de prohibition (ODRL zet assignee per regel, en de prohibition geldt dezelfde partij). Bij open aanbod nergens.
   - **Samenvatting.** De labels komen uit `PROFILE_ATTRIBUTES`, maar met kleine beginletter en zonder toelichting tussen haakjes: "postcodegebied" in plaats van "Postcodegebied (4 cijfers)", zodat de zin de voorbeeldzin uit de opdracht volgt. Het doellabel wordt ook met kleine letter geschreven ("offerteberekening").

4. **Verwijderen van een intentie verwijdert nu ook de Offer.** Niet in de opdracht; toegevoegd omdat een losse `<uuid>.policy.jsonld` zonder record nergens meer bereikbaar is en de opruimfase van de test anders wezen zou achterlaten (`app.py:3931-3934`, vier regels).

5. **Twee bestaande testchecks braken door het nieuwe bestand.** De fase "Intentie met per-veldselectie" telde het nieuwe `.policy.jsonld` als tweede "nieuw record" (twee checks rood in de eerste run) en verwachtte `targetedParty` zonder `@id`. Beide aangepast (`regressietest.py:1097-1100`, `1180-1185`); de eerste rode run liet één testrecord achter dat ik met de verwijderroute heb opgeruimd voordat de tweede run draaide.

6. **Ruwe JSON op de detailpagina staat alfabetisch.** Flask's `tojson`-filter sorteert sleutels; daardoor staat `"uid"` onderaan en `"@type"` bovenaan. Het bestand op schijf en de GET-route hebben de logische volgorde (context, type, uid, profile, assigner, permission, prohibition). Zelfde gedrag als `policy_edit.html`; niet aangepast.

7. **Datumnotatie op één pagina nu gemengd.** "Vastgelegd op" en de samenvattingszin tonen `dd-mm-jjjj` (zoals gevraagd); "Aangemaakt" en "Geldig tot" op dezelfde detailpagina blijven `jjjj-mm-dd` (buiten deze taak, zoals de opdracht zegt). Zie §5.

8. **Regelnummers.** De verwijzingen in de opdracht klopten voor `b03f12c` (attributenblok `2765-3086`, `intentie_new` `3499`, `intentie_detail` `3591`, dode comment `4117`). Door het nieuwe blok op `2477-2640` (164 regels) en de routes zijn ze verschoven: attributenblok nu `2929-3250`, `intentie_new` `3665`, `intentie_detail` `3766`, "Create consent record" `4342`.

9. **Bridge-modus is niet gedraaid.** De nieuwe GET-route staat niet in `blocked_endpoints` (`app.py:764-786`) en valt onder de gewone Bridge-login; de kaart op de detailpagina is niet aan `read_only` gebonden, alleen de knop "Voorwaarden opstellen". Dat is uit de code afgeleid, niet getest met `--bridge` (zie §5, subtaak 5).

10. **Losse waarneming.** In de repo-root staat een ongetrackt bestand met de naam `tatus --short` (26 kB, inhoud is een `git diff` van subtaak 2, vermoedelijk een vertikte `git status --short` met `>`). Niet van mij, niet aangeraakt.

---

## 2. Per bestand: wat en waarom

### `docs/mysolido_notitie_datamodel-myterms_20-09-2026.md`
Kop: statusregel bijgewerkt. §2: `targetedParty` krijgt `@id` (vorm en generatie zoals `consent_new()`), nieuw veld `mysolido:policy`, regel over weigering zonder attributen. §3: rij "Intentiepolicy" vervangen door de concrete Offer-vorm (context, type, assigner, permission met targets en twee constraints, prohibition, assignee, geen eigen status, samenvattingsfunctie, lees- en herstelroute). §4: rij van de Offer aangepast (wie schrijft: `intentie_new()` en de herstelroute) en nieuwe rij voor `mysolido:policy` en `targetedParty.@id`.

### `app.py` (4402 → 4627 regels)
- **Verbergregel `.policy.jsonld`** in `list_folder_filesystem()` (`243-244`), `search_pod_filesystem()` (`277`), `get_pod_stats_filesystem()` (`333`) en `load_all_intentions()` (`3567-3568`). Zie §1 punt 1.
- **Nieuw blok `=== INTENTIEPOLICY: ODRL-Offer per intentie ===` (`2477-2640`)**, direct na `edit_policy()` en vóór de consentmodule; `build_policy()` en `policy_summary_nl()` zijn niet aangeraakt.
  - Constanten `INTENTION_POLICY_CONTEXT`, `INTENTION_POLICY_UID_PREFIX`, `PARTY_URN_PREFIX`, `OPEN_OFFER_WHO_NL` (`2484-2491`).
  - `intention_policy_uid()` (`2493`), `intention_policy_relpath()` (`2497`), `intention_id_from_record()` (`2501`), `generate_party_id()` (`2505`, `urn:mysolido:party:<hex>` met `secrets.token_hex(4)` zoals `consent_new()`).
  - `build_intention_policy(record)` (`2510-2545`): de Offer volgens notitie §3. Targets in de volgorde van `sharedAttributes`; purpose-`@id` uit het record; `validThrough` als `xsd:dateTime`; assignee alleen bij `targeted`; prohibition alleen bij `noOnwardTransfer`. Assigner is `WEBID` uit `.env` (via `os.getenv`, zoals de rest van de app).
  - `write_intention_policy(record)` (`2547`, schrijft via `pod_write`, geeft `None` zonder attributen), `load_intention_policy(intention_id)` (`2557`).
  - `format_date_nl_iso()` (`2569`, ISO → `dd-mm-jjjj`), `_join_nl()` (`2577`, "a, b en c"), `_lower_first()` (`2584`), `_summary_label()` (`2588`), `_operand_value()` (`2593`).
  - `intention_policy_summary_nl(policy, record)` (`2597-2640`): leest wie/targets/constraints/prohibition uit de policy zelf en valt voor het doellabel terug op het record.
- **`INTENTION_CATEGORIES`** (`3381`): `autoverzekering` krijgt `default_validity: '2w'` (restpunt geldigheid).
- **`intentie_new()`** (`3665-3760`): weigering zonder gevuld, aangevinkt attribuut met flash (`3705-3708`); `mysolido:policy` in het record (`3733`); `targetedParty` met `@id` (`3736-3737`); `write_intention_policy(record)` direct na het schrijven van het record (`3743-3744`); logregel met de policy-uid (`3747-3749`).
- **`intentie_detail()`** (`3766-3816`): laadt de Offer en maakt de samenvatting (`3802-3804`); geeft `policy`, `policy_summary` en `captured_at` in `dd-mm-jjjj` door (`3806-3816`).
- **Nieuwe routes** (`3818-3856`): `GET /intenties/<uuid>/policy.jsonld` (`intentie_policy_file`, 404 zonder bestand, `application/ld+json`, niet geblokkeerd in Bridge-modus) en `POST /intenties/<uuid>/policy/create` (`intentie_policy_create`, 403 in Bridge-modus, weigert zonder `sharedAttributes`, schrijft de Offer en zet `mysolido:policy` als dat nog ontbrak, logt `intention_policy_create`).
- **`intentie_delete()`** (`3931-3934`): verwijdert ook `<uuid>.policy.jsonld`.

### `templates/intentie_detail.html`
Nieuwe kaart **Voorwaarden (ODRL-aanbod)** (`92-116`) tussen de MyTerms-kaart en het snapshot: samenvattingszin, uitklapbare ruwe JSON-LD (`<details class="policy-raw">`, dezelfde opmaak als `policy_edit.html`), link naar de GET-route en de uid. Zonder policy maar mét `sharedAttributes`: melding plus knop "Voorwaarden opstellen" (alleen als `read_only` onwaar is). Zonder `sharedAttributes` (oud formaat): alleen de melding dat er geen voorwaarden zijn. De kaart zelf is niet aan `read_only` gebonden en verschijnt dus ook op de Bridge. "Vastgelegd op" krijgt de datum al geformatteerd uit de route.

### `templates/intentie_nieuw.html`
`categoryValidity` (`193-198`) naast `categoryFields`; `updateAttributeSelection()` zet de geldigheidsduur op `default_validity` van de categorie als die er is (`206-208`). Bij *Autoverzekering* springt de keuzelijst dus op "2 weken"; andere categorieën laten de keuze staan.

### `translations.py`
NL `366-374` en EN `1016-1024`: `flash_attributes_required`, `flash_policy_created`, `flash_policy_no_attributes`, `int_policy_title`, `int_policy_file`, `int_policy_missing`, `int_policy_create`, `int_policy_none`. De bestaande sleutel `policy_raw` ("Bekijk ruwe ODRL policy (JSON-LD)") wordt hergebruikt.

### `scripts/regressietest.py` (1279 → 1450 regels)
- Fase "Intentie met per-veldselectie": `new_files()` negeert `.policy.jsonld` (`1097-1100`); check op `targetedParty` met `@id` (`1180-1185`); opruimen verwijdert ook policybestanden (`1204-1212`).
- Nieuwe fase `phase_intention_policy` (`1215-1395`): open aanbod met vier attributen → bestand, `@type`/uid/profile/assigner, één permission `use` met targets in volgorde, beide constraints met de juiste waarden, prohibition `distribute`+`transfer`, geen assignee, `mysolido:policy` in het record, samenvatting op de detailpagina (acht tekstfragmenten), ruwe JSON zichtbaar, "Vastgelegd op dd-mm-jjjj", GET-route `application/ld+json`; gericht aanbod zonder doorleververbod → assignee = `targetedParty.@id` met `rdfs:label`, geen prohibition, samenvatting begint met de partijnaam; intentie zonder attributen geweigerd met melding; policybestand verwijderen → knop zichtbaar → `POST policy/create` maakt hem opnieuw; listing, zoeken en overzicht tonen het bestand niet; verwijderen van de intentie neemt de Offer mee; opruimen.
- `--phase demo` (`1411`) en de volledige run (`1425`) nemen de fase mee.

### `scripts/regressietest.md`
Rij 13c aangevuld (`@id`, policybestanden), nieuwe rij 13d (`67`), paragraaf over `--phase demo` noemt 13a t/m 13d (`91-93`).

---

## 3. Voorbeeld: de Offer voor de demo-intentie

Gegenereerd met `build_intention_policy()` op jouw record `a0ac025c-0521-42cc-bb0e-d68f943cff70` (droog, zonder het bestand te schrijven; dat doe je zelf met "Voorwaarden opstellen", zie §4). Dit is exact wat dan in `intenties/a0ac025c-0521-42cc-bb0e-d68f943cff70.policy.jsonld` komt:

```json
{
  "@context": [
    "http://www.w3.org/ns/odrl.jsonld",
    {
      "dpv": "https://w3id.org/dpv#",
      "rdfs": "http://www.w3.org/2000/01/rdf-schema#"
    }
  ],
  "@type": "Offer",
  "uid": "urn:mysolido:policy:intention:a0ac025c-0521-42cc-bb0e-d68f943cff70",
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
            "@value": "2026-10-04T08:56:20.437971+00:00"
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
      "action": [
        "distribute",
        "transfer"
      ]
    }
  ]
}
```

Bijbehorende samenvattingszin op de detailpagina:

> Iedereen die deze voorwaarden accepteert mag leeftijdscategorie, postcodegebied, voertuigtype en schadeverleden gebruiken, uitsluitend voor offerteberekening, tot 04-10-2026, en mag ze niet doorleveren.

Ter vergelijking een gericht aanbod zonder doorleververbod met twee attributen (uit de testrun): de permission krijgt `"assignee": {"@id": "urn:mysolido:party:<hex>", "rdfs:label": "Verzekeraar X"}`, er is geen `prohibition`, en de zin luidt "Verzekeraar X mag voertuigtype en postcodegebied gebruiken, uitsluitend voor offerteberekening, tot 27-09-2026."

---

## 4. Uitkomst regressietest

Tegen de lopende CSS 7.2.0 en een voor de test gestarte Flask, scenario U.

| Run | Opdracht | Resultaat |
|---|---|---|
| 1 | `--phase demo` (eerste keer) | 45 geslaagd, **2 gefaald**: de oude intentiefase telde het nieuwe policybestand als tweede record (§1 punt 5). Test aangepast, achtergebleven testrecord opgeruimd |
| 2 | `--phase demo` (na aanpassing) | **48 geslaagd, 0 gefaald**, 2 info, 2 s |
| 3 | volledige run `--scenario U` | **141 geslaagd, 0 gefaald**, 2 niet automatiseerbaar (bekend: WebID-token op http, scp naar Bridge), 32 info, 8 s. Alle bestaande fasen groen |

Fasen van run 3: Preflight, Accountcreatie, WebID en credentials, Bestanden en roundtrip, Identifier-normalisatie, WAC/ACL, Deellinks, ODRL-beleid, Toestemmingen en consentrequests, Demodata, Profielvelden, Intentie, **Intentiepolicy**, Backup en restore, /debug, Probes 7.2.0, Bridge-sync module, Persistentie aanmaken, Opruimen. Ruwe uitvoer van run 3 en run 2 in de bijlage.

Aanvullend in de browser bekeken (127.0.0.1:5000): jouw intentie `a0ac025c` toont de kaart "Voorwaarden (ODRL-aanbod)" met de melding en de knop "Voorwaarden opstellen" (niet geklikt); een tijdelijke testintentie toonde samenvatting, uitklapbare JSON, link naar het bestand en "Vastgelegd op 20-09-2026"; het formulier springt bij *Autoverzekering* op "2 weken". De testintentie is daarna verwijderd.

---

## 5. Handmatige controle (niet uitgevoerd, voor jou)

Start Flask (`python app.py`), open `http://127.0.0.1:5000`.

1. **Bestaande intentie zonder policy.** *Profiel → Mijn intenties → Autoverzekering* (jouw intentie van vanochtend, "ik zoek een allrisk verzekering…"). Verwacht: kaart **Voorwaarden (ODRL-aanbod)** met "Voor deze intentie zijn nog geen voorwaarden opgesteld." en de knop **Voorwaarden opstellen**. Klik erop. Verwacht: groene melding "Voorwaarden opgesteld.", in de kaart de zin uit §3, daaronder "Bekijk ruwe ODRL policy (JSON-LD)" uitklapbaar en de link "Bekijk als bestand (JSON-LD)" die de Offer als `application/ld+json` opent. Op schijf staat nu `.data\mysolido\intenties\a0ac025c-….policy.jsonld` en het record bevat `"mysolido:policy": "urn:mysolido:policy:intention:a0ac025c-…"`. Verder onderaan: "Vastgelegd op 20-09-2026; …".
2. **Weigering en gericht aanbod.** *Nieuwe intentie*: kies **Autoverzekering**; de geldigheidsduur springt op **2 weken**. Vink alle vier de voorgeselecteerde gegevens uit, vul een omschrijving in en sla op: rode melding "Vink minstens één ingevuld gegeven aan…", er is niets aangemaakt. Vink de vier weer aan, kies **Gericht aanbod**, naam "Verzekeraar X", laat doorlevering aangevinkt, sla op en open de intentie. Verwacht: zin "Verzekeraar X mag leeftijdscategorie, postcodegebied, voertuigtype en schadeverleden gebruiken, uitsluitend voor offerteberekening, tot <datum over 2 weken>, en mag ze niet doorleveren."; in de JSON een `assignee` met `@id` `urn:mysolido:party:…` en `rdfs:label` "Verzekeraar X", dezelfde `@id` als `mysolido:targetedParty.@id` in het record. Klik daarna **Verwijderen**: in `.data\mysolido\intenties\` zijn record én `.policy.jsonld` van deze testintentie weg.
3. **Onzichtbaar in de kluis.** Open `http://127.0.0.1:5000/browse/intenties` (systeemmap, niet in het mappenrooster): alleen `a0ac025c-….jsonld` staat in de lijst, geen `.policy.jsonld`. Zoek via de zoekbalk op "policy": geen treffer uit `intenties/`. *Mijn intenties* toont alleen echte intenties. Facultatief, vooruitlopend op subtaak 5: start `python app.py --bridge`, log in en open dezelfde intentie: de kaart met samenvatting en JSON is zichtbaar, de knop "Voorwaarden opstellen" niet, en `/intenties/a0ac025c-…/policy.jsonld` levert de JSON-LD.

---

## 6. Buiten dit verslag

**Bewust niet gedaan.** `build_policy()`, `policy_summary_nl()`, `detect_policy_rule()`, `init_default_policies()`, mappolicies en `policy_edit.html` alleen gelezen. Verzoeken, consent, `verzoek_approve()`, de dode comment (nu `app.py:4342`), `APPROVAL_VALIDITY`, DPV-statustermen: subtaak 4. Bridge-code, `sync_bridge.py`, VPS: subtaak 5 (niet gedraaid in Bridge-modus). Profielopslag, seed-script, CSS, startscripts, installers, `package.json`, backup-export, `.env` (alleen gelezen), README, trustpagina: ongewijzigd. Jouw intentie `a0ac025c` is niet aangeraakt: geen Offer geschreven, geen `mysolido:policy` gezet. Geen ODRL-validator gedraaid; de vorm is tegen de ODRL 2.2-termen uit `build_policy()` en de specificatienamen gecontroleerd, niet machinaal gevalideerd.

**Tegengekomen, voor subtaak 4.**
- Alles wat het verzoekformulier nodig heeft staat klaar: `GET /intenties/<uuid>/policy.jsonld` (Offer), `record['mysolido:policy']` (uid), `record['mysolido:targetedParty']['@id']` (partij), `intention_policy_summary_nl()` (zin). Een Agreement is de Offer met `@type` `Agreement`, uid `urn:mysolido:agreement:<verzoek-uuid>`, `assignee` = de wederpartij en dezelfde permission/prohibition.
- De GET-route vereist eigenaarslogin (Bridge) en is lokaal open; als de wederpartij de voorwaarden op het publieke verzoekformulier moet zien, moet dat formulier de Offer zelf inlezen (server-side) of moet er een publieke variant komen. Ontwerpkeuze voor 4.
- "Voorwaarden opstellen" schrijft de Offer opnieuw uit het record; zolang het record niet verandert is het resultaat identiek. Bij acceptatie in subtaak 4 is het verstandig de geaccepteerde Offer te kopiëren of te hashen in het verzoek (`mysolido:acceptedPolicy` + kopie), zodat een latere herschrijving de bewijsketen niet raakt.
- De `assigner` is de lokale WebID `http://127.0.0.1:3000/mysolido/profile/card#me`. In een Agreement die de verzekeraar bewaart, verwijst die naar een adres dat alleen op jouw pc bestaat. Zie de vragen.

**Tegengekomen, voor subtaak 5.**
- `sync_bridge.py` kopieert met `scp -r`; `<uuid>.policy.jsonld` is een gewoon bestand en gaat mee. De Bridge toont de kaart alleen-lezen zodra de VPS de nieuwe code heeft; de GET-route werkt daar na Bridge-login. Niet getest.
- Op de Bridge verschijnt bij een record zonder Offer alleen de melding, geen knop; de Offer moet dus op de pc worden opgesteld vóór de sync.

**Tegengekomen, voor de andere lijsten.**
- Datumnotatie op de intentiepagina is nu gemengd (`dd-mm-jjjj` bij "Vastgelegd op" en in de zin, `jjjj-mm-dd` bij "Aangemaakt"/"Geldig tot" en in het overzicht). Eén afspraak voor de hele app hoort op de kleine-puntenlijst.
- Ruwe JSON in de browser staat alfabetisch door `tojson`; wie de volgorde uit het bestand wil zien, kan `json.dumps` in de route doen in plaats van het filter. Geldt ook voor `policy_edit.html`.
- `int_share_data_desc` in `translations.py` blijft ongebruikt (al gemeld in subtaak 2).
- Het ongetrackte bestand `tatus --short` in de repo-root (§1 punt 10).
- De `validThrough` in de Offer draagt microseconden (`…20.437971+00:00`); geldig `xsd:dateTime`, maar de Flask-vervalcontrole van verzoeken werkt op hele seconden. Cosmetisch.

**Vragen die alleen jij kunt beantwoorden.**
1. Moet de `assigner` de lokale WebID blijven (eerlijk over wat er draait) of wil je voor de demo een publieke identifier (bijv. de Bridge-URL of `urn:mysolido:owner`) zodat de Offer op de telefoon en bij de verzekeraar niet naar `127.0.0.1` wijst?
2. Wil je "Voorwaarden opstellen" ook aanbieden als er al een Offer is (opnieuw genereren na een wijziging), of bewust alleen bij een ontbrekend bestand zoals nu?
3. Moet de wederpartij de Offer straks kunnen ophalen zonder eigenaarslogin (publieke leesroute of inbedding in het verzoekformulier)? Bepaalt de vorm van subtaak 4.
4. `permission.action` is `use` (zoals de opdracht zegt). ODRL kent ook `read`; `use` is breder en dekt "berekenen". Akkoord, of liever `read` naast de `.acl`-terminologie van de kluis?
5. Mag het bestand `tatus --short` weg?

---

## Bijlage: ruwe uitvoer

### Run 3: `python scripts/regressietest.py --scenario U` (volledige run)

```
MySolido regressietest 2026-09-20 11:47 -- scenario U, fase all, CSS http://127.0.0.1:3000 (7.2.0), Flask http://127.0.0.1:5000, Pod http://127.0.0.1:3000/mysolido/

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
  [PASS] Test-Pod aanmaken  -- http://127.0.0.1:3000/regressietest-pod-1a81ef/
  [PASS] Test-Pod staat op schijf als .data/<podnaam>/  -- C:\Users\Wim\mysolido\.data\regressietest-pod-1a81ef
  [PASS] Test-WebID publiek bereikbaar met solid:oidcIssuer  -- http://127.0.0.1:3000/regressietest-pod-1a81ef/profile/card#me
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
  [PASS] Consentrequest: JSON-LD velden correct en statustoken in bevestiging  -- c0e7964d-eb5f-47e8-936c-9957ccb19f46
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
  [PASS] Intentiepolicy: intenties/<uuid>.policy.jsonld geschreven  -- d8786648-6507-4552-b703-0474a599448f.policy.jsonld
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

== Backup en restore ==
  [PASS] Backup: zip-export  -- 5641 bytes
  [PASS] Backup: bevat testbestand met juiste inhoud  -- regressietest/ldp/roundtrip.txt
  [INFO] Backup: .policy.jsonld en .acl in zip  -- nee, dotfiles en .acl worden overgeslagen
  [INFO] Backup: .mysolido/share_links.json in zip  -- nee
  [PASS] Restore: bestand uit zip teruggezet en via CSS leesbaar

== Flask /debug (HTTP-laag) ==
  [PASS] Flask /debug: HTTP-lezing van Pod-root via CSS (root is publiek)

== Probes 7.2.0-changelog ==
  [INFO] Probe dubbele slug: twee POSTs met Slug slug-test.txt  -- 201 http://127.0.0.1:3000/mysolido/regressietest/ldp/slug-test.txt | 201 http://127.0.0.1:3000/mysolido/regressietest/ldp/6f5a46f3-6e4c-4fc7-8f77-e2985d82bc3c; op schijf ['slug-test.txt']
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
  [PASS] Opruimen: verzoeken/ verwijderd (bestond niet voor de test)
  [PASS] Opruimen: .mysolido/ verwijderd (bestond niet voor de test)
  [INFO] Opruimen: testaccount verwijderen via account-API  -- geen account-URL in controls
  [PASS] Opruimen: test-Pod-map van schijf verwijderd  -- C:\Users\Wim\mysolido\.data\regressietest-pod-1a81ef
  [INFO] Opruimen: runtime-bestanden in projectmap (trash.json, shares.json, audit_log.json, notifications.json)  -- blijven staan, vallen onder .gitignore

Resultaat: 141 geslaagd, 0 gefaald, 2 niet automatiseerbaar, 32 info (8s)
```

### Run 2: `python scripts/regressietest.py --phase demo` (na aanpassing van de intentiefase)

```
MySolido regressietest 2026-09-20 11:47 -- scenario U, fase demo, CSS http://127.0.0.1:3000 (7.2.0), Flask http://127.0.0.1:5000, Pod http://127.0.0.1:3000/mysolido/

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
  [PASS] Intentiepolicy: intenties/<uuid>.policy.jsonld geschreven  -- de32d166-2869-4943-a5e2-8045c60dd34e.policy.jsonld
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

Resultaat: 48 geslaagd, 0 gefaald, 0 niet automatiseerbaar, 2 info (2s)
```
