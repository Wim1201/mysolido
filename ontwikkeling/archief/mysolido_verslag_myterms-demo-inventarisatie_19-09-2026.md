# MySolido — Inventarisatie bouwstenen MyTerms-demo en scenario-script

| | |
|---|---|
| **Datum** | 19 september 2026 |
| **Softwareversie** | branch `main`, commit `810fef5` (14-09-2026, "macOS-bouwinstructies: CSS-versie uit package.json en start via server.js"); laatste tag `v1.3.0` (11-04-2026) |
| **Omgeving** | Windows 10, hoofdcheckout `C:\Users\Wim\mysolido`; `package.json` pint `@solid/community-server` op `7.2.0` (gecontroleerd); `.data/mysolido/` bevat op deze datum alleen het CSS-Pod-sjabloon (`.acl`, `.meta`, `README$.markdown`, `README.acl`, `profile/`), geen standaardmappen, geen `profiel/`, `intenties/`, `toestemmingen/` of `verzoeken/` |
| **Brondata (alleen gelezen)** | `app.py` (4035 regels: constanten 628-830, policy 2276-2476, consent 2479-2762, profiel 2765-2902, intenties 2905-3347, verzoeken 3350-3807, opstart 3995-4035), `sync_bridge.py`, `share_links.py`, `shares.py`, `audit.py`, `templates/intentie_nieuw.html`, `intentie_detail.html`, `consent_form.html`, `consent_detail.html`, `verzoek_formulier.html`, `verzoek_detail.html`, `verzoek_response.html`, `policy_edit.html`, `profiel_data.html`, `base.html`, `index.html`, `profile.html`, `translations.py` (formulierteksten), `scripts/regressietest.py` (fasen policy, consent, bridge) en `regressietest.md`, `docs/css-koppelvlakken.md`, `README.nl.md`, `MySolido_Roadmap_Policylaag_v1.md`, `docs/MySolido_Koersdocument_Modus.md`, `prompt_mysolido_bridge_test.md`, `.env` (alleen de niet-geheime sleutels `SOLID_POD_URL`, `CSS_BASE_URL`, `WEBID`, `SHARE_BASE_URL`, `BRIDGE_AUTO_SYNC`), git-tags en -log. Extern: de DPV-gids "ISO/IEC TS 27560 to DPV mapping" (w3c-cg.github.io/dpv/guides/consent-27560) voor de veldvergelijking in paragraaf 4 |
| **Vervolg op** | `docs/css-koppelvlakken.md` (14-09-2026); regelnummers hieronder verwijzen naar commit `810fef5` en verschuiven bij latere wijzigingen |
| **Werkwijze** | Geen code gewijzigd, geen servers gestart, geen testruns, geen bestanden buiten `docs/`, geen git-wijzigingen. Feiten zijn uit de code gelezen; vermoedens staan als zodanig gemarkeerd |

---

## 1. Correcties op de planning

De planning ("de bouwstenen bestaan al sinds v1.2; de taak rijgt ze aaneen") klopt op de datering en op de losse modules, maar niet op de samenhang. Wat er in de code staat:

1. **De datering klopt.** Profielmodule (`9829c62`), intentiemodule (`befebfa`) en consentverzoeken (`bbedefd`) zijn op 3 april 2026 gecommit; ODRL-policies en de consentmodule (`68b9076`) op 2 april; tag `v1.2.0` staat op 4 april. "Sinds v1.2" is juist.

2. **De modules verwijzen niet naar elkaar.** Een intentie bevat geen policy-verwijzing, een verzoek verwijst niet naar een intentie, een goedkeuring maakt geen toestemming aan, en een toestemmingsrecord kent geen intentie, verzoek of policy. De keten intentie → gegevensselectie → policy → acceptatie → consentrecord bestaat nergens als geheel. De losse schakels zijn er, de verbindingen zijn allemaal nog te maken.

3. **Goedkeuren van een verzoek schrijft geen consentrecord.** In `verzoek_approve()` (`app.py:3691-3768`) staat op regel 3745 het commentaar "Create consent record (using existing consent module pattern)", gevolgd door alleen een flash-melding en een logregel. Er wordt geen bestand in `toestemmingen/` geschreven. De README-belofte "elke toestemming wordt geregistreerd conform ISO 27560" (README.nl.md:213) geldt alleen voor records die de eigenaar handmatig via `/consent/new` aanmaakt. De regressietest test bij verzoeken uitsluitend het afwijzen (`regressietest.py:740`); het goedkeuringspad is nooit geautomatiseerd getest.

4. **Er is geen weg terug van de Bridge naar de pc.** `sync_bridge.py` is één richting (pc → Bridge, `scp -r`, regel 4 en 90-104). Het publieke verzoekformulier op de Bridge schrijft in de Bridge-kopie van de Pod (`verzoek_submit()`, `app.py:3484-3559`, via `pod_write`). De eigenaarroutes voor verzoeken geven op de Bridge `403` (`app.py:3640, 3661, 3694, 3774`). Een verzoek dat op de Bridge binnenkomt, bereikt de pc dus nooit; README-stap 2 "Uw klant ziet het verzoek in zijn MySolido-kluis" (README.nl.md:210) heeft geen implementatie. Dit bepaalt de haalbaarheid van subtaak 5, zie paragraaf 3.

