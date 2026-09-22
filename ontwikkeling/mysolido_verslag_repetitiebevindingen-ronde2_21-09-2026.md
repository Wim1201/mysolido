# MySolido — verslag repetitiebevindingen ronde 2, 21-09-2026

| | |
|---|---|
| Datum | 21-09-2026, 15:46–18:05 |
| Uitgangshash | d12adba op branch `myterms-demo` (werkboom schoon voor .py, .html en .css; alleen ongetrackte .md-bestanden) |
| Omgeving | pc Wim, repo `C:\Users\Wim\mysolido`, Python 3.13, CSS 7.2.0 op poort 3000, Pod `http://127.0.0.1:3000/mysolido/`; Claude Code (desktopapp) met browserpaneel |
| Vervolg op | `docs/mysolido_verslag_generale-repetitie-myterms_21-09-2026.md` (de B-nummers) en `docs/mysolido_verslag_bridge-authenticatie_21-09-2026.md` (ronde 1, gecommit als d12adba) |
| Van/aan | Claude Code → Wim; Wim leest de diff en commit zelf |
| Git en VPS | niets gecommit, niets gepusht, VPS niet aangeraakt |

## Correcties op eerdere bevindingen (vóór al het nieuwe)

1. **B7 "auto-sync met ~2,5 minuut vertraging": er was geen auto-sync.** `.env` op de pc staat op `BRIDGE_AUTO_SYNC=false`. De profielpagina toonde toch "Aan — synchroniseert na elke wijziging", omdat de template op `bridge_sync_status.running is not none` testte, en `running` is altijd een boolean: de tekst stond dus áltijd op "Aan". Bovendien reageert auto-sync (als hij aan staat) alleen op bestandsbewerkingen in de kluis (uploaden, verwijderen, verplaatsen, delen, intrekken van een deling; `auto_sync_after_change()` wordt nergens in de intentie-, verzoek- of toestemmingsroutes aangeroepen). Vermoeden, niet vastgesteld: de syncs van 09:40:06 en 10:06:22 uit het repetitieverslag waren handmatige syncs waarvan het kopiëren (`scp -r` van de hele pod) ruim twee minuten duurde; "Bezig…" bleef staan tot herladen. De oorspronkelijke waarneming blijft in het repetitieverslag staan.
2. **B6: `_status` stond niet in de bestanden.** De sleutels `_status` en `_id` werden alleen bij het tonen aan het record-dict toegevoegd (`consent_list()`, `consent_detail()`); `consent_withdraw()` leest en schrijft het bestand rechtstreeks, zonder die sleutels. De ruwe weergave dumpte het verrijkte dict en toonde ze daardoor. Geen migratie nodig; de demo-Pod bevat geen records met `_status`.
3. **B1 is één CSS-botsing, geen fout in de templates.** Zie de inventaris van 15:5x en de oplossing hieronder. De markup stond overal al op de juiste plek.
4. **Uit ronde 1, blijft gelden:** het vermoede lek op de Bridge reproduceert niet; de routetabel-lus in 13h bevestigt dat alles buiten de openbare lijst dicht is.

## Tijdstempels

| Tijd | Handeling |
|---|---|
| 15:46 | Controlepunt: HEAD d12adba, branch `myterms-demo`, geen gewijzigde .py/.html/.css. Repetitieverslag gelezen. |
| 15:47–15:55 | **Stap 1, B1-inventaris:** CSS en templates gelezen; in het browserpaneel op Wims Flask op 5000 (alleen lezen) gemeten dat een badge in een kaart `position: absolute; top: -4px; right: -6px` krijgt en dat de pagina horizontaal schuift. Lijst en voorstel aan Wim voorgelegd; **gestopt**. |
| 17:4x | Akkoord van Wim (met de twee aanvullingen voor de lijst "handmatig te controleren"). |
| 17:46 | **Stap 2, B1:** `style.css` aangepast. |
| 17:52 | **Stap 4/6/8, app.py en translations.py:** B4, B5, B6, B7-vlag, B8-foutafhandelaars, tijdfilter `nl_datetime`; vertalingen NL en EN. |
| 17:54 | **Stap 3/5/7/8, templates en CSS:** B2, B7, B8, B9, tabtitels, kaart Acties, formulierstijl, pod-adres. Jinja-controle via de Flask-omgeving. |
| 17:57 | **Stap 9:** regressietest uitgebreid; vers proces `MYSOLIDO_PORT=5010 REQUEST_RATE_LIMIT=100 python app.py` gestart; eerste run: 170 geslaagd, 3 gefaald (alle drie fouten in mijn nieuwe testregels, zie stap 9). |
| 17:58 | Testregels gecorrigeerd; tweede run: **173 geslaagd, 0 gefaald, 0 niet automatiseerbaar, 4 info (13 s)**. Geen achtergebleven testrecords in de Pod. |
| 17:59 | Browsercontrole op 5010: `/verzoek` met formulierstijl, `/profile` met knop Toestemmingen; auto-sync-regel "Uit — …", geen badges absoluut, geen horizontale schuifbalk. Proces op 5010 gestopt. |
| 18:01 | **Stap 10:** datamodelnotitie §5 en rij Consentrecord; demoprotocol bijgewerkt. |
| 18:05 | Dit verslag. |

