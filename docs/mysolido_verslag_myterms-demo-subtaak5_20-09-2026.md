# MySolido — Verslag MyTerms-demo, subtaak 5: afronden, demoprotocol, Bridge-gereedheid

| | |
|---|---|
| **Datum** | 20 september 2026 (vijfde sessie van die dag) |
| **Softwareversie** | branch `myterms-demo`, uitgangspunt commit `5bfacf3` ("MyTerms-demo subtaak 4b: consentrecord in 27560-vorm, DPV-statustermen, toestemming intrekken"). Alle wijzigingen hieronder zijn **niet gecommit** |
| **Omgeving** | Windows 10, hoofdcheckout `C:\Users\Wim\mysolido`; CSS 7.2.0 draaide al op `http://127.0.0.1:3000` (niet herstart); Flask voor de tests gestart met `REQUEST_RATE_LIMIT=100 python app.py` op `127.0.0.1:5000` (twee keer, zie §1 punt 3) en daarna gestopt; de testfase "Bridge-modus lokaal" startte en stopte zelf een tweede proces `python app.py --bridge` op poort 5001; Python 3.13.2. De VPS is niet aangeraakt |
| **Gewijzigd** | `app.py`, `translations.py`, `templates/base.html`, `templates/intentie_detail.html`, `templates/intenties.html`, `templates/verzoek_detail.html`, `templates/verzoek_response.html`, `templates/consent_list.html`, `templates/consent_detail.html`, `scripts/seed_demo.py`, `scripts/regressietest.py`, `scripts/regressietest.md`, `README.nl.md` (één zin), `.env.example` (twee sleutels) |
| **Aangemaakt** | `docs/mysolido_demoprotocol_myterms.md`, `docs/mysolido_uitrol-bridge_checklist.md`, dit verslag |
| **Pod na deze sessie** | Schone demostand na `python scripts/seed_demo.py --reset --yes` aan het eind: demoprofiel opnieuw gezet, de drie voorbeeldbestanden aanwezig, `intenties/`, `verzoeken/` en `toestemmingen/` leeg (ook de mappolicies daarin; de app maakt ze opnieuw bij het eerste record), `audit_log.json`, `trash.json` en `shares.json` leeg (`notifications.json` bestond niet). Jouw intenties `a0ac025c` en `fb9189cb`, de acceptaties van Jan Jansen en de testrecords van 20-09 zijn daarmee weg, zoals afgesproken |
| **Vervolg op** | `docs/mysolido_verslag_myterms-demo-subtaak4b_20-09-2026.md`; regelnummers "oud" verwijzen naar `5bfacf3`, "nieuw" naar de werkboom van dit verslag |
| **Niet gedaan** | geen git-wijzigingen (alleen `git rev-parse` gelezen), geen ClickUp, geen VPS, geen wijziging aan `sync_bridge.py`, `check_bridge_auth()`, BRIDGE_MODE-logica, datamodel, `build_*`, `conclude_agreement()`, `consent_withdraw()`, trustpagina, `.env`, CSS, startscripts, installers, `package.json`, backup-export |

---

## 1. Correcties op eerdere verslagen, inventarisatie en deze opdracht

1. **cp1252-vondst uit 4b, apart voor `docs/css-koppelvlakken.md`.** `pod_write()` schreef tot 20-09-2026 tekst zonder `encoding`, dus in de Windows-systeemcodering, terwijl alle lezers (`load_all_intentions`, `load_all_requests`, `load_all_consents`, `load_pod_json`, de regressietest) UTF-8 openen. Elk record met een niet-ASCII-teken (é, ë, gedachtestreepje) werd onleesbaar en gaf een 500 op de overzichtspagina's; ook `scp` naar de VPS (Linux, UTF-8) zou zulke bestanden kapot hebben overgebracht. Sinds 4b schrijft `pod_write()` UTF-8 (`app.py:172-174`). Het hoort in `css-koppelvlakken.md` bij de klasse-C-tabel (§6, rij `pod_write`) als bekende tekortkoming die is opgelost, met de kanttekening dat oudere Pods met accenten in records handmatig hercodering nodig hebben. Ik heb `css-koppelvlakken.md` niet aangepast (buiten de opdracht).

2. **`--bridge` luisterde vast op poort 5000.** `app.run(port=5000)` stond hard in beide takken van het opstartblok (oud `5234`, `5258`). Een tweede proces met `--bridge` naast de lokale app was zonder wijziging niet mogelijk. Nieuw: `APP_PORT` uit `MYSOLIDO_PORT` (standaard 5000, `app.py:75`), gebruikt op `5282` en `5306`. Dit is het opstartblok, niet de BRIDGE_MODE-logica; `check_bridge_auth()` en `check_bridge_mode()` zijn ongewijzigd.

3. **Bridge-wachtwoord voor de testfase.** `bridge_login()` leest `BRIDGE_PASSWORD` uit de omgeving (`.env` via `load_dotenv()` zonder override). De testfase geeft het tweede proces een eigen bcrypt-hash van een willekeurig wachtwoord mee in de procesomgeving; `.env` wordt niet gelezen als bron voor dat wachtwoord en niet geschreven (`migrate_passwords_to_bcrypt()` schrijft alleen als `.env` een platte tekst bevat, en dat is niet zo). Jouw Bridge-wachtwoord blijft dus buiten de test. Dezelfde Pod (`SOLID_POD_URL` uit `.env`) wordt door beide processen gelezen.