5. **De ODRL-generator kent vier vaste mapregels, geen policy op maat.** `build_policy()` (`app.py:2332-2386`) maakt per map een `odrl:Set` met de keuze eigenaar / lezen / lezen-niet-downloaden / tijdelijk. "Tijdelijk" is hard 30 dagen (regel 2380). Er is geen doelbinding (`purpose`), geen benoemde wederpartij, geen termijn naar keuze en geen target op veldniveau; het target is altijd `urn:mysolido:container:<map>`. De `dpv`-prefix wordt in de context gedeclareerd maar nergens in de policy gebruikt. Per intentie of toestemming wordt geen policy gemaakt; `intenties/.policy.jsonld` en `verzoeken/.policy.jsonld` zijn vaste eigenaar-only mappolicies (`app.py:3109-3132`, `3439-3462`).

6. **Het profiel mist twee van de vier scenariovelden.** Het profielformulier (`profiel_data.html`, opslag `app.py:2783-2902`) kent woonsituatie, gezin, voertuig (type/brandstof/bouwjaar), verzekeringen, werk en gezondheid. *Leeftijdscategorie* van de eigenaar ontbreekt (alleen leeftijdscategorieën van kinderen bestaan). *Schadeverleden* ontbreekt. *Postcodegebied* bestaat alleen als vrij tekstveld "Regio / provincie" (`pd:Location`, placeholder "Bijv. Noord-Brabant"). *Voertuigtype* bestaat (auto/motor/scooter/fiets/geen). Gegevensselectie in intentie en goedkeuring gaat bovendien per groep (zes checkboxes), niet per veld: wie "Voertuigen" aanvinkt deelt ook brandstof en bouwjaar.

7. **Het consentrecord is een DPV-record, geen ISO 27560-structuur.** Zie paragraaf 4. Twee statuswaarden in de code, `dpv:ConsentStatusGiven` en `dpv:ConsentStatusWithdrawn` (`app.py:2530, 2643, 2729`), bestaan niet in DPV; DPV kent `dpv:ConsentGiven` en `dpv:ConsentWithdrawn` (gecontroleerd in de DPV-27560-gids). De regressietest verwacht de huidige, onjuiste waarde (`regressietest.py:686, 706`).

8. **Op de Bridge is de policy-pagina geblokkeerd.** `edit_policy()` stuurt in Bridge-modus door naar het dashboard (`app.py:2440-2442`). De ruwe ODRL-JSON is alleen op die pagina te zien; op de telefoon blijft daarvan alleen de samenvattingsbadge over. Het eerdere demodoel "de ODRL policy op een container tonen op de iPhone" (prompt_mysolido_bridge_test.md) is met de huidige code niet als JSON mogelijk.

9. **Kleinere afwijkingen.** Het koersdocument noemt CSS v7.1.9; de repo staat sinds 14-09 op 7.2.0. De lokale Pod in de hoofdcheckout is leeg (zie kop), dus er is nog geen demodata; door de bekende welkomstscherm-bug (`docs/css-koppelvlakken.md`, "Bekende tekortkomingen") worden de standaardmappen ook niet automatisch aangemaakt.

---

## 2. Inventaris per bouwsteen

Feiten uit de code. Vermoedens staan cursief met "(vermoeden)".

