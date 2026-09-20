# MySolido — Verslag MyTerms-demo, subtaak 2: gegevensselectie uit profiel

| | |
|---|---|
| **Datum** | 20 september 2026 |
| **Softwareversie** | branch `myterms-demo`, uitgangspunt commit `613e6c0` (19-09-2026, "Verslag: inventarisatie bouwstenen MyTerms-demo"); `main` staat op dezelfde commit `613e6c0`. Alle wijzigingen hieronder zijn **niet gecommit** (werkboom) |
| **Omgeving** | Windows 10, hoofdcheckout `C:\Users\Wim\mysolido`; CSS 7.2.0 draaide al op `http://127.0.0.1:3000` (niet herstart); Flask voor de tests gestart met `python app.py` op `127.0.0.1:5000` en daarna gestopt; Python 3.13.2 |
| **Gewijzigd** | `app.py`, `templates/profiel_data.html`, `templates/intentie_nieuw.html`, `templates/intentie_detail.html`, `translations.py`, `scripts/regressietest.py`, `scripts/regressietest.md` |
| **Aangemaakt** | `docs/mysolido_notitie_datamodel-myterms_20-09-2026.md`, `scripts/seed_demo.py`, dit verslag |
| **Pod na deze sessie** | `.data/mysolido/` bevat nu de twintig standaardmappen, `profiel/profiel.jsonld` (demoprofiel) met `profiel/.policy.jsonld`, drie voorbeeldtekstbestanden in `voertuigen/` en `financieel/`, en `intenties/.policy.jsonld` (door de app aangemaakt bij de eerste testintentie). Geen intenties, verzoeken of toestemmingen: alle testrecords zijn opgeruimd |
| **Vervolg op** | `docs/mysolido_verslag_myterms-demo-inventarisatie_19-09-2026.md`; regelnummers van de oude stand verwijzen naar `810fef5`/`613e6c0` (identieke `app.py`), nieuwe regelnummers naar de werkboom van dit verslag |
| **Niet gedaan** | geen git-wijzigingen, geen ClickUp, geen Bridge, geen wijzigingen aan policygeneratie, verzoeken, consent, CSS-pinning, startscripts, `.env`, README of trustpagina |

---

## 1. Correcties op inventarisatie, opdracht en datamodel

1. **"Niet rechtstreeks in `.data/` schrijven" is niet hoe de app werkt.** De opdracht vroeg het seed-script via `pod_write` te laten lopen en níet rechtstreeks in `.data/` te schrijven omdat CSS dan zijn metadata mist. `pod_write`, `pod_mkdir` en `pod_exists` (`app.py:165-205`) schrijven zelf rechtstreeks op schijf in `.data/<pod>/`; de app gebruikt voor profiel, intenties, verzoeken en toestemmingen nergens HTTP (`docs/css-koppelvlakken.md` §6 en §8, klasse C). Het seed-script gebruikt dus dezelfde routines als de app en schrijft daarmee, net als de app, op schijf. CSS serveert die bestanden zonder `.meta` (regressietest: `.policy.jsonld` via CSS 200 met `application/ld+json`). De controle "CSS antwoordt op `CSS_BASE_URL`" zit wel in het script, zodat het niet tegen een niet-lopende stack wordt gedraaid.

2. **Importeren van `app.py` heeft geen storende bijwerkingen.** Op moduleniveau gebeurt alleen `load_dotenv()` (`app.py:39`) en `os.makedirs(temp/)` (`app.py:58`); server, auto-setup en `init_default_policies()` staan onder `if __name__ == '__main__'` (`app.py:4360` e.v.). Daarom importeert `seed_demo.py` `app.py` en is er geen eigen schrijffunctie gemaakt. Dit staat in de docstring van het script.

3. **De regressietest had geen intentiefase.** De opdracht vroeg "de intentiefase die `sharedProfileData` verwacht" aan te passen; die fase bestond niet (fasen: policy, consent/verzoek, bridge, zie `regressietest.py` op `613e6c0`, regel 969-1013). Er is niets aangepast, er is een nieuwe fase bijgekomen (§2, `scripts/regressietest.py`).

4. **Regelnummer van de dode comment.** "Create consent record" stond op `app.py:3750`, niet 3745 (inventarisatie §1 punt 3 en het controlepunt in de opdracht); in de werkboom staat hij nu op `app.py:4117`. Niet aangeraakt (subtaak 4).