4. **Dagenduur in het consentrecord rondde naar beneden af.** `_days_between()` uit 4b nam `(end - start).days`; zodra de acceptatie een paar seconden na het aanmaken van de intentie valt, gaf dat 13 in plaats van 14. In 4b viel dat niet op omdat de test binnen dezelfde seconde accepteerde. Nu naar boven afgerond op hele dagen (`app.py:2810-2819`). Fout van mij in 4b; gecorrigeerd en getest.

5. **Verzoeklimiet in de test.** De demo-fase en de volledige run samen doen nu tweeëntwintig acceptatie-POSTs; met de standaardlimiet van tien faalt de tweede run in hetzelfde proces (zie 4b). Met de nieuwe `.env`-sleutel `REQUEST_RATE_LIMIT` (`app.py:4400-4406`) is Flask voor de tests met `REQUEST_RATE_LIMIT=100` gestart; beide runs groen in één proces. De checklist beschrijft dit.

6. **`--reset` verwijdert ook de mappolicies** `intenties/.policy.jsonld` en `verzoeken/.policy.jsonld`, omdat de opdracht "de inhoud van de drie mappen (records, policies, …)" zegt. De app maakt ze opnieuw aan bij het eerste record (`ensure_intenties_policy()`, `ensure_verzoeken_policy()`); tot die tijd staan de mappen zonder policy, wat de kluislisting niet stoort (systeemmappen). Het slotbericht van het script zegt dat.

7. **Datumnotatie: aangemaakt/gewijzigd op het consentdetail tonen ook de tijd.** De opdracht vroeg dd-mm-jjjj; op het consentdetail is de tijd (UTC) na de datum blijven staan omdat "Aangemaakt" en "Laatst gewijzigd" daar altijd een tijdstip toonden en de twee gebeurtenissen op dezelfde dag anders niet te onderscheiden zijn. De lijstpagina's tonen alleen de datum.

8. **Naamveld verzoekdetail.** Sinds 4b vulde `_build_acceptance_request()` `schema:name` met het partijlabel (de organisatie), waardoor "Naam" de organisatie toonde. Nieuw: `schema:name` = `contactName` (`app.py:4956`) en de template valt voor oude records terug op `schema:name` (`verzoek_detail.html:69-71`). Bestaande records op schijf zijn niet herschreven; die zijn met `--reset` toch verdwenen.

9. **Regelnummers uit de opdracht klopten voor `5bfacf3`.** Nieuw: versieblok `57-75`, `inject_globals` `854-855`, `nl_date`-filter `2602-2605`, `_days_between` `2810`, `generate_consent_id` `3114`, `consent_list` `3147`, `consent_new` `3175`, `intenties_overview` `4071`, aanbodlink `4228-4245`, verzoeklimiet `4400-4406`, `verzoek_response` `4647-4689`, `verzoeken_overview` `4710`, `_build_acceptance_request` `4956`, opstartblok `5282`/`5306`.

10. **Inventarisatie §3 en §5 (variant A) kloppen** met wat nu lokaal bewezen is: de Bridge toont, accepteert niet, en heeft geen retourkanaal. Eén aanvulling op §5 stap 4: "aanbieden" is nu een concrete handeling (aanbodlink kopiëren), wat de inventarisatie nog open liet.

---

## 2. Per bestand: wat en waarom

### `app.py` (5258 → 5306 regels)
- **Versieblok** (`57-75`): `VERSION`, `_git_short_hash()` (subprocess `git rev-parse --short HEAD`, 5 s time-out, elke fout → leeg), `APP_VERSION`, `APP_MODE` ("Bridge"/"lokaal"), `APP_PORT`. `inject_globals()` geeft `app_version` en `app_mode` door (`854-855`).
- **Jinja-filter `nl_date`** (`2602-2605`): ISO → dd-mm-jjjj via het bestaande `format_date_nl_iso()`.
- **`_days_between()`** (`2810-2819`): naar boven afgerond (§1 punt 4).
- **`generate_consent_id()`** (`3114`): tijdzonebewuste UTC-datum; **`consent_new()`** (`3175`): `utc_now_iso_seconds()` in plaats van `utcnow()` met Z. De `DeprecationWarning` van `utcnow()` is daarmee weg uit de consentmodule; `send_crash_report()` (`104`) en `build_policy()` (`2383`) gebruiken `utcnow()` nog (buiten de opdracht).
- **`consent_list()`** (`3146-3147`): `_expiry_date` en `_created_date` als dd-mm-jjjj.
- **`intenties_overview()`** (`4071`) en **`verzoeken_overview()`** (`4710`): `_date` als dd-mm-jjjj.
- **`intentie_detail()`** (`4228-4245`): `offer_url` = host van het verzoek (lokaal) of `SHARE_BASE_URL` (Bridge, met terugval op de host) plus `url_for('verzoek_intentie')`.
- **Verzoeklimiet** (`4400-4406`): `REQUEST_RATE_LIMIT` uit `.env`, standaard 10; `is_rate_limited()` gebruikt die als er geen expliciet maximum wordt meegegeven.
- **`verzoek_response()`** (`4647`, `4660`, `4689`): Agreement-uid na intrekken; "geldig tot" als dd-mm-jjjj in beide takken.
- **`_build_acceptance_request()`** (`4956`): `schema:name` = persoon.
- **Opstartblok** (`5279-5282`, `5303-5306`): poort en versie in de startregel en `app.run(port=APP_PORT)`.