| Bouwsteen | Waar in de code | Wat er staat | Wat er voor dit scenario ontbreekt |
|---|---|---|---|
| **Intentie** | `INTENTION_CATEGORIES`, `VALIDITY_OPTIONS` (`app.py:2905-2924`); `intentie_new()` (`3162-3233`); detail/activeren/intrekken/verwijderen (`3236-3347`); `templates/intentie_nieuw.html`, `intentie_detail.html`; opslag `intenties/<uuid>.jsonld` | Categorie `autoverzekering` bestaat (voorselectie groepen `vehicle`, `insurance`). Geldigheid 1w / **2w (14 dagen)** / 1m / 3m. Vrije omschrijving. Status concept → actief → ingetrokken/verlopen (`check_expired_intentions`, `3080-3106`). Record `mysolido:Intention` met `schema:validThrough` en `mysolido:sharedProfileData` (per groep `included` + kopie van de data). Tekst bij opslaan: "wordt alleen lokaal opgeslagen, er wordt niets gedeeld of verzonden" | Geen doelveld (offerteberekening), geen doorleververbod-vlag, geen selectie per veld, geen verwijzing naar een policy. De datakopie in het record is een momentopname; bij profielwijziging wijkt de intentie af van het profiel (detailpagina toont overigens het *huidige* profiel, `3260-3262`) |
| **Profiel / gegevensselectie** | `profiel_data()` en `profiel_data_save()` (`app.py:2765-2902`); `load_profile_data()` (`2931-2940`); `extract_profile_groups()` (`2943-3055`); `templates/profiel_data.html`; opslag `profiel/profiel.jsonld` + vaste `profiel/.policy.jsonld` | JSON-LD `dpv:PersonalData` met `pd:`-termen; zes groepen: housing (`pd:HousingOwnership`, `mysolido:housingType`, `pd:Location`), household, vehicle (`type`, `fuel`, `yearBuilt`), insurance (lijst `type`/`provider`/`endDate`), occupation, health (`smokingStatus`; huisartspraktijk wordt bewust *niet* in de groep opgenomen, `3038`). Op de Bridge alleen-lezen (`read_only=BRIDGE_MODE`) | Velden **leeftijdscategorie** en **schadeverleden** ontbreken; **postcodegebied** alleen als vrije tekst "Regio / provincie"; **voertuigtype** aanwezig. Geen selectie op veldniveau, alleen per groep. *(vermoeden)* Enkele `pd:`-termen (`pd:HousingOwnership`, `pd:HouseholdSize`, `pd:Vehicle`, `pd:Insurance`, `pd:HealthData`) zijn niet tegen DPV-PD gecontroleerd |
| **ODRL-policy** | `get_container_policy()`, `policy_summary_nl()`, `build_policy()`, `detect_policy_rule()`, `init_default_policies()`, `edit_policy()` (`app.py:2276-2476`); `templates/policy_edit.html`; opslag `<map>/.policy.jsonld`; aanmaak bij start (`4024`) | `odrl:Set`, `uid` `urn:mysolido:policy:<map>`, `profile` ODRL core, permission eigenaar read/write/delete, prohibition `distribute`; vier regels waarvan "temporal" een `dateTime lteq`-constraint van vast 30 dagen zet. Assignees `urn:mysolido:owner` / `urn:mysolido:anyone`, target `urn:mysolido:container:<map>`. Nederlandse samenvatting via `policy_summary_nl()`. Getest in `regressietest.py` fase 11 | Geen `purpose`-constraint, geen wederpartij als assignee, geen termijn naar keuze, geen target per gegevensveld, geen `odrl:Offer`/`odrl:Agreement`-vorm, geen policy per intentie of toestemming. Pagina op de Bridge geblokkeerd, dus geen leesweergave op de telefoon. Handhaving: alleen de tijdconstraint van het verzoek wordt in Flask gecontroleerd (`verzoek_response`, `3608-3616`); mappolicies worden nergens afgedwongen, alleen getoond |
| **Verzoek van buitenaf** (vraagkant) | `REQUEST_CATEGORIES`, `APPROVAL_VALIDITY` (`app.py:3350-3366`); `verzoek_submit()` (`3484-3559`); status- en responspagina (`3562-3634`); eigenaarroutes (`3637-3807`); `templates/verzoek_formulier.html`, `verzoek_detail.html`, `verzoek_response.html`; opslag `verzoeken/<uuid>.jsonld` en `<uuid>_response.json` | Publiek formulier (ook op de Bridge, `check_bridge_auth` `743-761`): naam, organisatie, e-mail, categorie (o.a. verzekeringen), gevraagde groepen, doel (vrije tekst), akkoordvinkje. Record `mysolido:ConsentRequest` met statustoken. Eigenaar ziet verzoek op de pc, keurt goed (kiest groepen + geldigheid 1d/1w/1m/3m) of wijst af. Goedkeuring schrijft `_response.json` met de volledige goedgekeurde groepen en zet `responseLink` + `validUntil`; de responspagina controleert de vervaldatum | Verzoek verwijst niet naar een intentie of policy; het akkoordvinkje ("alleen voor het opgegeven doel en akkoord met de voorwaarden") is generiek, niet gebonden aan een concrete policy-`uid`. Geldigheid 14 dagen ontbreekt in `APPROVAL_VALIDITY` (wel in `VALIDITY_OPTIONS`). Response bevat hele groepen, niet de vier velden. Geen transport Bridge → pc |
| **Acceptatie** | Twee plekken: `agreed_terms` in `verzoek_submit()` (`3504, 3518-3520`, opgeslagen als `mysolido:agreedToTerms: true`) en `verzoek_approve()` (`3691-3768`) | Wederpartij accepteert generieke voorwaarden bij indienen; eigenaar keurt goed op de pc. Beide worden gelogd (`audit.py`, `audit_log.json` in de *projectmap*, niet in de Pod) | Geen vastlegging van *welke* voorwaarden (policy-`uid`, versie, tijdstip) de wederpartij accepteerde; geen `odrl:Agreement`; geen consentrecord als gevolg van de goedkeuring (dode comment `3745`) |
| **Consentrecord** | `PURPOSE_MAP`, `DATA_CATEGORY_MAP` (`app.py:2479-2496`); `load_all_consents()`, `get_consent_status_display()`, `get_consent_stats()`, `generate_consent_id()` (`2499-2580`); `consent_list/new/detail/withdraw/delete` (`2583-2762`); `templates/consent_form.html`, `consent_detail.html`; opslag `toestemmingen/<YYYYMMDD-NNN>.jsonld` | Handmatig formulier: titel, omschrijving, ontvanger (naam), doel (7 vaste keuzes, `insurance` = "Verzekering", `dpv:ServiceProvision`), gegevenscategorie (6 vaste keuzes, één per record), vervaldatum, notitie. Record `dpv:ConsentRecord` met `dct:created/modified`, `dpv:hasDataSubject`, `hasDataController` (willekeurige `urn:mysolido:party:<hex>` + naam), `hasPurpose`, `hasPersonalDataCategory`, `hasConsentStatus`, `hasLegalBasis`, `hasRight`, optioneel `hasExpiry`. Intrekken zet status en `modified`. Detailpagina toont velden en ruwe JSON; op de Bridge leesbaar zonder knoppen. Getest in `regressietest.py` fase 12 | Geen koppeling aan intentie, verzoek of policy; geen veldenlijst (vier velden), alleen één categorie; geen doorleververbod-veld; geen ISO 27560-structuur (paragraaf 4); statustermen onjuist; geen gebeurtenisgeschiedenis (gegeven → ingetrokken overschrijft) |
| **Weergave via de Bridge** | `BRIDGE_MODE` (`app.py:41`); `check_bridge_auth()` (`743-761`); `check_bridge_mode()` (`764-786`); per-route `if BRIDGE_MODE` (o.a. `2440, 2605, 2710, 2742, 2786, 3165, 3273, 3301, 3329, 3640-3774`); `read_only`/`bridge_mode` in templates; `sync_bridge.py`; nav in `base.html:52-57, 77-80` | Zelfde Flask met `--bridge`, wachtwoordlogin, schrijfroutes geblokkeerd. Leesbaar op de telefoon: dashboard met consentstatistieken (`index.html:74-79`) en policybadges (`93-94`), `/consent` en `/consent/<id>`, `/intenties` en `/intenties/<id>`, `/profiel-data` (uitgeschakelde velden), `/profile`. Sync: handmatig (`/bridge-sync`) of automatisch na wijzigingen (`auto_sync_after_change`, alleen aangeroepen bij bestandsacties en deellinks, `1210-1644`; **niet** bij intentie-, consent- of policywijzigingen) | Policy-JSON niet zichtbaar; `/verzoeken` niet bereikbaar; geen retourkanaal; auto-sync dekt de demo-modules niet, dus na elke stap handmatig syncen. Logboek op de Bridge is het eigen `audit_log.json` van de VPS, niet dat van de pc (projectmap wordt niet gesynchroniseerd) |
| **Access control (ter contrast)** | `build_acl_content()`, `write_acl()`, `/share`, `/revoke` (`app.py:1449-1536, 1650-1669`); `shares.py`; deellinks `share_links.py`, `/share/<token>` (`1580-1634`) | WAC-`.acl` naast bestanden en mappen, tokendeellinks met wachtwoord/vervaldatum/watermerk. Getest in fasen 9 en 10 | Voor het scenario niet nodig: de vier velden gaan niet als bestand de deur uit maar als responspagina. Wel het aanknopingspunt om in de demo het onderscheid *access control* (`.acl`, CSS) versus *usage control* (`.policy.jsonld`, Flask) te laten zien |