5. **DPV-PD-termen (DPV-PD 2.1, 16-03-2025, gecontroleerd op w3c-cg.github.io/dpv/2.1/pd/).** `pd:AgeRange`, `pd:PostalCode`, `pd:Vehicle`, `pd:Insurance`, `pd:Location`, `pd:FamilyStructure`, `pd:Professional` en `pd:Health` bestaan. **Niet** bestaan: `pd:HousingOwnership`, `pd:HouseholdSize`, `pd:Occupation`, `pd:HealthData` (de sleutels die `profiel.jsonld` sinds v1.2 gebruikt, inventarisatie §2 "vermoeden" bevestigd) en een claims-/schadeverledenterm (`pd:InsuranceClaim`, `pd:ClaimsHistory`). **Afwijking van de opdrachtregel:** voor `claims_history` is niet `mysolido:claims_history` gekozen maar `pd:Insurance` als naaste bredere geverifieerde term. Dat is één regel in `PROFILE_ATTRIBUTES` (`app.py:2856`) als je het anders wilt. De vier niet-bestaande `pd:`-sleutels blijven in de opslag staan (opslag ongewijzigd, zoals opgedragen); ze staan als `mysolido:<key>` in de constante en op de migratielijst (§6).

6. **Toevoegingen aan het datamodel uit de opdracht,** vastgelegd in de notitie vóór de bouw: `valueLabel` naast `value` in `sharedAttributes` (leesbare weergave die niet afhangt van latere optiewijzigingen) en `dpv` in het `purpose`-object (`dpv:ServiceProvision`, zodat subtaak 4 niet hoeft terug te zoeken). Verder is de notitie gevolgd; geen afwijkingen.

7. **`extract_profile_groups()` wordt ook door verzoeken gebruikt** (`verzoek_detail_owner`, `verzoek_approve`, werkboom `app.py:4048, 4088`; niet in de inventarisatie genoemd). De nieuwe groep `personal` en de uitgebreide samenvattingen van `housing` en `insurance` verschijnen daardoor ook op de verzoekpagina van de eigenaar. De `data`-vorm per groep is ongewijzigd gelaten (verzekeringen blijft een lijst), zodat `verzoek_approve` en de responspagina hetzelfde blijven doen. Zie §6 voor subtaak 4.

8. **Tijdstempels zijn UTC.** `capturedAt` en `schema:dateCreated` staan in UTC (`+00:00`), zoals de bestaande intentiecode al deed; de detailpagina toont alleen de datum. Bij een intentie 's avonds na 02:00 (zomertijd) kan de getoonde datum een dag vóór de lokale datum liggen. Bestaand gedrag, niet gewijzigd.

---

## 2. Per bestand: wat en waarom

### `docs/mysolido_notitie_datamodel-myterms_20-09-2026.md` (nieuw)
De datamodel-notitie uit de opdracht: attributen (met DPV-controle), intentierecord, namen voor subtaak 3 en 4, en de tabel veld / waar / wie schrijft / wie leest. Eerst geschreven, daarna gebouwd.

### `app.py` (4035 → 4402 regels)
- **`2765-3086` nieuw blok `=== PROFIEL-ATTRIBUTEN (MyTerms-demo, subtaak 2) ===`**, direct vóór de profielroutes:
  - `PROFILE_CONTEXT` (`2777`): de JSON-LD-context van het profiel, nu gedeeld door `profiel_data_save()` en het seed-script.
  - `PROFILE_GROUPS` (`2784`): zeven groepen met label en icoon; `personal` is nieuw.
  - `PROFILE_ATTRIBUTES` (`2796-2885`): de bron van waarheid. De vier scenario-attributen zijn gemarkeerd; de overige elf bestaande velden zijn opgenomen zodat de per-veldselectie compleet is (huisartspraktijk bewust niet). Per attribuut `label`, `group`, `input`, `options`, `dpv`, `path` en bij de drie nieuwe velden `form_field`.
  - `INTENTION_PURPOSES`, `DEFAULT_INTENTION_PURPOSE`, `OFFER_MODES` (`2888-2892`).
  - Hulpfuncties, elk één taak: `attribute_urn` (`2895`), `_profile_get`/`_profile_set` (`2900`, `2913`, lezen en schrijven langs `path`), `profile_attribute_value` (`2929`), `attribute_value_label` (`2941`, Nederlandse weergave per invoertype), `extract_profile_attributes` (`2971`, per groep voor het intentieformulier), `build_shared_attributes` (`2988`, het snapshot), `set_profile_attribute` (`3007`), `read_attributes_from_form` (`3014`, generieke uitlezing van de velden met `form_field`, met patrooncontrole voor het postcodegebied), `ensure_profiel_policy` (`3062`, de bestaande profielpolicy uit `profiel_data_save` verplaatst naar een functie zodat het seed-script hem kan aanroepen; inhoud ongewijzigd).