## Per bevinding: oorzaak, wijziging, bestand en regel, hoe getest

### B1 — badges rechtsboven in de pagina, horizontale schuifbalk

- **Oorzaak.** [static/css/style.css:147](../static/css/style.css) definieerde het rode tellertje op de meldingenbel als generiek `.badge { position: absolute; top: -4px; right: -6px }`. De statusbadges gebruiken dezelfde klasse; het tweede `.badge`-blok (kleur, padding) zette `position` niet terug. Zonder gepositioneerde ouder verankerden alle statusbadges aan de pagina: 4 px boven de bovenrand (iPhone: in de statusbalk), 6 px voorbij de rechterrand (de schuifbalk). Op /consent ging het goed door de eigen klasse `.consent-status-badge`.
- **Wijziging.** Selector beperkt tot de bel: `.bell-link .badge` (style.css:149); in het generieke `.badge`-blok expliciet `position: static; vertical-align: middle` (style.css:1665). Geen templates aangepast. Gecontroleerd dat de bel in `base.html:35` werkelijk `class="bell-link"` heeft met daarin `<span class="badge">`.
- **Getest.** Statische controle in de test (Afronding (B1), regressietest.py:1951). Visueel: badge-proef op /profile zonder absolute positionering, `scrollWidth` = `clientWidth`. De bel zelf en de posities op de iPhone staan op de lijst "handmatig te controleren".

### B2 — Toestemmingen onbereikbaar op de telefoon

- **Wijziging.** Knop *Toestemmingen* (`t.nav_consent`, `id="btn-consent"`) op het profiel tussen *Mijn intenties* en *Inkomende verzoeken* ([templates/profile.html:33](../templates/profile.html)), lokaal én op de Bridge. Onderbalk ongewijzigd.
- **Getest.** Lokaal (regressietest.py:1957) en op de Bridge met sessie (2212).

### B4 — einddatum Agreement versus consentrecord (optie A)

- **Oorzaak.** `build_consent_record()` schreef naast `mysolido:validUntil` een blok `dpv:hasDuration` met `mysolido:days` (naar boven afgeronde dagen van acceptatie tot validUntil) en `mysolido:iso8601`; de detailpagina toonde dat als "14 dagen vanaf acceptatie". Zo stonden er twee looptijden.
- **Keuze: weglaten.** Alleen `mysolido:validUntil` (= `schema:validThrough` van de intentie) blijft; `dpv:hasDuration` wordt niet meer geschreven ([app.py:2887](../app.py), 2937). Reden: één einddatum, één bron; de duur was een afgeleide die verwarring gaf, en wie hem nodig heeft rekent hem uit `events[given].at` en `validUntil`. Het alternatief (werkelijke duur in hele seconden of ISO-8601) zou het record opnieuw twee getallen geven die bij een gericht aanbod, dat pas na bevestiging sluit, ook nog eens per acceptatie verschillen. Bestaande records met `hasDuration` blijven leesbaar; de template toont het blok niet meer. De helper `_days_between()` is verwijderd.
- **Detailpagina.** Rij *Geldigheid*: "geldig tot <datum> · de einddatum van het aanbod (schema:validThrough van de intentie; de Agreement heeft geen eigen einddatum)" ([templates/consent_detail.html:57](../templates/consent_detail.html); nieuwe sleutel `consent_27560_end_of_offer` in `translations.py`, `consent_27560_days` vervalt).
- **Getest.** Record zonder `hasDuration` en `validUntil` = `validThrough` (regressietest.py:1700); tekst op de pagina, "vanaf acceptatie" afwezig (1735).

### B5 — Verwijderen op consentrecords met Agreement (optie A)

- **Wijziging.** `consent_delete()` leest het record en weigert bij `mysolido:agreement` met de melding "Op deze toestemming rust een Agreement; ze kan worden ingetrokken, maar niet verwijderd." en redirect naar het detail ([app.py:3401](../app.py)). Knop weg in de lijst ([templates/consent_list.html:47](../templates/consent_list.html)) en in het detail, waar de uitleg staat (`id="consent-agreement-note"`, [templates/consent_detail.html:172](../templates/consent_detail.html)). Handmatige toestemmingen zonder Agreement houden hun knop.
- **Getest.** Detail zonder knop en met uitleg (1740), lijst zonder knop (1747), route weigert en bestand blijft (1750), ook na intrekken (1795). De bestaande test die een handmatige toestemming verwijdert (fase Toestemmingen en consentrequests) slaagt nog.

### B6 — `_status` in de ruwe JSON