---

## 3. Acceptatie en consentrecord als de demo via de Bridge loopt

**Feiten.**
- De Bridge is dezelfde Flask-app met `--bridge` op een kopie van `.data/<pod>/` (`docs/css-koppelvlakken.md` §10). Alle eigenaarroutes die iets schrijven zijn geblokkeerd of geven `403`: intentie aanmaken/activeren/intrekken, policy bewerken, toestemming aanmaken/intrekken/verwijderen, profiel opslaan, verzoek goedkeuren/afwijzen.
- De enige routes die op de Bridge schrijven zijn het publieke verzoekformulier en de crash-rapportage. Ze schrijven in de Bridge-kopie op de VPS.
- De sync is `scp -r` van pc naar Bridge; bestanden met dezelfde naam worden overschreven, bestanden die alleen op de Bridge staan blijven daar staan. Er is geen code die iets van de Bridge terughaalt.
- Flask bindt lokaal alleen op `127.0.0.1:5000` (`app.py:4035`, geen `host`-parameter); de telefoon kan de pc-versie dus niet via het LAN bereiken zonder codewijziging.

**Antwoord.** Als de demo op de telefoon via de Bridge loopt, kan de telefoon níets accepteren en níets vastleggen. Acceptatie door de eigenaar en het schrijven van het consentrecord gebeuren uitsluitend op de pc, in `.data/mysolido/toestemmingen/` (na bouw van subtaak 4). De telefoon toont daarna de gesynchroniseerde kopie. Een verzoek dat een wederpartij op de Bridge indient, komt niet op de pc aan.

**Gevolg voor subtaak 5.** "End-to-end via Bridge op telefoon" is met de huidige architectuur niet haalbaar zoals bedacht. Drie varianten, oplopend in bouwwerk:

| Variant | Wat | Bouwwerk | Wat de demo laat zien |
|---|---|---|---|
| **A. Twee schermen** | Eigenaarstappen (intentie, selectie, policy, acceptatie, consentrecord) op de pc; na elke stap `/bridge-sync`; de telefoon toont intentie, policy en consentrecord alleen-lezen. De vraagkant (verzekeraar) wordt op de pc gesimuleerd of via het lokale `/verzoek`-formulier ingevoerd | Geen nieuwe transportlaag. Wel: leesweergave van de policy op de Bridge (nu geblokkeerd) en de subtaken 2-4 | De hele keten, waarbij de telefoon de rol "kluis in je zak, bewijs van de afspraak" speelt. Eerlijk over wat de Bridge is: een spiegel |
| **B. Retourkanaal** | Verzoeken die op de Bridge binnenkomen naar de pc halen (bijv. `scp` van alleen `verzoeken/` terug, of een Flask-endpoint op de Bridge dat nieuwe verzoeken met token uitlevert en dat de pc pollt) | Nieuwe module + beveiliging + conflictregels (wat als een verzoek op beide plekken bestaat). Aparte taak, groter dan de demo | Vraagkant echt vanaf een tweede telefoon of laptop via `bridge.mysolido.com/verzoek` |
| **C. Alles lokaal, telefoon in het LAN** | Flask op `0.0.0.0` binden en de pc-versie op de telefoon openen | Kleine codewijziging, maar doorbreekt het uitgangspunt "de pc-versie is alleen lokaal bereikbaar" en de Bridge speelt geen rol | Eigenaar kán dan op de telefoon accepteren, maar het is geen Bridge-demo meer |