### Templates
- `base.html` (`74-75`): versieregel `<p id="app-version">MySolido <hash> · <modus></p>` onder de inhoud, boven de onderbalk; op elke pagina, ook `bridge_login`.
- `intentie_detail.html`: datums via `nl_date` (`53`, `57`); blok **Aanbodlink** (`61-88`) met alleen-lezen invoerveld, knop *Kopieer* (Clipboard API met terugval op `execCommand`, tekst wisselt twee seconden naar "Gekopieerd") en de hint; alleen bij status `actief`.
- `intenties.html` (`46`): geldig-tot via `nl_date`; de aanmaakdatum komt geformatteerd uit de route.
- `verzoek_detail.html`: datum (`70`), naamveld (`69-71`), geldig-tot in beide kaarten (`156`, `271`).
- `verzoek_response.html` (`19-21`): Agreement-uid onder "Toestemming ingetrokken op …".
- `consent_list.html` (`25`): aanmaakdatum uit de route; `consent_detail.html` (`99`, `128-138`): datums via `nl_date`, met tijd (UTC) op het detail.

### `translations.py`
NL `424-427`, EN `1152-1155`: `int_offer_link`, `int_offer_link_hint`, `int_copy`, `int_copied`.

### `scripts/seed_demo.py`
`RESET_FOLDERS`, `RUNTIME_FILES`, `reset_plan()` en `do_reset()` (`85-116`); argumenten `--reset` en `--yes` (`153-157`); in `main()` (`164-185`) eerst het plan printen, zonder `--yes` weigeren met exit 1 zonder iets te wijzigen, met `--yes` uitvoeren en daarna `--force` afdwingen; slotbericht (`212-216`). Runtime-bestanden worden leeggemaakt met de lege structuur van hun huidige type (lijst of object), niet verwijderd. Niets buiten de drie mappen en vier bestanden.

### `scripts/regressietest.py` (1932 → 2162 regels)
- Helpers `_git_short_hash()`, `_nl_date()`, `_make_accepted_case()`, `_cleanup_case()` (`1856-1911`).
- **`phase_finishing`** (`1913-1982`, 14 checks + 1 info): versieregel met hash en "lokaal"; aanbodlink met volledige URL en kopieerknop; datums dd-mm-jjjj op intentiedetail en -lijst, verzoekdetail en -lijst, responspagina, consentlijst en -detail; naamveld = persoon en `schema:name`/`rdfs:label`-verdeling; consentrecord met `+00:00` en id-datum van vandaag; Agreement-uid na intrekken; opruimen.
- **`phase_bridge_local`** (`1985-2110`, 12 checks): slaat over als poort 5001 bezet is; maakt een testketen op de lokale app; start `python app.py --bridge` met `MYSOLIDO_PORT=5001` en een eigen wachtwoordhash, wacht tot 30 s; controleert redirect naar login, login, intentiedetail (Offer-kaart, "Geaccepteerd door", aanbodlink, geen Activeren/Aanbod intrekken/Voorwaarden opstellen), consentdetail (27560-tabel, geen Intrekken, geen verzoeklink), acceptatieformulier zonder login (voorwaarden, geen formulier, Bridge-melding), POST geweigerd zonder nieuw verzoek, `/verzoeken` 403, `policy.jsonld` en `agreement.jsonld` als ld+json, versieregel met "Bridge"; stopt het proces (`kill`) en controleert dat de poort weer vrij is; ruimt de keten op. Log van het tweede proces in `%TEMP%\mysolido-bridge-test-<run>.log`.
- `--phase demo` (`2118-2119`) en de volledige run (`2136-2137`) nemen beide fasen mee.

### `scripts/regressietest.md`
Rijen 13g en 13h (`70-71`); paragraaf `--phase demo` noemt 13a t/m 13h, de vrije poort 5001 en `REQUEST_RATE_LIMIT` (`95-106`).

### `README.nl.md` (`213`)
"Elke toestemming die via een intentie tot stand komt, wordt geregistreerd conform ISO/IEC TS 27560 — …". Alleen die zin; regels 30, 226, 261 en 285 noemen 27560 ook nog in algemene bewoordingen (niet aangeraakt, zie §6).

### `.env.example`
`MYSOLIDO_PORT` en `REQUEST_RATE_LIMIT` als uitgecommentarieerde sleutels met toelichting (`13-17`). `.env` zelf niet aangeraakt.

### `docs/mysolido_demoprotocol_myterms.md` (nieuw)
Voorbereiding (Flask vers, `--reset --yes`, vensters, telefoon, eerste sync), de acht scenario-stappen met per stap pc / privévenster / telefoon en de vier sync-momenten, de bekende beperkingen, en een storingstabel.