- **`profiel_data()` (`3089-3105`)**: geeft `attributes=PROFILE_ATTRIBUTES` door aan het formulier (voor de opties van de leeftijdscategorie).
- **`profiel_data_save()` (`3108-3207`)**: `@context` uit `PROFILE_CONTEXT` (`3117`); nieuw blok `3188-3194` dat de drie scenariovelden via `read_attributes_from_form` en `set_profile_attribute` opslaat en per ongeldig veld een foutmelding geeft (de rest wordt wél opgeslagen); de policy-aanmaak is de aanroep `ensure_profiel_policy()` (`3204`). De bestaande veldcode ertussen is niet aangeraakt.
- **`INTENTION_CATEGORIES` (`3212-3235`)**: `profile_fields` zijn nu attribuutsleutels in plaats van groepsnamen; `autoverzekering` selecteert precies `age_category`, `postal_area`, `vehicle_type`, `claims_history` voor. De andere categorieën hebben een vergelijkbare vertaling gekregen (per categorie de velden uit de oude groepen die in `PROFILE_ATTRIBUTES` zitten).
- **`extract_profile_groups()` (`3262-3392`)**: groep `personal` toegevoegd (`3266-3274`), postcodegebied in samenvatting en `data` van `housing` (`3284-3297`), schadeverleden in de samenvatting van `insurance` (`3348-3351`, `data` blijft de verzekeringenlijst). Verder ongewijzigd; de functie blijft in gebruik voor oude intentierecords en voor verzoeken.
- **`intentie_new()` (`3499-3588`)**: POST leest `purpose`, `no_onward_transfer`, `offer_mode`, `targeted_party` (`3521-3533`; gericht aanbod zonder naam wordt geweigerd met flash) en `attributes` (`3535-3537`); het record (`3539-3565`) volgt datamodel punt 2 en bevat geen `mysolido:sharedProfileData` meer; `targetedParty` alleen bij `targeted`; het logboek krijgt de attribuut-urn's mee. GET (`3578-3588`) geeft `attribute_groups`, `purposes` en `default_purpose` door.
- **`intentie_detail()` (`3591-3634`)**: toont het snapshot (`3613-3624`); alleen als een record geen `sharedAttributes` heeft maar wel `sharedProfileData`, wordt het actuele profiel geladen voor de oude groepsweergave. Daarmee is de "twee waarheden"-opmerking uit de inventarisatie (`3260-3262` oud) opgelost voor nieuwe records.

### `templates/profiel_data.html`
- Kaart **Persoonlijk** met keuzelijst leeftijdscategorie (`38-51`), opties uit `PROFILE_ATTRIBUTES`.
- **Postcodegebied (4 cijfers)** naast "Regio / provincie" (`81-87`), `pattern="[0-9]{4}"` en `inputmode="numeric"`; de servercontrole staat in `read_attributes_from_form`.
- **Schadeverleden** onderaan de verzekeringenkaart (`187-205`): schadevrije jaren (getal) en schade geclaimd in de laatste 3 jaar (ja/nee). Alle drie respecteren `read_only` (Bridge).

### `templates/intentie_nieuw.html` (herschreven)
Per groep een blok met per attribuut een checkbox `name="attributes" value="<key>"` en de huidige waarde ernaast; niet-gevulde attributen zijn uitgeschakeld met de link "vul aan". Nieuwe kaart **Voorwaarden (MyTerms)**: doel (keuzelijst uit `INTENTION_PURPOSES`), doorlevering (checkbox, standaard aan = niet toegestaan), aanbodvorm (keuzerondjes open/gericht, standaard open; bij gericht verschijnt het verplichte naamveld). De voorselectie-JS werkt nu op attribuutsleutels en slaat uitgeschakelde checkboxes over.