- **Uitkomst.** Stond **niet** in het bestand (zie correctie 2).
- **Wijziging.** `consent_detail()` leest de bestandstekst en geeft die als `raw_json` door ([app.py:3302](../app.py)); de template toont `{{ raw_json }}` in plaats van het verrijkte dict ([templates/consent_detail.html:184](../templates/consent_detail.html)). De regel staat als commentaar bij de route. De weergavesleutels blijven in het geheugen voor badge en tabel. Gevolg, bewust: bij een oud record met `dpv:ConsentStatusGiven` toont de tabel de genormaliseerde term en de ruwe JSON de oude, want dat is wat er staat; de bestaande test daarop is daarop aangepast (regressietest.py:1850).
- **Getest.** Geschreven bestand zonder `_`-sleutels (1703); ruwe weergave zonder `_status`/`_filename`, mét `dct:conformsTo` (1737).

### B7 — auto-sync: tekst en zelfverversende status

- **Hoe het werkelijk werkt.** `sync_bridge.py`: `sync_to_bridge()` doet een `ssh mkdir` en daarna `scp -r` van de hele pod-map; `auto_sync_after_change()` start dat 2 s na een bestandsbewerking, alleen als `BRIDGE_AUTO_SYNC=true`. De status (`running`, `last_sync`, `last_result`, `error`) leeft in het geheugen van het Flask-proces; `last_sync` is lokale tijd zonder tijdzone. Het mechanisme is niet aangeraakt.
- **Wijziging.** De profielpagina toont de werkelijke vlag: `bridge_auto_sync` uit de context processor ([app.py:30](../app.py), 878) en `id="sync-auto"` in [templates/profile.html:168](../templates/profile.html). Teksten (NL en EN): "Aan — start 2 seconden na een bestandswijziging in de kluis (uploaden, verwijderen, verplaatsen, delen). Intenties, verzoeken en toestemmingen synchroniseren niet vanzelf; het kopiëren zelf kan enkele minuten duren." en "Uit — synchroniseer met de knop hieronder (…)". Zolang de status "Bezig…" is, haalt een script elke 3 s `/bridge-sync/status` op en zet badge, *Laatste sync* en foutregel bij zonder herladen (profile.html:182). *Laatste sync* nu als dd-mm-jjjj HH:MM.
- **Getest.** Tekst volgt de vlag en belooft geen sync "na elke wijziging" (regressietest.py:1961). Het zelfverversen is niet automatisch getest (vereist een echte sync naar de VPS): handmatig.

### B8 — knop *Inkomende verzoeken* op de Bridge, kale Engelse 403

- **Wijziging.** Knop verborgen in bridge-modus (`{% if not bridge_mode %}`, profile.html:36). Nieuwe foutafhandelaars voor 403 en 404 ([app.py:5327](../app.py), 5335) die `error.html` in de gewone opmaak tonen, in het Nederlands: "Geen toegang" met op de Bridge "De Bridge is alleen-lezen; beheren doe je in je lokale MySolido." en "Pagina niet gevonden". `error.html` kreeg een optionele kop (`heading`). De 500-afhandelaar is ongewijzigd. Pagina's die zelf een 404 renderen (statuspagina, responspagina met onbekend token) doen dat nog steeds met hun eigen tekst.
- **Getest.** Bridge: /verzoeken geeft 403 in het Nederlands met navigatie (2205), 404 met sessie (2209), profiel zonder knop (2212); lokaal 404 (1968) en profiel mét knop (1957). Zonder sessie blijft alles op de Bridge een redirect naar het inlogscherm (routetabel-lus uit ronde 1).

### B9 — teksten in bridge-modus

- **Wijziging.** Onder de aanbodlink op het intentiedetail in bridge-modus: "Geef deze link aan de wederpartij; daar leest ze de voorwaarden. Accepteren gebeurt via de lokale kluis van de eigenaar, niet via de Bridge." (`int_offer_link_hint_bridge`, [templates/intentie_detail.html:69](../templates/intentie_detail.html)). Kopzin op de Bridge-voorwaardenpagina bij een actief aanbod: "… U leest ze hier; accepteren gebeurt via de lokale kluis van de eigenaar, niet via de Bridge." (`req_int_intro_bridge`, [templates/verzoek_intentie.html:48](../templates/verzoek_intentie.html)); bij een inactief aanbod blijft de bestaande tekst "niet actief".
- **Getest.** Beide teksten op de Bridge (2218, 2222).

### Cosmetisch