### `docs/mysolido_uitrol-bridge_checklist.md` (nieuw)
Achttien stappen in zeven blokken: vooraf op de pc (commit, lokale test, requirements-diff, nieuwe sleutels), inloggen en huidige stand (proces, map, oude hash, `.env` met `SHARE_BASE_URL`), code bijwerken (`fetch`/`checkout`/`pull --ff-only`), herstarten en controleren (versieregel, leesroutes), sync en telefoon, terugdraaien, vastleggen. Per stap verwacht resultaat en terugweg. Geen inloggegevens in het document.

---

## 3. Lokale Bridge-modus: uitkomst punt voor punt

Tweede proces `python app.py --bridge`, `MYSOLIDO_PORT=5001`, dezelfde Pod, eigen wachtwoordhash; gestart en gestopt door de testfase. Alle punten uit de opdracht:

| Controle | Uitkomst |
|---|---|
| Tweede proces start op 5001 tegen dezelfde Pod | PASS (binnen enkele seconden; log in `%TEMP%`) |
| Zonder login redirect naar `bridge-login` | PASS |
| Inloggen met het Bridge-wachtwoord | PASS |
| Intentiedetail met Offer-kaart en "Geaccepteerd door", zonder knoppen | PASS (geen `activate`/`withdraw`-formulier, geen "Voorwaarden opstellen"; aanbodlink zichtbaar met `SHARE_BASE_URL`-terugval op de host) |
| Consentdetail met 27560-tabel zonder Intrekken | PASS (ook zonder verzoeklink, want `/verzoeken` is 403 op de Bridge) |
| `/verzoek/intentie/<uuid>` met voorwaarden, zonder formulier, met Bridge-melding | PASS (zonder login bereikbaar; melding "via de Bridge kunt u de voorwaarden alleen lezen") |
| POST accepteren geweigerd | PASS (redirect, geen nieuw verzoek) |
| `/verzoeken` 403 | PASS |
| `policy.jsonld` en `agreement.jsonld` als `application/ld+json` | PASS |
| Versieregel met "Bridge" | PASS ("MySolido 5bfacf3 · Bridge") |
| Proces gestopt, poort vrij | PASS |

Vastgelegd als **regressietestfase** (13h), niet als handmatige checklist: het starten en stoppen bleek betrouwbaar (twee runs, beide groen; bij een bezette poort slaat de fase zichzelf over). Wat de fase níet bewijst: de VPS-omgeving zelf (Linux, service, `SHARE_BASE_URL`, `scp`); daarvoor is de uitrolchecklist.

---

## 4. Uitkomst regressietest

| Run | Opdracht | Resultaat |
|---|---|---|
| 1 | `--phase demo` (eerste keer) | 133 geslaagd, **2 gefaald**: dagenduur 13 i.p.v. 14 (§1 punt 4) en een te krap tekstvenster in de eigen check op de Bridge-voettekst. Beide hersteld, Flask herstart |
| 2 | `--phase demo` (13a t/m 13h) | **135 geslaagd, 0 gefaald**, 3 info, 12 s |
| 3 | volledige run `--scenario U` (zelfde proces als run 2, `REQUEST_RATE_LIMIT=100`) | **226 geslaagd, 0 gefaald**, 2 niet automatiseerbaar (bekend: WebID-token op http, scp naar Bridge), 33 info, 19 s |

Fasen van run 3: Preflight, Accountcreatie, WebID en credentials, Bestanden en roundtrip, Identifier-normalisatie, WAC/ACL, Deellinks, ODRL-beleid, Toestemmingen en consentrequests, Demodata, Profielvelden, Intentie, Intentiepolicy, Acceptatie en Agreement, Consentrecord, **Afronding**, **Bridge-modus lokaal**, Backup en restore, /debug, Probes 7.2.0, Bridge-sync module, Persistentie aanmaken, Opruimen. Ruwe uitvoer van run 3 en run 2 in de bijlage; uitvoer van `--reset --yes` ook. Flask-log zonder fouten.

---

## 5. Handmatige controle (niet uitgevoerd, voor jou): de demo van begin tot eind, zonder adresbalk

Volg `docs/mysolido_demoprotocol_myterms.md` letterlijk; dit is de verkorte controle of alles klopt na `--reset`.