Voorstel: A voor de demo van september/oktober, B als aparte ClickUp-taak in "Straks". Keuze is aan jou (zie paragraaf 7).

---

## 4. Is er al iets dat op ISO/IEC TS 27560 lijkt?

**Kort:** er is een DPV-consentrecord (`dpv:ConsentRecord`) dat ongeveer een derde van de 27560-velden dekt. De 27560-structuur zelf (kop, verwerkingsdeel, gebeurtenis, partijen) moet nog worden gemaakt. Omdat DPV een officiële mapping op 27560 publiceert, kan het record DPV-vocabulaire houden en toch 27560-volledig worden.

Vergelijking van de 27560-velden (volgens de DPV-27560-gids) met het huidige record uit `consent_new()` (`app.py:2624-2660`):

| 27560-veld | DPV-equivalent | In het huidige record | Voor het scenario |
|---|---|---|---|
| `schema_version` | `dct:conformsTo` | ontbreekt | toevoegen (verwijzing naar 27560 + eigen profielversie) |
| `record_id` | `dpv:hasIdentifier` / `@id` | `@id` = `urn:mysolido:consent:YYYYMMDD-NNN` | aanwezig |
| `pii_principal_id` | `dpv:hasDataSubject` | `urn:mysolido:owner` | aanwezig; WebID zou logischer zijn |
| `privacy_notice`, `language` | `dpv:hasNotice`, `dct:language` | ontbreekt | optioneel |
| `purpose` (+ `purpose_type`, `lawful_basis`) | `dpv:hasPurpose`, `dpv:hasLegalBasis` | `hasPurpose` = vaste keuze (bij verzekering `dpv:ServiceProvision`, "Verzekering"); `hasLegalBasis` = `dpv:Consent` | doel moet "offerteberekening" worden, niet "Verzekering"; tekst + DPV-type |
| `pii_information` (lijst attributen) | `dpv:hasPersonalData` | `dpv:hasPersonalDataCategory` met één categorie (bijv. `dpv:Financial`) | lijst van precies vier attributen nodig: leeftijdscategorie, postcodegebied, voertuigtype, schadeverleden. *(vermoeden)* `hasPersonalDataCategory` is een DPV-1-term; DPV 2 gebruikt `hasPersonalData` |
| `pii_controllers` | `dpv:hasDataController` | naam + willekeurige urn | partij-id, rol en contact ontbreken |
| `storage_locations`, `retention_period` | `dpv:hasStorageCondition` | ontbreekt | bewaartermijn = 14 dagen, vastleggen |
| `recipient_third_parties` | `dpv:hasRecipient` | ontbreekt | **doorleververbod** hoort hier expliciet: geen derden, plus verwijzing naar de ODRL-prohibition |
| `jurisdiction` | `dpv:hasJurisdiction` | ontbreekt | NL, eenvoudig toe te voegen |
| `event_time` | `dct:date` | `dct:created` / `dct:modified` (alleen laatste stand) | gebeurtenisgeschiedenis nodig: gegeven op, ingetrokken op |
| `event_type` | `dpv:Consent`-type | impliciet (`hasLegalBasis: dpv:Consent`) | expliciete toestemming benoemen |
| `event_state` | `dpv:hasConsentStatus` | `dpv:ConsentStatusGiven` / `…Withdrawn` (**geen DPV-termen**) | corrigeren naar `dpv:ConsentGiven` / `dpv:ConsentWithdrawn` (+ `dpv:ConsentExpired` bij verlopen); regressietest meeveranderen |
| `entity_id` | `dpv:isImplementedByEntity` | ontbreekt | MySolido-instantie / WebID |
| geldigheid | `dpv:hasExpiry` | `dpv:hasExpiry` met `dpv:hasExpiryTime` (alleen als datum ingevuld) | 14 dagen vanaf acceptatie, altijd gevuld |
| rechten | `dpv:hasRight` | `dpv:RightToWithdrawConsent` | aanwezig |
| koppeling aan policy / intentie / verzoek | (buiten 27560) | ontbreekt | nodig om de keten te bewijzen: `odrl`-`uid` van de Agreement, intentie-`@id`, verzoek-`@id` |

Conclusie: "conform ISO 27560" is nu een claim in README en trustpagina, geen eigenschap van de code. Het record is een goede basis; de veldenlijst hierboven is de bouwlijst voor subtaak 4.

---

## 5. Scenario-script

Uitgangspunten: variant A uit paragraaf 3 (eigenaar op de pc, telefoon toont), de wederpartij heet in de demo "Verzekeraar X". Per stap: wat de gebruiker ziet en doet, wat het systeem doet, en welke bouwsteen of welk gat erachter zit. **Gat** betekent: nog te bouwen.

### Stap 0 — Voorbereiding (pc, eenmalig)
- **Gebruiker:** vult op *Profiel → Mijn gegevens* de vier velden in: leeftijdscategorie (bijv. 35-44), postcodegebied (bijv. 5611 of "56xx"), voertuigtype (auto), schadeverleden (bijv. 5 schadevrije jaren, geen claims in 3 jaar).
- **Systeem:** schrijft `profiel/profiel.jsonld` en, als die nog niet bestaat, `profiel/.policy.jsonld` (eigenaar-only).
- **Bouwsteen:** profielmodule. **Gat:** leeftijdscategorie, postcodegebied als afgebakend veld en schadeverleden bestaan niet in formulier, opslag en `extract_profile_groups()`.