| Punt | Wijziging | Waar | Getest |
|---|---|---|---|
| Tijden in Nederlandse tijd | Filter `nl_datetime`: ISO-tijdstip → dd-mm-jjjj HH:MM in Europe/Amsterdam (zoneinfo, met een EU-zomertijdterugval zonder tijdzonedatabase); tijdstippen zonder tijdzone (`last_sync`) worden niet verschoven. Records blijven UTC. Toegepast op verzoekdetail (*Geaccepteerd op*, met de UTC-waarde uit het record ernaast), consentrecord (gebeurtenissen, aangemaakt/gewijzigd, ook de oude vorm) en *Laatste sync*. | [app.py:2645](../app.py), 2667; consent_detail.html:71, 100, 129, 133; verzoek_detail.html:110; profile.html | 1743, 1756; filter handmatig gecontroleerd op 21-09 10:49 (zomertijd) en 15-01 09:49 (wintertijd) |
| Tabtitels | bevestiging na acceptatie "Voorwaarden geaccepteerd"; responspagina na intrekken "Toestemming ingetrokken" | verzoek_bevestiging.html:3, verzoek_response.html:3 | 1778 (response); bevestiging handmatig |
| Kaart *Acties* | alleen tonen als er een actie is (`has_actions`) | intentie_detail.html:202 | 2279 |
| Invoervelden acceptatieformulier | gedeelde regel `.form-input` (plus `:focus`) in style.css; de scoped varianten blijven | style.css:1115 | statisch (1953) en visueel op /verzoek |
| Intern pod-adres op de Bridge | `Pod: …` niet tonen in bridge-modus op dashboard (twee plekken) en profiel | index.html:210, 391; profile.html:11 | 2212, 2216 |

## Uitkomst regressietest

```
MySolido regressietest 2026-09-21 17:58 -- scenario U, fase demo, CSS http://127.0.0.1:3000 (7.2.0), Flask http://127.0.0.1:5010
Resultaat: 173 geslaagd, 0 gefaald, 0 niet automatiseerbaar, 4 info (13s)
```

Ronde 1 had 151 checks; er zijn er 22 bij. De eerste run (17:57) gaf drie fouten, alle drie in mijn nieuwe of aangepaste testregels, niet in de app: (1) de ruwe JSON wordt door Jinja ge-escaped (`&#34;`), dus de check op `"dct:conformsTo"` met aanhalingstekens sloeg niet aan; (2) de bestaande test op de oude statusterm zocht `ConsentStatusGiven` in de hele pagina, terwijl de ruwe weergave die term nu terecht toont (B6); (3) de WebID bevat het pod-adres als voorvoegsel, dus de check op "geen intern pod-adres" moest op de letterlijke regel `Pod: <url>` testen. Na correctie: 0 gefaald. De Pod-demostand is niet aangeraakt buiten wat de test aanmaakt en opruimt; controle achteraf: geen `Regressietest`-records in intenties, verzoeken of toestemmingen. Uitvoer en JSON staan in de scratchpad van deze sessie.

## Gewijzigde en nieuwe bestanden (voor `git add`)

| Bestand | Status | Wat |
|---|---|---|
| `app.py` | M | import auto-sync-vlag (30), context processor (878), `_amsterdam_offset`/`format_datetime_nl`/filter `nl_datetime` (2635–2670), B4 in `build_consent_record()` (2887, 2937; `_days_between` verwijderd), B6 in `consent_detail()` (3302), B5 in `consent_delete()` (3395–3402), foutafhandelaars 403/404 (5327–5338) |
| `translations.py` | M | nieuwe sleutels NL+EN: `bridge_sync_refreshing`, `error_403_*`, `error_404_*`, `flash_consent_has_agreement`, `consent_has_agreement_note`, `consent_27560_end_of_offer` (vervangt `consent_27560_days`), `int_offer_link_hint_bridge`, `req_int_intro_bridge`, `time_local_note`; gewijzigd `bridge_auto_sync_on/off` |
| `static/css/style.css` | M | B1 (149, 1665), `.form-input` (1115) |
| `templates/profile.html` | M | B2, B7 (tekst, ids, script), B8, pod-adres |
| `templates/consent_detail.html` | M | B4-rij, B5-knop en uitleg, B6-ruwe weergave, tijden |
| `templates/consent_list.html` | M | B5-knop |
| `templates/intentie_detail.html` | M | B9-hint, kaart Acties |
| `templates/verzoek_intentie.html` | M | B9-kopzin |
| `templates/verzoek_detail.html` | M | acceptatietijd |
| `templates/verzoek_bevestiging.html`, `templates/verzoek_response.html` | M | tabtitels |
| `templates/index.html` | M | pod-adres (twee plekken) |
| `templates/error.html` | M | optionele kop |
| `scripts/regressietest.py` | M | 22 nieuwe checks, 2 aangepaste (B4-record, oude statusterm) |
| `docs/mysolido_notitie_datamodel-myterms_20-09-2026.md` | M | rij Consentrecord (storage, verwijderen) en nieuw §5 met de besluiten B4, B5, B6 |
| `docs/mysolido_demoprotocol_myterms.md` | M | aanpassingen uit het repetitieverslag plus de wijzigingen van deze ronde |
| `docs/mysolido_verslag_repetitiebevindingen-ronde2_21-09-2026.md` | nieuw | dit verslag |

Niet aangeraakt: `BRIDGE_PUBLIC_ENDPOINTS`, `check_bridge_auth()`, `templates/base_public.html`, `sync_bridge.py`. De al ongetrackte .md-bestanden van eerder vandaag staan er nog net zo.

## Handmatig te controleren (wat de test niet ziet)