1. **Startstand.** `python app.py` (vers), `python scripts/seed_demo.py --reset --yes`. Open `http://127.0.0.1:5000`: onderaan "MySolido 5bfacf3 · lokaal" (na jouw commit: de nieuwe hash). *Mijn intenties*, *Verzoeken*, *Toestemmingen* en *Logboek* zijn leeg; *Mijn gegevens* toont het demoprofiel.
2. **Stap 1 t/m 4.** Nieuwe intentie Autoverzekering (2 weken springt voor, vier vinkjes), opslaan, openen: datums als dd-mm-jjjj, Offer-kaart, snapshot. *Activeren*: de regel **Aanbodlink** verschijnt met `http://127.0.0.1:5000/verzoek/intentie/<uuid>` en *Kopieer*; de knop zegt kort "Gekopieerd". Open een privévenster en plak de link: voorwaarden, vier labels zonder waarden, formulier met de identiteitszin en het vinkje.
3. **Stap 5 en 6.** Accepteer als Jan Jansen / Verzekeraar X BV. Bevestigingspagina met *Gegevens bekijken*; responspagina met "Verzekeraar X BV mag …", Agreement-uid, vier waarden, "geldig tot dd-mm-jjjj". Op de pc: *Verzoeken* (datum dd-mm-jjjj, badge Geaccepteerd) → detail: *Naam* toont Jan Jansen, *Organisatie* Verzekeraar X BV, kaart *Acceptatie en Agreement*, *Bekijk consentrecord*. *Toestemmingen*: record met "Intentie: Autoverzekering", datum dd-mm-jjjj; detail met de 27560-tabel en "14 dagen vanaf acceptatie". Intentie: "Geaccepteerd door Verzekeraar X BV op dd-mm-jjjj · Jan Jansen".
4. **Stap 8.** *Toestemmingen → Intrekken*. Privévenster herladen: "Toestemming ingetrokken op dd-mm-jjjj" met de Agreement-uid eronder, geen waarden. Intentie: "(toestemming ingetrokken op …)". Daarna *Aanbod intrekken* op de intentie: de aanbodlink verdwijnt van de pagina en het privévenster toont bij herladen de voorwaarden zonder formulier.
5. **Bridge, alleen als de VPS al is bijgewerkt** (checklist): na *Synchroniseer naar Bridge* op de telefoon dezelfde pagina's alleen-lezen, met "MySolido <hash> · Bridge" onderaan. Zo niet: sla over; de lokale Bridge-fase (13h) heeft hetzelfde bewezen op poort 5001.
6. **Opnieuw beginnen:** `python scripts/seed_demo.py --reset --yes`; de intentie, het verzoek, de Agreement, de response, het consentrecord en de logregels zijn weg, het profiel staat weer op de demowaarden.

---

## 6. Buiten dit verslag

**Bewust niet gedaan.** De VPS is niet aangeraakt; `sync_bridge.py` alleen gelezen; BRIDGE_MODE-logica en `check_bridge_auth()` ongewijzigd (alleen `APP_PORT` in het opstartblok). Trustpagina ongewijzigd; README alleen regel 213, terwijl regels 30, 226, 261 en 285 27560 nog algemeen noemen. `.env` niet aangeraakt (`REQUEST_RATE_LIMIT` en `MYSOLIDO_PORT` staan alleen in `.env.example`). `css-koppelvlakken.md` niet bijgewerkt met de cp1252-vondst (§1 punt 1). De datumnotatie is alleen op de demo-pagina's gedaan; dashboard, kluislisting (`%d %b %Y`), deellinks, prullenbak en logboek houden hun eigen notaties. `datetime.utcnow()` blijft in `send_crash_report()` en `build_policy()`. Geen Bridge-run op de telefoon.

**Wat er voor Boy en de andere lijsten ligt** (verzameld uit de vijf verslagen):
- **Migratie DPV-sleutels in het profiel** (verslag 2): `pd:HousingOwnership`, `pd:HouseholdSize`, `pd:Occupation`, `pd:HealthData` in `profiel.jsonld` bestaan niet in DPV-PD 2.1; `PROFILE_ATTRIBUTES` draagt de juiste termen, de opslag nog niet. Samen met de oude statuswaarden in handmatige consentrecords (normalisatie bij lezen, geen migratie op schijf, verslag 4b).
- **`/consent/new` op de 27560-bouwer** (verslag 4b): het handmatige formulier schrijft nog DPV 1-eigenschappen (`hasExpiry`, `hasExpiryTime`, `hasPersonalDataCategory`, `dpv:RightToWithdrawConsent`); besluit 20-09: blijft bestaan, niet in de demo, niet herbouwd. Zodra het wel gebeurt: `build_consent_record()` met een handmatige partij.
- **Generieke goedkeuringen zonder consentrecord** (verslag 4b): het oude `/verzoek`-pad schrijft geen record; README-zin is nu beperkt tot intentiegebonden toestemmingen. Opruimen of ook op de bouwer zetten.
- **Gemengde datumnotatie elders** (verslagen 3, 4a, 4b, dit): dd-mm-jjjj op de demo-pagina's, `jjjj-mm-dd` en `%d %b %Y` elders; plus `indent=2`/`indent=4` en `+00:00`/`Z` in de opslag (consentmodule nu `+00:00`).
- **Projectmap-bestanden buiten Pod en backup** (verslagen 19-09 en 2): `audit_log.json`, `notifications.json`, `trash.json`, `shares.json` staan in de projectmap, niet in de Pod, gaan niet mee in sync of backup-export; `--reset` maakt ze nu leeg. Ook `.mysolido/share_links.json` en de dotfile-policies vallen buiten de backup-export.
- **Retourkanaal Bridge** (verslag 19-09 §3, variant B): een verzoek dat op de Bridge binnenkomt bereikt de pc nooit; nu ondervangen door de blokkade op de Bridge en de melding. Aparte taak als de demo daarna doorgaat.
- **Identiteit van de wederpartij** (verslagen 4a, 4b): zelfverklaard, met zin op het formulier; partij-id willekeurig (open) of vooraf benoemd (gericht). Verificatie (WebID van de wederpartij, of een uitnodigingscode per gericht aanbod) is een ontwerpvraag voor de Personal Agent-definitie.
- **Meermaals accepteren** blijft onbegrensd per partij (besluit 4b); de verzoeklimiet per IP is de enige rem.
- **`count_new_requests()`** telt nu `wacht-op-bevestiging` mee (4b); de teller telt niet `ingetrokken` of `geaccepteerd` (bedoeld).
- **Sync wist niet** (checklist stap 14): records die alleen op de VPS staan blijven daar na een `--reset` op de pc; opruimen op de VPS is handwerk.
- **`dpv:isImplementedByEntity`** op gezag van de DPV-27560-gids (besluit 20-09); `dpv:hasRecipient: []` als lege lijst; beide nooit met een DPV-validator getoetst.
- **`utcnow()`** nog op twee plekken buiten de consentmodule.