### `templates/intentie_detail.html` (herschreven)
Kaart **Voorwaarden (MyTerms)** (doel, doorlevering, aanbodvorm met partijnaam) en kaart **Vastgelegde gegevens** met de regel "Vastgelegd op <datum>; wijzigingen in je profiel daarna staan hier niet in." en per attribuut label en `valueLabel` (`data-attribute="<urn>"` voor de test). Oude records met `sharedProfileData` krijgen de vroegere groepsweergave met de melding dat het je huidige profiel toont. Actieknoppen ongewijzigd.

### `translations.py`
NL `345-366` en EN `987-1008`: teksten voor selectie, voorwaarden, snapshot, oud record en twee flash-meldingen (`flash_targeted_party_required`, `flash_attribute_invalid`). NL `487-496` en EN `1129-1138`: labels van de drie profielvelden en ja/nee. Bestaande sleutels ongewijzigd; `int_share_data_desc` blijft bestaan maar wordt door het nieuwe formulier niet meer gebruikt.

### `scripts/seed_demo.py` (nieuw, 176 regels)
Importeert `app.py` (zie §1 punt 2), controleert Pod-map en CSS, weigert met exit 1 als `profiel/profiel.jsonld` bestaat (tenzij `--force`), maakt ontbrekende `DEFAULT_FOLDERS` aan, bouwt het demoprofiel uitsluitend via `set_profile_attribute` (dus via `PROFILE_ATTRIBUTES.path`), schrijft `profiel.jsonld` en de policy via `ensure_profiel_policy`, zet drie tekstbestanden neer en print wat is aangemaakt plus de vier scenariowaarden. Wist nooit iets. Demoprofiel: 35-44, postcodegebied 5611, koop/tussenwoning/Noord-Brabant, 3 personen met één kind 5-12, auto benzine 2019, zorg- en aansprakelijkheidsverzekering (bewust géén autoverzekering), 5 schadevrije jaren zonder claims, ICT/loondienst, niet-roker.