| # | Pagina | Verwachting |
|---|---|---|
| 1 | Intentielijst en intentiedetail, pc | badge *Concept*/*Actief*/*Ingetrokken* in de kaartkop rechts naast de titel, niet rechtsboven in de pagina; geen horizontale schuifbalk |
| 2 | Verzoekenlijst en verzoekdetail, pc | badge *Geaccepteerd*/*Toestemming ingetrokken* in de regel resp. kaartkop; op het detail de groepslabels (badge-concept/goedgekeurd) naast elkaar in de kaart, niet gestapeld rechtsboven |
| 3 | Intentiedetail, "Geaccepteerd door", na intrekken | "(toestemming ingetrokken op …)" direct achter de naam, op dezelfde regel of eronder bij weinig ruimte |
| 4 | Responspagina en statuspagina wederpartij | badge onder de titel in de kaart |
| 5 | iPhone (Bridge), dezelfde pagina's | geen badge over de iOS-statusbalk; geen horizontale schuifbalk (pagina laat zich niet zijwaarts slepen) |
| 6 | Smal scherm (~380 px), lange titel met badge erachter (bijv. intentiedetail) | de badge mag naar de volgende regel vallen; geen horizontale schuifbalk |
| 7 | Meldingenbel in de kop (lokaal, met ≥1 ongelezen melding) | rood tellertje nog steeds rechtsboven op de bel, zoals vóór deze ronde (`.bell-link .badge`) |
| 8 | Profiel, knop *Inkomende verzoeken* met nieuwe verzoeken | het aantal als blauw getal in de knop achter de tekst (was nooit op de knop) |
| 9 | Profiel → *Nu synchroniseren* (pc met VPS) | status gaat naar "Bezig… (de status ververst vanzelf)" en springt zonder herladen naar "Gesynchroniseerd" met nieuw tijdstip dd-mm-jjjj HH:MM; bij een fout de foutregel |
| 10 | Bevestigingspagina na acceptatie (privévenster) | tabtitel "Voorwaarden geaccepteerd - MySolido"; kale opmaak |
| 11 | Bridge op de telefoon: Profiel | knop *Toestemmingen* aanwezig en werkend; *Inkomende verzoeken* afwezig; geen "Pod: http://127.0.0.1:3000/…" (de WebID-regel staat er nog, zie "Buiten dit verslag") |
| 12 | Consentrecord, pc en telefoon | *Geldigheid* noemt de einddatum van het aanbod; tijden in Nederlandse tijd; geen *Verwijderen* maar de uitlegzin; ruwe JSON zonder `_status` |
| 13 | Telefoon, `/verzoeken` via het adres | Nederlandse pagina "Geen toegang" in de gewone opmaak |

## Buiten dit verslag

- **Jouw Flask op poort 5000 draait nog de code van d12adba** (geen reloader). Herstart hem om de wijzigingen te zien; de browsermetingen op 5000 waren alleen-lezen. De schrijvende test draaide op 5010, dat proces is gestopt.
- **WebID op de Bridge.** De regel `http://127.0.0.1:3000/mysolido/profile/card#me` staat nog op het Bridge-profiel; de opdracht betrof alleen het pod-adres. Of de WebID daar ook weg moet, is een aparte keuze (het demoprotocol noemt het bewust als "eerlijk over wat er draait").
- **Auto-sync inhoudelijk.** Dat intenties, verzoeken en toestemmingen nooit auto-sync triggeren, is nu eerlijk in de tekst, maar niet veranderd (opdracht: mechanisme niet aanraken). Wil je het wel, dan is dat één aanroep van `auto_sync_after_change()` in `conclude_agreement()`, `consent_withdraw()`, `intentie_new()`, `intentie_activate()` en `intentie_withdraw()`; de kopieertijd van `scp -r` blijft.
- **B4 optie B ("looptijd vanaf acceptatie") en het delen van documenten in een aanbod:** ontwerpwerk voor later, niet gedaan.
- **VPS:** niet aangeraakt; draait d12adba. Uitrol volgens `docs/mysolido_uitrol-bridge_checklist.md`, en denk aan het legen van de drie recordmappen daar (staat nu in het demoprotocol, A3).
- **Geparkeerde punten uit de CSS-upgrade** (backup-export, welkomstscherm, `$.ext`, `README$.markdown` in de listing, "draait al"-controle, auto_setup, trash-id's): niet gedaan, eigen ronde. `README$.markdown` in de Bridge-root uit het repetitieverslag hoort daarbij.
- **Demoprotocol-teksten** zijn bijgewerkt naar de nieuwe knopnaam *Nu synchroniseren* (de tekst van de knop op het profiel); de oude naam "Synchroniseer naar Bridge" komt er niet meer in voor.
- **Niet gecommit, niet gepusht**; jij leest de diff en commit zelf. De `git`-waarschuwingen "LF will be replaced by CRLF" betreffen bestanden die al LF waren.

---

# Ronde 2b: visuele test (21-09-2026, 18:14–18:35)

| | |
|---|---|
| Uitgangspunt | d12adba plus de ongecommitte wijzigingen van ronde 2 (16 bestanden en dit verslag); controlepunt 18:14 klopte |
| Omgeving | zelfde pc; Playwright 1.53.0 voor Python met Chromium 138.0.7204.23 (desktop 1366×768) en **WebKit 18.5, de Playwright-build op Windows, niet Safari op iOS** (apparaatprofiel iPhone 13, 390×844, touch, mobiele user-agent) |
| Vervolg op | ronde 2 hierboven; de 13 punten "handmatig te controleren" |
| Git en VPS | niets gecommit, niets gepusht, geen uitrol, geen echte sync |

## Correcties op ronde 2

1. **De lijst "handmatig te controleren" is grotendeels vervallen.** Twaalf van de dertien punten meet `--phase visueel` nu in een headless browser; alleen de echte iPhone blijft over (zie onder). Alle metingen slaagden bij de eerste run op de code van ronde 2, dus ronde 2 bleek in orde; er is niets aan de app veranderd, behalve één testbaarheidsaanpassing in het B7-script (de startvoorwaarde staat nu als `data-running` op het statuselement in plaats van in de scripttekst; gedrag gelijk).
2. **B7, het vermoeden "handmatige syncs" is aangescherpt.** Ronde 2 hield het op handmatige syncs met lange kopieertijd. Nu vastgesteld: het ronde pijltjesicoon in de kopbalk is een sync-trigger op elke pagina (zie hieronder). Bewijs voor 09:40 is er niet meer, omdat het logboek daarna is gereset.
3. **Screenshots op volledige paginahoogte tonen de vaste onderbalk en de kop halverwege de afbeelding.** Dat is een eigenschap van `full_page`-schermafbeeldingen met `position: fixed`-elementen, geen fout in de app; de metingen gebruiken de echte posities in de viewport.

## Uitkomst sync-trigger

| # | Trigger | Waar | Voorwaarde |
|---|---|---|---|
| 1 | Ronde pijltjesicoon in de kopbalk (naast maan en bel): formulier `POST /bridge-sync`, daarna terug naar de pagina waar je was | `templates/base.html:24`, `id="sync-btn"`, titel "Synchroniseer naar Bridge" | lokaal, op elke pagina, zodra `BRIDGE_HOST` en de ssh-sleutel bestaan |
| 2 | Knop *Nu synchroniseren* op het profiel, zelfde route | `templates/profile.html:178` | idem |
| 3 | `auto_sync_after_change()` na uploaden, verwijderen (twee plekken), map maken, verplaatsen, deellink maken, deellink intrekken | `app.py` 1262–1696 | alleen bij `BRIDGE_AUTO_SYNC=true`; op de pc false |
| 4 | Commandoregel `python sync_bridge.py` | `sync_bridge.py:160` | handmatig |

Geen JavaScript-trigger; `app.js` bevat niets over sync. Elke aanroep van de route logt `bridge_sync_triggered` in `audit_log.json`, maar dat bestand is met `seed_demo.py --reset` na de repetitie leeggemaakt: de oudste regel is van 15:34 vandaag (één sync-trigger, Wims eigen test). De syncs van 09:40:06, 10:06:22 en 11:06:17 zijn dus niet meer te herleiden. Wat vaststaat: auto-sync kan het niet geweest zijn, en trigger 1 doet precies wat werd vermoed, staat op elke pagina en brengt je na de klik terug op dezelfde pagina, zodat een klik niet opvalt. Onderbouwd vermoeden, geen bewijs. Bij de volgende repetitie geeft *Logboek* uitsluitsel. Niets aan de triggers veranderd.

## De dertien punten: geautomatiseerd of handmatig

| # | Punt | Status | Meting in `--phase visueel` |
|---|---|---|---|
| 1 | Intentielijst en -detail: badge in de kaartkop, geen schuifbalk | geautomatiseerd | per badge omtrek binnen de container (tabel hieronder); `scrollWidth ≤ clientWidth`; geen zichtbaar element met bovenrand < 0; telling ≥ minimum |
| 2 | Verzoekenlijst en -detail, ook de groepslabels | geautomatiseerd | idem; plus geen twee badges op precies dezelfde plek (gestapeld) |
| 3 | "(toestemming ingetrokken op …)" achter de naam | geautomatiseerd | badge binnen de kaart *Geaccepteerd door* (`.card`), minimum 2 badges op die pagina |
| 4 | Respons- en statuspagina wederpartij | geautomatiseerd | badge binnen `.card`; op de ingetrokken responspagina bewust 0 badges, alleen de algemene regels |
| 5 | iPhone: niet over de statusbalk, geen zijwaarts slepen | deels | 390×844 in WebKit: geen element boven de bovenrand, geen schuifbalk. **De echte iOS-statusbalk en safe-area blijven handmatig** |
| 6 | Lange titel plus badge op 380 px | geautomatiseerd | testdata met organisatienaam van 91 tekens en persoonsnaam van 41 tekens; op 390 px op consentdetail en verzoekdetail: badge binnen de kaart, geen schuifbalk |
| 7 | Tellertje op de bel | geautomatiseerd | met één ongelezen melding: omtrek van `.bell-link .badge` snijdt de omtrek van het belicoon; faalt als de badge ontbreekt |
| 8 | Teller bij *Inkomende verzoeken* | geautomatiseerd | met één nieuw generiek verzoek: `.badge-nieuw` binnen `a.btn`, minimum 1 |
| 9 | Syncstatus ververst zichzelf | geautomatiseerd | `/profile` en `/bridge-sync/status` via Playwright-routing (eerst "bezig", dan "klaar" met tijdstip); verwacht zonder herladen "Gesynchroniseerd" en *Laatste sync* 21-09-2026 12:34; geen echte sync |
| 10 | Bevestigingspagina na acceptatie | geautomatiseerd | formulier in de browser ingevuld en verstuurd; tabtitel "Voorwaarden geaccepteerd - MySolido", geen navigatie-elementen, geen schuifbalk |
| 11 | Bridge-profiel op de telefoon | geautomatiseerd | bridge-modus, ingelogd, 390 px: `#btn-consent` zichtbaar, `#btn-requests` afwezig, geen "Pod: " in de hoofdinhoud |
| 12 | Consentrecord | geautomatiseerd | badge in de kop; geen `form[action$="/delete"]`, wel `#consent-agreement-note`; **tegenproef:** handmatige toestemming zonder Agreement heeft precies één zichtbare knop *Verwijderen* en geen uitlegzin |
| 13 | `/verzoeken` op de telefoon | geautomatiseerd | bridge-modus, ingelogd, 390 px: status 403, "Geen toegang", `nav.header-nav` aanwezig |

Elke meting telt eerst wat hij vindt en faalt bij nul waar iets verwacht wordt; per pagina staat het aantal badges en het aantal zichtbare elementen in de testregel.

### Welke container de omtrek bepaalt

| Pagina | Badge-selector | Container (`closest`) | Minimum badges |
|---|---|---|---|
| intentielijst `/intenties` | `main .badge` | `.consent-item` (het lijstitem) | 2 |
| intentiedetail (actief; met ingetrokken toestemming) | `main .badge` | `.card` (kopkaart resp. kaart *Geaccepteerd door*) | 1; 2 |
| verzoekenlijst `/verzoeken` | `main .badge` | `.consent-item` | 2 |
| verzoekdetail (lange naam; ingetrokken) | `main .badge` | `.card` (kopkaart, kaart *Acceptatie en Agreement*, gegevenskaarten) | 3; 3 (gemeten 6 en 7) |
| responspagina (geaccepteerd; ingetrokken) | `main .badge` | `.card` | 1; 0 |
| statuspagina (geaccepteerd; ingetrokken) | `main .badge` | `.card` | 1; 1 |
| consentlijst `/consent` | `main .consent-status-badge` | `.consent-item` | 3 lokaal, 2 Bridge (gemeten 3 en 4) |
| consentdetail (lange titel; ingetrokken; handmatig) | `main .consent-status-badge` | `.consent-detail-card` | 1 |
| profiel lokaal | `main .badge-nieuw` | `a.btn` (de knop *Inkomende verzoeken*) | 1 |
| profiel Bridge | `main .badge` | `a.btn` | 0 |
| dashboard, acceptatieformulier, verzoekformulier | `main .badge` | `.card` | 0 (alleen de algemene regels); bel apart |
| bel (dashboard lokaal) | `.bell-link .badge` | overlap met `.bell-link svg`, geen omtrekregel | 1 |

`main` sluit de bel uit van de omtrekregel: die badge staat met opzet 4 px boven en 6 px rechts van zijn link.

## Tijdstempels

| Tijd | Handeling |
|---|---|
| 18:14 | Controlepunt (d12adba, 16 gewijzigde bestanden). Sync-triggers gezocht in app.py, templates, app.js, scripts en .bat-bestanden; logboek gelezen (alleen lezen). |
| 18:16 | Playwright gevonden (1.53.0, Chromium aanwezig, WebKit niet). Tabel van de 13 punten aan Wim voorgelegd; **gestopt**. |
| 18:2x | Akkoord van Wim met drie aanvullingen (telling ≥ 1, container per pagina expliciet, tegenproef punt 12). |
| 18:21–18:23 | `python -m playwright install webkit` (56,8 MB, WebKit 18.5 in `%LOCALAPPDATA%\ms-playwright\webkit-2182`). |
| 18:27 | `phase_visual` in `scripts/regressietest.py` (`--phase visueel`), `data-running` in profile.html, `requirements-dev.txt`, `.gitignore` (`regressietest-schermen/`), `scripts/regressietest.md`. Vers proces op 5010 gestart (`REQUEST_RATE_LIMIT=100`). |
| 18:27:24–18:28:02 | `--phase visueel`: **89 geslaagd, 0 gefaald, 0 niet automatiseerbaar, 2 info (37 s)**; 68 schermafbeeldingen. |
| 18:28–18:29 | **Tegenproef 1:** bel-regel tijdelijk weer generiek (`.badge`), `position: static` laten staan: 87 geslaagd, **2 gefaald** (bel-teller overlapt het icoon niet, desktop en iPhone). CSS hersteld, byte-gelijk gecontroleerd. |
| 18:29–18:30 | **Tegenproef 2:** de oorspronkelijke botsing volledig terug (generieke regel én zonder `position: static`): 54 geslaagd, **35 gefaald** (schuifbalk 1372 > 1366, badges op -4 px boven de pagina, badges buiten hun container, op vrijwel elke pagina en beide viewports). CSS hersteld, byte-gelijk; schermafbeeldingen van de goede run teruggezet. |
| 18:30:13–18:30:27 | `--phase demo`: **173 geslaagd, 0 gefaald, 0 niet automatiseerbaar, 4 info (14 s)**. Geen testrecords achtergebleven; `notifications.json` teruggezet (leeg, zoals vooraf). Proces op 5010 gestopt. |
| 18:3x | Steekproef van de schermafbeeldingen (consentdetail lange titel op iPhone, intentiedetail met ingetrokken toestemming op desktop): badges in de kaart, toevoeging achter de naam, teller op de bel. Deze sectie. |

## Telling

| Fase | Uitkomst |
|---|---|
| `--phase visueel` (Chromium 1366×768 + WebKit iPhone 390×844, lokaal en Bridge) | 89 geslaagd, 0 gefaald, 2 info |
| `--phase demo` (13a–13h) | 173 geslaagd, 0 gefaald, 4 info |
| tegenproef 1 (bel-regel generiek) | 2 gefaald, precies de bel-metingen |
| tegenproef 2 (oorspronkelijke botsing) | 35 gefaald |

De tegenproeven zijn niet in de test opgenomen (ze veranderen de CSS); ze staan hier als bewijs dat de fase een volgende botsing vangt.

## Handmatig blijft

| Pagina | Verwachting |
|---|---|
| Echte iPhone, Safari op iOS, na uitrol op de Bridge: intentielijst en -detail, verzoek-/responspagina, consentrecord, profiel | geen badge over de iOS-statusbalk of in de safe-area; de pagina laat zich niet zijwaarts slepen; knop *Toestemmingen* op het profiel. De emulatie meet dezelfde pagina's in WebKit op Windows, maar niet de statusbalk en de safe-area van het toestel |

## Gewijzigde en nieuwe bestanden (bijgewerkt, voor `git add`)

Ronde 2 (16 bestanden, zie de lijst hierboven) plus ronde 2b:

| Bestand | Status | Wat |
|---|---|---|
| `scripts/regressietest.py` | M (ronde 2 en 2b) | `_start_bridge_process()`, `_stop_process()`, `VISUAL_MEASURE_JS`, `VISUAL_BELL_JS`, `_visual_pages()`, `phase_visual()`; `_make_accepted_case()` met `name`/`organization`; `--phase visueel` |
| `templates/profile.html` | M (ronde 2 en 2b) | `data-running` op `#sync-status`, startvoorwaarde van het B7-script |
| `scripts/regressietest.md` | M | sectie "visuele test (Playwright)" met installatie-instructie; rij "Echte iPhone" bij handmatig |
| `.gitignore` | M | `regressietest-schermen/` |
| `requirements-dev.txt` | nieuw | `playwright>=1.53`, alleen ontwikkeling |
| `regressietest-schermen/` | nieuw, niet in git | 68 schermafbeeldingen `<modus>_<viewport>_<pagina>.png` van de laatste goede run |

Totaal: 18 gewijzigde bestanden, 2 nieuwe bestanden in git (`requirements-dev.txt` en dit verslag), 1 nieuwe map buiten git.

## Buiten dit verslag (ronde 2b)

- **WebKit ≠ Safari op iOS.** Playwright's WebKit op Windows deelt de layout-engine, niet de iOS-schil: statusbalk, safe-area, adresbalk die meeschuift en de scrollfysica van het toestel meet hij niet. Daarom blijft de echte iPhone op de lijst.
- **`--phase visueel` staat niet in `--phase all` en niet in `demo`.** Bewust apart, omdat hij Playwright nodig heeft en 37 s kost; zonder Playwright slaat hij zichzelf over met één `SKIP`-regel. Wil je hem standaard in `demo`, dan is dat één regel in `main()`.
- **De fase verandert tijdelijk de testdata op dezelfde Pod** (twee acceptaties, één intrekking, één handmatige toestemming, één generiek verzoek, één melding) en ruimt alles op; `notifications.json` wordt byte-gelijk teruggezet. Niet tegelijk draaien met `--phase demo` (beide gebruiken poort 5001).
- **Jouw Flask op 5000** draait nog de code van d12adba; niet aangeraakt, alleen gelezen in ronde 2.
- **Sync-triggers ongewijzigd**, ook het icoon in de kopbalk. Of dat icoon op elke pagina moet blijven, is een ontwerpkeuze voor jou; het logboek registreert elke klik.
- **Niet gecommit, niet gepusht, VPS niet aangeraakt.**