**Vragen die alleen jij kunt beantwoorden.**
1. Commit van subtaak 5: de versieregel toont pas de nieuwe hash na jouw commit; tot die tijd staat er `5bfacf3` terwijl de code al verder is. Wil je de hash aanvullen met een "+"-markering bij een vuile werkboom (`git status --porcelain`), of is de commit-hash genoeg?
2. Wil je `REQUEST_RATE_LIMIT=50` (of hoger) standaard in jouw `.env` zetten voor de oefenmiddag, of houd je de standaard 10 en herstart je Flask bij problemen (storingstabel)?
3. Moeten de README-regels 30, 226, 261 en 285 dezelfde beperking krijgen als regel 213, of blijft dat voor de taak "Personal Agent-definitie" samen met de trustpagina?
4. `--reset` verwijdert ook de mappolicies in de drie mappen (§1 punt 6). Akkoord, of moeten `intenties/.policy.jsonld` en `verzoeken/.policy.jsonld` blijven staan?
5. Op de Bridge toont de aanbodlink `SHARE_BASE_URL` + pad. Wil je die link daar überhaupt tonen (de wederpartij kan er niets mee behalve lezen), of alleen lokaal?

---

## Bijlage: ruwe uitvoer

### `python scripts/seed_demo.py --reset --yes` (slot van de sessie)

```
Pod-map: C:\Users\Wim\mysolido\.data\mysolido
Pod-URL: http://127.0.0.1:3000/mysolido/

--reset gaat verwijderen (Pod):
  intenties\.policy.jsonld
  intenties\6be76b8b-ef98-4146-a936-3cb28999882f.jsonld
  intenties\6be76b8b-ef98-4146-a936-3cb28999882f.policy.jsonld
  intenties\94ee79c5-27d7-4035-9745-c8611b89a33d.jsonld
  intenties\94ee79c5-27d7-4035-9745-c8611b89a33d.policy.jsonld
  intenties\a0ac025c-0521-42cc-bb0e-d68f943cff70.jsonld
  intenties\a0ac025c-0521-42cc-bb0e-d68f943cff70.policy.jsonld
  intenties\fb9189cb-7e53-4d80-930d-a2681b1a494a.jsonld
  intenties\fb9189cb-7e53-4d80-930d-a2681b1a494a.policy.jsonld
  verzoeken\.policy.jsonld
  verzoeken\562ec811-716b-4317-ac63-f5f4cdad1da3.agreement.jsonld
  verzoeken\562ec811-716b-4317-ac63-f5f4cdad1da3.jsonld
  verzoeken\562ec811-716b-4317-ac63-f5f4cdad1da3_response.json
  verzoeken\9e44614f-cbbe-4ac7-8ee1-a81ec08497b6.agreement.jsonld
  verzoeken\9e44614f-cbbe-4ac7-8ee1-a81ec08497b6.jsonld
  verzoeken\9e44614f-cbbe-4ac7-8ee1-a81ec08497b6_response.json
  toestemmingen\20260920-001.jsonld
--reset gaat leegmaken (projectmap):
  audit_log.json
  trash.json
  shares.json
--reset zet daarna profiel/profiel.jsonld opnieuw (als --force).
[OK] 17 bestanden verwijderd, 3 runtime-bestanden leeggemaakt.


Aangemaakt:
  mappen (0 nieuw, 20 bestonden al): -
  profiel/profiel.jsonld (overschreven)
  profiel/.policy.jsonld (bestond al)
  voertuigen/demo-kentekenbewijs.txt
  voertuigen/demo-apk-rapport-2026.txt
  financieel/demo-jaaroverzicht-2025.txt

Demoprofiel (scenario-attributen):
  urn:mysolido:attribute:age_category           35-44
  urn:mysolido:attribute:postal_area            5611
  urn:mysolido:attribute:vehicle_type           Auto
  urn:mysolido:attribute:claims_history         Schadevrije jaren: 5, Schade geclaimd in de laatste 3 jaar: nee

Niet aangeraakt: intenties/, verzoeken/, toestemmingen/ en alle overige bestaande bestanden.
```

### Run 3: `python scripts/regressietest.py --scenario U` (volledige run, `REQUEST_RATE_LIMIT=100`)