### Stap 1 — Intentie uitspreken (pc)
- **Gebruiker:** *Profiel → Mijn intenties → Nieuwe intentie*; kiest "Autoverzekering", omschrijft "Ik zoek een autoverzekering", kiest geldigheid **2 weken**, kiest doel "Offerteberekening" en zet "Doorlevering aan derden: niet toegestaan" aan.
- **Systeem:** schrijft `intenties/<uuid>.jsonld` met status concept, `schema:validThrough` = nu + 14 dagen.
- **Bouwsteen:** intentiemodule (categorie en 2 weken bestaan). **Gat:** doelveld en doorleververbod-vlag ontbreken in formulier en record.

### Stap 2 — Gegevensselectie (pc)
- **Gebruiker:** ziet in hetzelfde formulier de profielgegevens en vinkt precies vier velden aan: leeftijdscategorie, postcodegebied, voertuigtype, schadeverleden. Brandstof en bouwjaar blijven uit.
- **Systeem:** legt in de intentie vast welke attributen gedeeld worden (verwijzingen naar profielvelden, niet per se een kopie).
- **Bouwsteen:** checkbox-selectie in `intentie_nieuw.html` en `mysolido:sharedProfileData`. **Gat:** selectie is per groep; per veld is nodig. De categorie "autoverzekering" kan de vier velden voorselecteren (het mechanisme `profile_fields` bestaat al, `app.py:2906`).

### Stap 3 — Voorwaarden: ODRL-policy genereren (pc)
- **Gebruiker:** klikt "Voorwaarden opstellen" (of dit gebeurt bij opslaan) en ziet een Nederlandse samenvatting: *"Verzekeraar mag leeftijdscategorie, postcodegebied, voertuigtype en schadeverleden gebruiken, uitsluitend voor offerteberekening, tot <datum>, niet doorleveren."* Daaronder de ruwe JSON-LD (uitklapbaar, zoals `policy_edit.html` dat nu doet).
- **Systeem:** maakt `intenties/<uuid>.policy.jsonld` (beleid naast de data, conform het bestaande principe): `@type` `odrl:Offer`, `assigner` = WebID van de eigenaar, één `permission` met `action` `use` (of `read`), `target` = de vier attributen (elk een eigen identifier, bijv. `urn:mysolido:profiel:<uuid>#leeftijdscategorie`), `constraint` `purpose eq offerteberekening` en `dateTime lteq validThrough`; `prohibition` op `distribute` (en eventueel `share`/`transfer`) voor dezelfde targets. Nog geen `assignee`: het is een aanbod aan de markt.
- **Bouwsteen:** `build_policy()` als voorbeeld van vorm en opslag; ODRL-JSON-LD-context is er al. **Gat:** nieuwe functie (werktitel `build_intention_policy`) met purpose-constraint, termijn uit de intentie, targets per veld, Offer-vorm; `policy_summary_nl()` kent deze vorm niet; geen leesroute die op de Bridge werkt.
- **Zichtbaar onderscheid access/usage control:** hier hoort de uitleg: het `.acl` op `profiel/` (CSS, *mag je erbij*) verandert niet; de policy (Flask, *waarvoor mag je het gebruiken*) is het nieuwe stuk.

### Stap 4 — Intentie activeren en aanbieden (pc)
- **Gebruiker:** klikt *Activeren*.
- **Systeem:** status `actief`; policy krijgt status "aangeboden". Anonieme publicatie naar een marktplaats bestaat niet en hoort niet in deze demo (roadmap "Later").
- **Bouwsteen:** `intentie_activate()`. **Gat:** geen.

### Stap 5 — Verzekeraar X reageert en accepteert de voorwaarden (in variant A op de pc gesimuleerd; het formulier zelf bestaat)
- **Gebruiker (in de rol van Verzekeraar X):** opent `/verzoek`, vult naam/organisatie/e-mail in, kiest "Verzekeringen", verwijst naar de intentie, ziet de policy-samenvatting en vinkt aan: "Ik accepteer deze voorwaarden (policy `urn:mysolido:policy:<uuid>`)".
- **Systeem:** schrijft `verzoeken/<uuid>.jsonld` met `mysolido:intention` = intentie-`@id`, `mysolido:acceptedPolicy` = policy-`uid`, tijdstip en het exacte aanbod (hash of kopie).
- **Bouwsteen:** verzoekformulier en `agreed_terms`. **Gat:** verwijzing naar intentie en policy; tonen van de voorwaarden op het formulier; de gevraagde-data-lijst zou uit de intentie moeten komen in plaats van uit zes vaste groepen.