### `scripts/regressietest.py` (1029 → 1279 regels)
- `import subprocess` (`44`); constanten `DEFAULT_FOLDERS_ALL`, `SEED_SCRIPT`, `SEED_FILES`, `ATTR`, `SCENARIO_ATTRIBUTES` (`63-76`).
- `Ctx.pre_existing` kent nu ook `intenties` en `profiel`; `ctx.seeded` (`196-200`).
- Nieuwe fasen (`985-1218`): `phase_seed` (lege Pod → exit 0, twintig mappen, voorbeeldbestanden, profiel + policy, vier waarden, tweede run weigert met exit 1 en laat alles staan; bestond het profiel al, dan alleen de weigering), `phase_profile_fields` (opslaan en teruglezen van de drie velden, bestaande velden blijven werken, ongeldig postcodegebied niet opgeslagen; het oorspronkelijke profiel wordt teruggezet), `phase_intention` (formulier, record met precies de vier attributen en de actuele profielwaarden, `capturedAt`, purpose, `noOnwardTransfer`, `offerMode`, geen `sharedProfileData`, 14 dagen, detailpagina met "Vastgelegd op" en de vier urn's, snapshot blijft gelijk na profielwijziging, gericht aanbod zonder/met naam, oud record leesbaar, opruimen).
- `--phase demo` draait alleen deze drie (`1238-1241`); in de volledige run staan ze na de consentfase (`1252-1254`). `phase_cleanup` meldt dat demodata blijft staan en ruimt `intenties/` op als die vóór de run niet bestond en alleen `.policy.jsonld` bevat (`924-928`).

### `scripts/regressietest.md`
Rijen 13a (demodata), 13b (profielvelden), 13c (intentie) in de tabel; nieuwe paragraaf "Geautomatiseerd, aparte run: demodata, profielvelden en intentie" met de waarschuwing dat `--phase demo` een lege Pod vult en de demodata laat staan.

---

## 3. Uitkomst regressietest

Gedraaid tegen de lopende CSS 7.2.0 en een voor de test gestarte Flask, scenario U.

| Run | Opdracht | Resultaat |
|---|---|---|
| 1 | `python scripts/regressietest.py --phase demo` (Pod nog zonder profiel) | **28 geslaagd, 0 gefaald**, 3 s. Seed vulde de lege Pod; alle checks van 13a-13c groen |
| 2 | `python scripts/regressietest.py --scenario U` (volledige run, Pod nu gevuld) | **117 geslaagd, 0 gefaald**, 2 niet automatiseerbaar (bekend: WebID-token op http, scp naar Bridge), 32 info, 15 s. Alle bestaande fasen groen; seed-fase koos het pad "profiel bestond al" (info) en testte de weigering |

Fasen van run 2: Preflight, Accountcreatie, WebID en credentials, Bestanden en roundtrip, Identifier-normalisatie, WAC/ACL, Deellinks, ODRL-beleid, Toestemmingen en consentrequests, **Demodata**, **Profielvelden**, **Intentie**, Backup en restore, /debug, Probes 7.2.0, Bridge-sync module, Persistentie aanmaken, Opruimen. Ruwe uitvoer van run 2 in de bijlage; run 1 staat in §3 van de bijlage.

Aanvullend handmatig door mij bekeken in de browser (127.0.0.1:5000): `/profiel-data` (drie nieuwe velden gevuld met de demowaarden), `/intenties/nieuw` (voorselectie van precies vier attributen bij autoverzekering, voorwaardenkaart) en de detailpagina van een testintentie (voorwaarden en snapshot met "Vastgelegd op 2026-09-20"). De testintentie is daarna verwijderd.

---

## 4. Handmatige controle (niet uitgevoerd, voor jou)

Start de stack zoals gewoonlijk (CSS draait al; `python app.py` of `start-mysolido.bat`) en open `http://127.0.0.1:5000`.

1. **Profiel.** *Profiel → Mijn gegevens.* Verwacht: bovenaan de kaart **Persoonlijk** met leeftijdscategorie **35-44**; bij **Woonsituatie** naast "Regio / provincie" het veld **Postcodegebied (4 cijfers)** met **5611**; onderaan **Verzekeringen** het kopje **Schadeverleden** met **5** schadevrije jaren en **Nee**. Zet het postcodegebied op `56` en klik Opslaan: rode melding "Het veld 'Postcodegebied (4 cijfers)' is ongeldig en is niet opgeslagen", het veld is na herladen leeg, de rest is bewaard. Zet het terug op `5611` en sla op.
2. **Intentie aanmaken.** *Profiel → Mijn intenties → Nieuwe intentie.* Kies **Autoverzekering**, geldigheid **2 weken**, omschrijving "Ik zoek een autoverzekering". Verwacht onder "Welke gegevens wil je delen?": per groep de velden met hun huidige waarde ernaast, en precies vier aangevinkt: Leeftijdscategorie (35-44), Postcodegebied (5611), Voertuigtype (Auto), Schadeverleden (5 / nee); Brandstof en Bouwjaar staan uit. Onder **Voorwaarden (MyTerms)**: doel **Offerteberekening**, "Doorlevering aan derden niet toegestaan" aangevinkt, **Open aanbod** geselecteerd. Klik op *Gericht aanbod*: het naamveld verschijnt en is verplicht. Zet terug op *Open aanbod* en sla op als concept.
3. **Snapshot.** Open de intentie. Verwacht: kaart **Voorwaarden (MyTerms)** met Offerteberekening / Niet toegestaan / Open aanbod, en kaart **Vastgelegde gegevens** met "Vastgelegd op 2026-09-20; wijzigingen in je profiel daarna staan hier niet in." en de vier regels. Ga daarna naar *Mijn gegevens*, zet de leeftijdscategorie op **45-54**, sla op en open de intentie opnieuw: er staat nog steeds **35-44**. Zet de leeftijdscategorie terug op 35-44 (of draai `python scripts/seed_demo.py --force`). Wie wil, opent `.data\mysolido\intenties\<uuid>.jsonld`: `mysolido:sharedAttributes` met vier objecten, `mysolido:purpose`, `mysolido:noOnwardTransfer: true`, `mysolido:offerMode: "open"`.

---

## 5. Buiten dit verslag

**Bewust niet gedaan.** `build_policy()`, `policy_summary_nl()`, mappolicies en `policy_edit.html` (subtaak 3); `verzoek_*`, `consent_*`, `verzoek_approve()`, de dode comment (nu `app.py:4117`) en de onjuiste DPV-statustermen (nu `app.py:2530, 2643, 2729` ongewijzigd in nummering, want alles daarboven is gelijk gebleven) (subtaak 4); `BRIDGE_MODE`, `sync_bridge.py`, VPS (subtaak 5); CSS-pinning, startscripts, installers, `package.json`, backup-export, `.env` (alleen gelezen), README en trustpagina. Geen git-wijzigingen, geen ClickUp. De welkomstscherm-bug (`is_pod_empty`) is niet opgelost; het seed-script maakt de mappen zelf aan. De regressietest verwijdert de gezaaide demodata niet (bedoeld als demostand). Het door `pod_write` gemaakte `intenties/.policy.jsonld` staat in de Pod als bijproduct van de testintenties; onschadelijk, de app maakt hem anders bij de eerste echte intentie.

**Tegengekomen, voor subtaak 3.**
- De targets voor de Offer liggen klaar: `[a['@id'] for a in record['mysolido:sharedAttributes']]`; de purpose-urn en `noOnwardTransfer` staan in het record. `attribute_urn()` en `PROFILE_ATTRIBUTES[key]['dpv']` zijn bruikbaar voor `dpv:hasPersonalData`.
- `policy_summary_nl()` kent alleen de vier mapregels; de Offer-vorm heeft een eigen samenvatting nodig (al genoemd in de inventarisatie).

**Tegengekomen, voor subtaak 4.**
- `verzoek_detail_owner` en `verzoek_approve` (`app.py:4048, 4088`) werken nog per groep via `extract_profile_groups()`; de nieuwe groep `personal` verschijnt daar nu ook. Zodra het verzoek aan een intentie gekoppeld wordt, ligt het voor de hand dat de goedkeuring `sharedAttributes` van de intentie gebruikt in plaats van groepen.
- `REQUEST_CATEGORIES`/`requested_data` in het publieke formulier zijn nog zes vaste groepen; per attribuut kan pas als het verzoek naar een intentie verwijst.
- `APPROVAL_VALIDITY` mist nog steeds 14 dagen.

**Tegengekomen, voor de andere lijsten.**
- Migratielijst profiel: de opslagsleutels `pd:HousingOwnership`, `pd:HouseholdSize`, `pd:Occupation` en `pd:HealthData` zijn geen DPV-PD-termen (§1 punt 5). Kandidaten: `pd:HouseOwned` dekt alleen "koop"; voor huishoudgrootte, sector/dienstverband en rookstatus zijn er geen specifieke termen, wel de bredere `pd:Family`, `pd:Professional`, `pd:Health`. Hoort bij dezelfde migratie als de consentstatustermen.
- `int_share_data_desc` in `translations.py` is nu ongebruikt.
- De Bridge toont `/profiel-data` en `/intenties/<id>` alleen-lezen; de nieuwe velden en de snapshotkaart komen daar mee zodra de VPS de nieuwe code heeft (subtaak 5). Niet getest in Bridge-modus.
- Bij het opslaan van het profiel wordt het hele bestand opnieuw opgebouwd uit het formulier; velden die het formulier niet kent (zoals een toekomstig vijfde attribuut zonder `form_field`, of door het seed-script gezette waarden die niet in het formulier staan) gaan bij opslaan verloren. Nu niet aan de orde omdat alle gezaaide velden in het formulier staan, maar relevant zodra een attribuut alleen via een script wordt gevuld.

**Vragen die alleen jij kunt beantwoorden.**
1. `claims_history` staat nu op `pd:Insurance` (naaste bredere term). Akkoord, of liever `mysolido:claims_history` zoals de opdrachtregel letterlijk zegt?
2. De voorselecties van de andere negen categorieën (zorg, woon, energie, hypotheek, reis, rechtsbijstand, pensioen, internet, anders) zijn door mij vertaald van groepen naar attributen. Kloppen die naar jouw idee, of moeten alleen `autoverzekering` en `anders` een voorselectie hebben?
3. Moet het intentieformulier een intentie zonder één enkel gevuld attribuut weigeren? Nu wordt die opgeslagen met een lege `sharedAttributes`-lijst (bestaand gedrag: ook eerder kon je zonder groepen opslaan).
4. Blijft de demodata in de hoofdcheckout staan tot de demo, of wil je de Pod na elke testrun leeg? Dat bepaalt of de opruimfase de seed moet terugdraaien.
5. Het demoprofiel heeft bewust géén lopende autoverzekering (de persoon zoekt er een). Klopt dat met het scenario-script, of moet er een aflopende polis in staan?

---

## Bijlage: ruwe uitvoer

### Run 2: `python scripts/regressietest.py --scenario U` (volledige run)

```
MySolido regressietest 2026-09-20 09:32 -- scenario U, fase all, CSS http://127.0.0.1:3000 (7.2.0), Flask http://127.0.0.1:5000, Pod http://127.0.0.1:3000/mysolido/

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
  [PASS] Test-Pod aanmaken  -- http://127.0.0.1:3000/regressietest-pod-8a4d60/
  [PASS] Test-Pod staat op schijf als .data/<podnaam>/  -- C:\Users\Wim\mysolido\.data\regressietest-pod-8a4d60
  [PASS] Test-WebID publiek bereikbaar met solid:oidcIssuer  -- http://127.0.0.1:3000/regressietest-pod-8a4d60/profile/card#me
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
  [PASS] Consentrequest: JSON-LD velden correct en statustoken in bevestiging  -- 445fd2b1-3f3f-419f-b649-a5a4813ad65c
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
  [PASS] Intentie: offerMode targeted met targetedParty, noOnwardTransfer false zonder vinkje
  [PASS] Intentie: oud record met sharedProfileData blijft leesbaar (groepsweergave)
  [PASS] Intentie: testrecords opgeruimd

== Backup en restore ==
  [PASS] Backup: zip-export  -- 4785 bytes
  [PASS] Backup: bevat testbestand met juiste inhoud  -- regressietest/ldp/roundtrip.txt
  [INFO] Backup: .policy.jsonld en .acl in zip  -- nee, dotfiles en .acl worden overgeslagen
  [INFO] Backup: .mysolido/share_links.json in zip  -- nee
  [PASS] Restore: bestand uit zip teruggezet en via CSS leesbaar

== Flask /debug (HTTP-laag) ==
  [PASS] Flask /debug: HTTP-lezing van Pod-root via CSS (root is publiek)

== Probes 7.2.0-changelog ==
  [INFO] Probe dubbele slug: twee POSTs met Slug slug-test.txt  -- 201 http://127.0.0.1:3000/mysolido/regressietest/ldp/slug-test.txt | 201 http://127.0.0.1:3000/mysolido/regressietest/ldp/07262d92-a389-41cd-b4ea-4957b23e2c1a; op schijf ['slug-test.txt']
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
  [PASS] Opruimen: test-Pod-map van schijf verwijderd  -- C:\Users\Wim\mysolido\.data\regressietest-pod-8a4d60
  [INFO] Opruimen: runtime-bestanden in projectmap (trash.json, shares.json, audit_log.json, notifications.json)  -- blijven staan, vallen onder .gitignore

Resultaat: 117 geslaagd, 0 gefaald, 2 niet automatiseerbaar, 32 info (15s)
```

### Run 1: `python scripts/regressietest.py --phase demo` (Pod zonder profiel)

```
MySolido regressietest 2026-09-20 09:32 -- scenario U, fase demo, CSS http://127.0.0.1:3000 (7.2.0), Flask http://127.0.0.1:5000, Pod http://127.0.0.1:3000/mysolido/

== Demodata (seed_demo.py) ==
  [PASS] Seed: lege Pod gevuld (exit 0)
  [PASS] Seed: twintig standaardmappen aanwezig
  [PASS] Seed: voorbeeldbestanden in voertuigen/ en financieel/
  [PASS] Seed: profiel/profiel.jsonld aanwezig
  [PASS] Seed: profiel/.policy.jsonld aanwezig
  [PASS] Seed: demoprofiel bevat de vier scenariowaarden
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
  [PASS] Intentie: offerMode targeted met targetedParty, noOnwardTransfer false zonder vinkje
  [PASS] Intentie: oud record met sharedProfileData blijft leesbaar (groepsweergave)
  [PASS] Intentie: testrecords opgeruimd

Resultaat: 28 geslaagd, 0 gefaald, 0 niet automatiseerbaar, 0 info (3s)
```