```
MySolido regressietest 2026-09-20 16:32 -- scenario U, fase all, CSS http://127.0.0.1:3000 (7.2.0), Flask http://127.0.0.1:5000, Pod http://127.0.0.1:3000/mysolido/

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
  [PASS] Test-Pod aanmaken  -- http://127.0.0.1:3000/regressietest-pod-eba0e5/
  [PASS] Test-Pod staat op schijf als .data/<podnaam>/  -- C:\Users\Wim\mysolido\.data\regressietest-pod-eba0e5
  [PASS] Test-WebID publiek bereikbaar met solid:oidcIssuer  -- http://127.0.0.1:3000/regressietest-pod-eba0e5/profile/card#me
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
  [PASS] Toestemming: JSON-LD velden correct  -- 20260920-002
  [PASS] Toestemming: detailpagina leest record terug
  [PASS] Toestemming: record niet publiek via CSS  -- status 401
  [PASS] Toestemming: CSS serveert .jsonld als application/ld+json  -- application/ld+json
  [PASS] Toestemming: intrekken zet status dpv:ConsentWithdrawn
  [PASS] Toestemming: verwijderen
  [PASS] Consentrequest: verzoek via publiek formulier weggeschreven
  [PASS] Consentrequest: JSON-LD velden correct en statustoken in bevestiging  -- 0c03de94-8808-4ea4-9dd2-7b7afc2c235d
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
  [PASS] Intentiepolicy: intenties/<uuid>.policy.jsonld geschreven  -- e7963855-ba78-4de7-8b2e-45d4560b249f.policy.jsonld
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
  [PASS] Consentrecord: verzoek heeft mysolido:consent en toestemmingen/<id>.jsonld bestaat  -- 20260920-002
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
  [PASS] Consentrecord: detailpagina toont status ConsentWithdrawn en het withdrawn-eventC:\Users\Wim\mysolido\scripts\regressietest.py:1970: DeprecationWarning: datetime.datetime.utcnow() is deprecated and scheduled for removal in a future version. Use timezone-aware objects to represent datetimes in UTC: datetime.datetime.now(datetime.UTC).
  str(con.get('dct:created', '')).endswith('+00:00') and cid.startswith(datetime.utcnow().strftime('%Y%m%d')),

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

== Afronding (versieregel, aanbodlink, datums) ==
  [PASS] Afronding: versieregel in de voettekst met commit-hash en "lokaal"  -- 5bfacf3
  [PASS] Afronding: testketen (intentie, acceptatie, consentrecord) aangemaakt
  [PASS] Afronding: aanbodlink met volledige URL en kopieerknop op de actieve intentie
  [PASS] Afronding: intentiedetail toont Aangemaakt en Geldig tot als dd-mm-jjjj
  [PASS] Afronding: intentielijst toont datums als dd-mm-jjjj
  [PASS] Afronding: verzoekdetail toont de persoon in het naamveld en de datum als dd-mm-jjjj
  [PASS] Afronding: schema:name van het verzoek is de persoon, rdfs:label de organisatie
  [PASS] Afronding: verzoeklijst toont de datum als dd-mm-jjjj
  [PASS] Afronding: responspagina toont "geldig tot" als dd-mm-jjjj
  [PASS] Afronding: consentlijst toont aanmaakdatum en geldigheid als dd-mm-jjjj
  [PASS] Afronding: consentdetail toont datums als dd-mm-jjjj
  [PASS] Afronding: consentrecord gebruikt +00:00-notatie zonder Z en de id-datum van vandaag (UTC)
  [PASS] Afronding: responspagina na intrekken toont de Agreement-uid
  [INFO] Afronding: REQUEST_RATE_LIMIT uit .env  -- alleen bij opstart gelezen; niet in deze run getest
  [PASS] Afronding: testketen opgeruimd

== Bridge-modus lokaal (tweede proces, poort 5001) ==
  [PASS] Bridge lokaal: testketen op de lokale app aangemaakt
  [PASS] Bridge lokaal: tweede proces gestart met --bridge op poort 5001
  [PASS] Bridge lokaal: zonder login redirect naar bridge-login
  [PASS] Bridge lokaal: inloggen met het Bridge-wachtwoord
  [PASS] Bridge lokaal: intentiedetail met Offer-kaart en "Geaccepteerd door", zonder knoppen
  [PASS] Bridge lokaal: consentdetail met 27560-tabel, zonder Intrekken
  [PASS] Bridge lokaal: acceptatieformulier toont voorwaarden zonder formulier, met Bridge-melding (zonder login)
  [PASS] Bridge lokaal: POST accepteren geweigerd, geen nieuw verzoek
  [PASS] Bridge lokaal: /verzoeken geeft 403
  [PASS] Bridge lokaal: policy.jsonld en agreement.jsonld als application/ld+json
  [PASS] Bridge lokaal: versieregel met "Bridge"  -- 5bfacf3
  [PASS] Bridge lokaal: tweede proces gestopt

== Backup en restore ==
  [PASS] Backup: zip-export  -- 17268 bytes
  [PASS] Backup: bevat testbestand met juiste inhoud  -- regressietest/ldp/roundtrip.txt
  [INFO] Backup: .policy.jsonld en .acl in zip  -- ja
  [INFO] Backup: .mysolido/share_links.json in zip  -- nee
  [PASS] Restore: bestand uit zip teruggezet en via CSS leesbaar

== Flask /debug (HTTP-laag) ==
  [PASS] Flask /debug: HTTP-lezing van Pod-root via CSS (root is publiek)

== Probes 7.2.0-changelog ==
  [INFO] Probe dubbele slug: twee POSTs met Slug slug-test.txt  -- 201 http://127.0.0.1:3000/mysolido/regressietest/ldp/slug-test.txt | 201 http://127.0.0.1:3000/mysolido/regressietest/ldp/9db97376-bb29-4a2e-873e-5e969a5b5fcf; op schijf ['slug-test.txt']
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
  [PASS] Opruimen: test-Pod-map van schijf verwijderd  -- C:\Users\Wim\mysolido\.data\regressietest-pod-eba0e5
  [INFO] Opruimen: runtime-bestanden in projectmap (trash.json, shares.json, audit_log.json, notifications.json)  -- blijven staan, vallen onder .gitignore

Resultaat: 226 geslaagd, 0 gefaald, 2 niet automatiseerbaar, 33 info (19s)
```