### Stap 6 — Acceptatie door de eigenaar en consentrecord (pc)
- **Gebruiker:** ziet op *Profiel → Verzoeken* het verzoek van Verzekeraar X met de geaccepteerde voorwaarden; controleert de vier velden, doel, termijn, doorleververbod; klikt *Goedkeuren*.
- **Systeem:** (a) maakt van de Offer een `odrl:Agreement` met `assignee` = Verzekeraar X en slaat die op (bij het verzoek of bij de intentie); (b) schrijft `_response.json` met alleen de vier velden; (c) schrijft `toestemmingen/<YYYYMMDD-NNN>.jsonld` in 27560-structuur met: de vier attributen (`pii_information`), doel offerteberekening, geldigheid 14 dagen (`retention_period` + `hasExpiry`), geen derden (`recipient_third_parties` leeg + verwijzing naar de prohibition), controller Verzekeraar X met contact, status `dpv:ConsentGiven`, event "gegeven op <tijd>", verwijzingen naar Agreement-`uid`, intentie en verzoek; (d) logt `request_approve` en `consent_create`.
- **Bouwsteen:** `verzoek_approve()`, `consent_new()`-recordopbouw, `generate_consent_id()`, `APPROVAL_VALIDITY`. **Gat:** (a), (c) en de veldbeperking in (b) bestaan niet; 14 dagen ontbreekt in `APPROVAL_VALIDITY`; statustermen; de dode comment op regel 3745 is precies de plek.

### Stap 7 — Synchroniseren en tonen op de telefoon (Bridge)
- **Gebruiker:** klikt *Sync naar Bridge*; opent op de telefoon `bridge.mysolido.com`, logt in; opent *Toestemmingen → <record>*: ziet ontvanger, doel, vier velden, geldig tot, "geen doorlevering", status Actief; opent *Profiel → Mijn intenties → <intentie>* en de voorwaarden (samenvatting + JSON).
- **Systeem:** `sync_to_bridge()` kopieert de hele Pod-map inclusief `intenties/`, `toestemmingen/`, `verzoeken/` en de dotfile-policies (`scp -r` neemt dotfiles mee; *(vermoeden)* niet apart getest voor `.policy.jsonld` op de Bridge, de regressietest test alleen de sync-module lokaal).
- **Bouwsteen:** Bridge-modus, `consent_detail.html` (leesbaar op Bridge), `intentie_detail.html` (leesbaar). **Gat:** leesroute voor de policy op de Bridge; `consent_detail.html` moet de nieuwe velden tonen; handmatig syncen omdat `auto_sync_after_change()` niet bij deze modules wordt aangeroepen.

### Stap 8 — Facultatief: intrekken (pc) en het effect tonen (telefoon)
- **Gebruiker:** trekt de toestemming in op de pc, synct, laat op de telefoon status "Ingetrokken" zien; de responspagina van Verzekeraar X geeft daarna geen data meer.
- **Bouwsteen:** `consent_withdraw()`, `verzoek_response()`-vervalcontrole. **Gat:** intrekken van de toestemming raakt het verzoek/response niet (geen koppeling); de vervalcontrole werkt alleen op `validUntil`.

### Herkenbaarheid van de zeven elementen

| Element | In de ODRL-policy (stap 3/6) | In het consentrecord (stap 6) |
|---|---|---|
| Leeftijdscategorie | `target` `…#leeftijdscategorie` | `pii_information[0]` / `dpv:hasPersonalData` |
| Postcodegebied | `target` `…#postcodegebied` | `pii_information[1]` |
| Voertuigtype | `target` `…#voertuigtype` | `pii_information[2]` |
| Schadeverleden | `target` `…#schadeverleden` | `pii_information[3]` |
| Doel: offerteberekening | `constraint` `purpose eq <offerteberekening>` | `purpose` / `dpv:hasPurpose` met omschrijving "Offerteberekening" |
| Termijn: 14 dagen | `constraint` `dateTime lteq <acceptatie + 14d>` | `retention_period` 14 dagen + `dpv:hasExpiry` |
| Geen doorlevering | `prohibition` `distribute` (+ `share`/`transfer`) | `recipient_third_parties` = geen + verwijzing naar de prohibition |

---

## 6. Voorgestelde bouwvolgorde subtaken 2 t/m 5 (voorstel, geen besluit)

De volgorde is 2 → 3 → 4 → 5 omdat elke stap het datamodel van de vorige nodig heeft. De transportkeuze voor subtaak 5 (paragraaf 3) kan nu al genomen worden en bepaalt hoeveel subtaak 5 omvat.