### Run 2: `python scripts/regressietest.py --phase demo` (13a t/m 13h)

```
MySolido regressietest 2026-09-20 16:32 -- scenario U, fase demo, CSS http://127.0.0.1:3000 (7.2.0), Flask http://127.0.0.1:5000, Pod http://127.0.0.1:3000/mysolido/

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
  [PASS] Intentiepolicy: intenties/<uuid>.policy.jsonld geschreven  -- ce7acff5-6cf4-4abf-99dd-5e84ca14d374.policy.jsonld
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
  [PASS] Consentrecord: verzoek heeft mysolido:consent en toestemmingen/<id>.jsonld bestaat  -- 20260920-002
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
  [PASS] Consentrecord: intrekken zet dpv:ConsentWithdrawn, tweede event withdrawn door WEBID, dct:modified gezetC:\Users\Wim\mysolido\scripts\regressietest.py:1970: DeprecationWarning: datetime.datetime.utcnow() is deprecated and scheduled for removal in a future version. Use timezone-aware objects to represent datetimes in UTC: datetime.datetime.now(datetime.UTC).
  str(con.get('dct:created', '')).endswith('+00:00') and cid.startswith(datetime.utcnow().strftime('%Y%m%d')),

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

== Afronding (versieregel, aanbodlink, datums) ==
  [PASS] Afronding: versieregel in de voettekst met commit-hash en "lokaal"  -- 5bfacf3
  [PASS] Afronding: testketen (intentie, acceptatie, consentrecord) aangemaakt
  [PASS] Afronding: aanbodlink met volledige URL en kopieerknop op de actieve intentie
  [PASS] Afronding: intentiedetail toont Aangemaakt en Geldig tot als dd-mm-jjjj
  [PASS] Afronding: intentielijst toont datums als dd-mm-jjjj
  [PASS] Afronding: verzoekdetail toont de persoon in het naamveld en de datum als dd-mm-jjjj
  [PASS] Afronding: schema:name van het verzoek is de persoon, rdfs:label de organisatie
  [PASS] Afronding: verzoeklijst toont de datum als dd-mm-jjjj
  [PASS] Afronding: responspagina toont "geldig tot" als dd-mm-jjjj
  [PASS] Afronding: consentlijst toont aanmaakdatum en geldigheid als dd-mm-jjjj
  [PASS] Afronding: consentdetail toont datums als dd-mm-jjjj
  [PASS] Afronding: consentrecord gebruikt +00:00-notatie zonder Z en de id-datum van vandaag (UTC)
  [PASS] Afronding: responspagina na intrekken toont de Agreement-uid
  [INFO] Afronding: REQUEST_RATE_LIMIT uit .env  -- alleen bij opstart gelezen; niet in deze run getest
  [PASS] Afronding: testketen opgeruimd

== Bridge-modus lokaal (tweede proces, poort 5001) ==
  [PASS] Bridge lokaal: testketen op de lokale app aangemaakt
  [PASS] Bridge lokaal: tweede proces gestart met --bridge op poort 5001
  [PASS] Bridge lokaal: zonder login redirect naar bridge-login
  [PASS] Bridge lokaal: inloggen met het Bridge-wachtwoord
  [PASS] Bridge lokaal: intentiedetail met Offer-kaart en "Geaccepteerd door", zonder knoppen
  [PASS] Bridge lokaal: consentdetail met 27560-tabel, zonder Intrekken
  [PASS] Bridge lokaal: acceptatieformulier toont voorwaarden zonder formulier, met Bridge-melding (zonder login)
  [PASS] Bridge lokaal: POST accepteren geweigerd, geen nieuw verzoek
  [PASS] Bridge lokaal: /verzoeken geeft 403
  [PASS] Bridge lokaal: policy.jsonld en agreement.jsonld als application/ld+json
  [PASS] Bridge lokaal: versieregel met "Bridge"  -- 5bfacf3
  [PASS] Bridge lokaal: tweede proces gestopt

Resultaat: 135 geslaagd, 0 gefaald, 0 niet automatiseerbaar, 3 info (12s)
```