| Subtaak | Wat er al is | Wat gemaakt moet worden | Afhankelijk van |
|---|---|---|---|
| **2. Gegevensselectie uit profiel** | Profielformulier met zes groepen; opslag als JSON-LD; `extract_profile_groups()`; groepsselectie in intentie met voorselectie per categorie; geldigheid 2 weken | Drie velden toevoegen (leeftijdscategorie als keuzelijst, postcodegebied als PC4 of "56xx", schadeverleden als schadevrije jaren + claims-ja/nee) in formulier, opslag, `extract_profile_groups()` en vertalingen; selectie per veld in `intentie_nieuw.html` en in het intentierecord (verwijzingen naar velden); doelveld en doorleververbod-vlag in de intentie; voorselectie van precies de vier velden bij "autoverzekering" | — |
| **3. ODRL-policy genereren** | `build_policy()` als vormvoorbeeld; JSON-LD-context met ODRL en DPV; opslagconventie `.policy.jsonld` naast de data; `policy_summary_nl()`; uitklapbare JSON in `policy_edit.html`; regressietestfase 11 als sjabloon | Nieuwe functie voor een intentiepolicy (`odrl:Offer`, purpose-constraint, termijn uit `validThrough`, targets per veld, prohibition distribute), apart van `build_policy()` zodat de mapregels ongemoeid blijven (ook met het oog op de ODRL 3-isolatie uit het koersdocument); opslag `intenties/<uuid>.policy.jsonld`; samenvatting in het Nederlands voor deze vorm; leesroute die ook in Bridge-modus werkt; testgevallen | 2 |
| **4. Acceptatie + consentrecord (ISO 27560)** | Verzoekformulier en -record; `verzoek_approve()` met response en geldigheid; `consent_new()`-recordopbouw, id-generator, status- en vervallogica, detailpagina; regressietestfasen 12-13 | Verzoek koppelen aan intentie en policy (velden + tonen van voorwaarden op het formulier); bij goedkeuren: Agreement maken, response beperken tot de geselecteerde velden, consentrecord schrijven in 27560-structuur (veldenlijst paragraaf 4) met verwijzingen; 14 dagen in `APPROVAL_VALIDITY`; statustermen corrigeren (`dpv:ConsentGiven`/`ConsentWithdrawn`) en de regressietest daarop aanpassen; gebeurtenisgeschiedenis; `consent_detail.html` uitbreiden; intrekken laat het verzoek meebewegen; regressietest uitbreiden met het goedkeuringspad | 3 |
| **5. End-to-end test via Bridge op telefoon** | Bridge-modus met login en blokkades; `sync_bridge.py`; alleen-lezen weergave van consent, intenties en profiel; publiek verzoekformulier; regressietestfase Bridge (7 checks) | Keuze A/B/C uit paragraaf 3 vastleggen; bij A: policy-leesroute op de Bridge (uit 3), controle dat `scp -r` de nieuwe records en dotfile-policies meeneemt, nieuwe code op de VPS uitrollen, demoprotocol met sync-momenten; bij B: retourkanaal als aparte taak vóór 5; testchecklist toevoegen aan `regressietest.md` (handmatig deel) | 4, en de transportkeuze |

Aanbevolen extra stap vóór subtaak 2: een korte "datamodel-notitie" met de exacte identifiers (attribuut-urn's, policy-`uid`, verwijzingsvelden), zodat 2, 3 en 4 dezelfde namen gebruiken. Dat is een halve pagina en voorkomt dat de koppelingen drie keer anders worden gebouwd.

---

## 7. Buiten dit verslag

**Bewust niet gedaan.** Geen code aangepast, geen servers gestart, geen regressietest gedraaid, geen testdata aangemaakt of gewist, geen ClickUp-handelingen, geen git-wijzigingen. `.env` alleen gelezen op niet-geheime sleutels; `.data/.internal/` niet geopend. De DPV-`pd:`-termen en de overige DPV-eigenschappen (`hasExpiry`, `hasExpiryTime`, `note`) zijn niet tegen de DPV-specificatie gecontroleerd; alleen de consentstatus-termen zijn geverifieerd via de DPV-27560-gids.

**Vragen die alleen jij kunt beantwoorden.**
1. Transportkeuze voor subtaak 5: variant A (twee schermen, geen retourkanaal), B (retourkanaal bouwen) of C (lokaal in het LAN)?
2. Wie accepteert in de demo? In MyTerms-termen stelt de eigenaar de voorwaarden en accepteert de wederpartij (stap 5); daarnaast keurt de eigenaar het verzoek goed (stap 6). Het script doet beide. Als één van de twee volstaat, wordt subtaak 4 kleiner.
3. Zijn de vier velden vast voor de demo, of exemplarisch? Bepaalt of de profieluitbreiding (leeftijdscategorie, postcodegebied, schadeverleden) als vaste velden of als generiek "attribuut"-mechanisme gebouwd wordt.
4. Welke codeversie draait op `bridge.mysolido.com`? De Bridge moet de nieuwe leesweergaven krijgen vóór de demo.
5. Waar staat de demodata? De Pod in de hoofdcheckout is leeg. Is die bewust leeg (na de regressietest van 14-09) en staat de gevulde Pod in `mysolido-backup-2026-09-14`, of moet het demoprofiel nog worden ingevoerd?
6. Mag de onjuiste DPV-statusterm nu gecorrigeerd worden, wetende dat bestaande records en de regressietest de oude waarde bevatten?

**Tegengekomen, buiten deze taak.**
- Dode comment "Create consent record" in `verzoek_approve()` (`app.py:3745`); het goedkeuringspad is in de regressietest niet gedekt.
- `audit_log.json`, `shares.json`, `trash.json` en de notificatiedata staan in de projectmap, niet in de Pod; ze worden niet gesynchroniseerd en vallen buiten de backup-export (sluit aan bij de bekende backup-tekortkoming).
- `auto_sync_after_change()` wordt alleen bij bestands- en deellinkacties aangeroepen, niet bij profiel-, intentie-, consent- of policywijzigingen.
- Intentierecords bevatten een kopie van de profieldata (`mysolido:sharedProfileData`), terwijl de detailpagina het actuele profiel toont: twee waarheden.
- De responspagina (`verzoek_response`) toont hele groepen; bij "Voertuigen" dus ook brandstof en bouwjaar.
- Het koersdocument noemt CSS v7.1.9 en "13 standaardcategorieën"; de code heeft 7.2.0 en twintig `DEFAULT_FOLDERS`.
- Repo-root bevat vijf ongetrackte markdown-bestanden (git status), een map `Nieuwe map/` en een Word-lockbestand `~$ntekeningen MySolido.docx`; niet aangeraakt.
- Flask bindt alleen op `127.0.0.1`; relevant zodra iemand de pc-versie op een telefoon wil tonen.
- README en trustpagina claimen "conform ISO/IEC TS 27560:2023"; tot subtaak 4 klaar is, is dat een voornemen.
