# MySolido — verslag Bridge-authenticatie en openbare pagina's, 21-09-2026

| | |
|---|---|
| Datum | 21-09-2026, 11:58–12:08 |
| Uitgangshash | df34993 op branch `myterms-demo` (werkboom schoon voor .py en .html; alleen ongetrackte .md-bestanden) |
| Omgeving | pc Wim, repo `C:\Users\Wim\mysolido`, Python 3.13, CSS 7.2.0 op poort 3000, Pod `http://127.0.0.1:3000/mysolido/`; Claude Code (desktopapp) |
| Vervolg op | `docs/mysolido_verslag_generale-repetitie-myterms_21-09-2026.md` en de Cowork-routetabel van vanochtend (lokaal Bridge-proces op 5001, 10:32–10:35) |
| Van/aan | Claude Code → Wim; Wim leest de diff en commit zelf |
| Git | niets gecommit, niets gepusht; VPS niet aangeraakt |

## Correcties bovenaan

1. **Het vermoede lek reproduceert niet.** `/profile` en `/profiel-data` zonder inlog op de Bridge: lokaal dicht (redirect naar `/bridge-login`), en op de VPS gaf `curl` zonder cookies op `/profiel-data`, `/profile` en `/` drie keer 302 naar `/bridge-login`. Vermoedelijke lezing: de sessie kwam uit een ander Safari-privétabblad dat nog een geldige Bridge-cookie had. De eerdere bevinding blijft in het repetitieverslag staan; deze correctie gaat erboven. Vandaag opnieuw bevestigd: de routetabel-lus (13h, 12:07) vindt 0 routes buiten de openbare lijst die zonder sessie antwoorden.
2. **De maatstaf was verkeerd geformuleerd.** Niet "niet ingelogd op de Bridge" maar "pagina voor de wederpartij": de acceptatiepagina en de responspagina toonden lokaal én op de Bridge de kluisnavigatie, en lokaal werkten die knoppen echt. Dat is vandaag opgelost met een eigen kale basistemplate, onafhankelijk van modus of sessie.
3. **Wel echt mis (bevestigd en opgelost):** `/verzoek`, `/verzoek/intentie/<id>`, `/verzoek/status/<token>` en `/verzoek/response/<token>` toonden de complete kluisnavigatie, het Bridge-kopje, de eigenaarsbanner en de uitlogknop uit `base.html`. Zie stap 2.
4. **Dode prefix `/share-password/`** in de openbare controle is weg; er bestond geen route mee. De test bewaakt nu dat die prefix dichtvalt.

## Wat er is gedaan (met tijdstempels)

| Tijd | Handeling |
|---|---|
| 11:58 | Controlepunt: `git rev-parse --short HEAD` = df34993, branch `myterms-demo`, geen gewijzigde .py/.html. Repo leesbaar. |
| 11:58–12:01 | Code gelezen: `check_bridge_auth` (één `before_request`, standaard dicht, lijst per endpointnaam), `base.html`, de vijf `/verzoek`-templates, onderdeel 13h van de regressietest. Geverifieerd dat `app.py` importeerbaar is zonder server te starten: 72 routes in `app.url_map`. |
| 12:02–12:03 | **Stap 1, `app.py`:** constante `BRIDGE_PUBLIC_ENDPOINTS` bovenin (regels 82–97), per regel de reden; helper `bridge_endpoint_is_public()` met de voorwaarde "status actief" voor de Offer-JSON; `check_bridge_auth()` gebruikt alleen nog die constante. De prefixcontroles op `/share/` en `/share-password/` zijn weg (`/share/<token>` is als endpointnaam `view_shared_file` al openbaar). Docstring van `intentie_policy_file` aangepast. |
| 12:03 | **Stap 2, templates:** nieuw `templates/base_public.html` (kale opmaak: kop met alleen naam en themaknop, flashes, inhoud, versieregel, spinner, `app.js`; geen kluisnavigatie, geen onderbalk, geen Bridge-kopje, geen eigenaarsbanner, geen uitlog-, melding- of syncknop). De templates `verzoek_formulier`, `verzoek_intentie`, `verzoek_status`, `verzoek_response` én `verzoek_bevestiging` erven nu van `base_public.html`. De bevestigingspagina is meegenomen omdat POST `/verzoek` en POST `/verzoek/intentie/<id>` hem tonen; hij is dus ook een pagina voor de wederpartij. |
| 12:06 | **Stap 3, regressietest 13h** (`scripts/regressietest.py`, `phase_bridge_local`): lus over `app.url_map`, Offer-JSON in beide standen, navigatiecontrole op de vier wederpartij-pagina's (lokaal, Bridge zonder login, Bridge met eigenaarssessie), controle dat de kluispagina mét sessie de navigatie behoudt, en de dode prefix. Details hieronder. |
| 12:06 | `docs/css-koppelvlakken.md` §10: regelverwijzing en omschrijving van de Bridge-rij bijgewerkt (`app.py:82-97`, `app.py:783-833`). |
| 12:07:07 | Vers proces gestart: `MYSOLIDO_PORT=5010 REQUEST_RATE_LIMIT=100 python app.py` (poort 5010, zie "Buiten dit verslag" waarom niet 5000). Bereikbaar na 1 s. |
| 12:07:18–12:07:32 | **Stap 4:** `python scripts/regressietest.py --phase demo --flask-base http://127.0.0.1:5010`. Uitkomst: **151 geslaagd, 0 gefaald, 0 niet automatiseerbaar, 4 info (13 s)**. |
| 12:08 | Browsercontrole van `/verzoek` op 5010: alleen kop "MySolido" met themaknop, formulier, geen navigatie. Geen achtergebleven testbestanden in de Pod (geen `Regressietest`-records in intenties, verzoeken of toestemmingen). Proces op 5010 gestopt; poort 5010 vrij. |

## Routetabel vóór en na

Bron: `app.url_map` van df34993 (72 routes, ongewijzigd in aantal). "Vóór" is de controle in df34993, "na" de controle met `BRIDGE_PUBLIC_ENDPOINTS`. Alles gemeten zonder sessie tegen een lokaal `--bridge`-proces op 5001 (regressietest 13h, 12:07).

### Openbaar (10 endpointnamen) — met per regel de reden zoals die nu in `app.py` staat

| Endpointnaam | Route | Vóór | Na | Reden |
|---|---|---|---|---|
| `bridge_login` | GET/POST `/bridge-login` | open | open | het inlogscherm zelf |
| `static` | `/static/<path>` | open | open | css, js en iconen; ook het inlogscherm en de openbare pagina's hebben ze nodig |
| `view_shared_file` | GET/POST `/share/<token>` | open (naam én prefix) | open (alleen naam) | deellink voor een ontvanger; het token en het eigen wachtwoord van de link beschermen de inhoud |
| `verzoek_formulier` | GET `/verzoek` | open | open | vrij verzoekformulier voor een wederpartij |
| `verzoek_submit` | POST `/verzoek` | open | open | indienen van dat verzoek (rate limit per IP) |
| `verzoek_status` | `/verzoek/status/<token>` | open | open | statuspagina van de wederpartij, alleen met het geheime statustoken |
| `verzoek_response` | `/verzoek/response/<token>` | open | open | vrijgegeven gegevens voor de wederpartij, alleen met het geheime statustoken |
| `verzoek_intentie` | GET/POST `/verzoek/intentie/<id>` | open | open | voorwaarden van een intentie lezen; accepteren blokkeert de route zelf op de Bridge |
| `crash_report_receive` | POST `/crash-report` | open | open | anonieme crashmelding van een lokale MySolido, zonder sessie |
| `intentie_policy_file` | GET `/intenties/<id>/policy.jsonld` | dicht | **open alleen bij status actief**; concept, ingetrokken, verlopen en onbekend id: inlog | de Offer machineleesbaar (MyTerms); bevat geen profielwaarden en de openbare voorwaardenpagina toont dezelfde JSON al |

### Weg

| Wat | Vóór | Na |
|---|---|---|
| prefix `/share-password/` | open zonder route (gaf 404 zonder inlogredirect) | dicht (redirect `/bridge-login`); test bewaakt het |
| prefix `/share/` | open via padcontrole naast de endpointnaam | alleen nog via de endpointnaam `view_shared_file` |

### Dicht, vóór én na (62 routes; zonder sessie redirect naar `/bridge-login`)

- Kluis en bestanden: `/`, `/browse/<path>`, `/upload`, `/delete`, `/create-folder`, `/move`, `/search`, `/view/<path>`, `/download/<path>`, `/policy/<path>`
- Delen: `/share` (POST), `/shares`, `/share-link/create`, `/share-link/revoke`, `/revoke`
- Prullenbak, logboek, meldingen: `/trash`, `/trash/restore`, `/trash/delete`, `/audit`, `/notifications`, `/notifications/read`
- Profiel en instellingen: `/profile`, `/profile/bridge-password`, `/profile/css-password`, `/profiel-data` (GET en POST), `/settings`, `/settings/language`, `/settings/watermark`, `/settings/crash-reporting`, `/settings/ai-provider`, `/settings/ocr-provider`, `/settings/export`
- Bridge-beheer: `/bridge-logout`, `/bridge-sync`, `/bridge-sync/status`, `/crash-reports`, `/crash-reports/delete/<f>`
- Beheer en debug: `/debug`, `/init-folders`, `/init-folders-welcome`, `/ai`, `/ai/ask`, `/ai/index`, `/ai/status`
- Toestemmingen: `/consent`, `/consent/new`, `/consent/<id>`, `/consent/<id>/withdraw`, `/consent/<id>/delete`
- Intenties: `/intenties`, `/intenties/nieuw`, `/intenties/<id>`, `/intenties/<id>/policy/create`, `/intenties/<id>/activate`, `/intenties/<id>/withdraw`, `/intenties/<id>/delete`
- Verzoeken (eigenaar): `/verzoeken`, `/verzoeken/<id>`, `/verzoeken/<id>/approve`, `/verzoeken/<id>/reject`, **`/verzoeken/<id>/agreement.jsonld`** (Agreement-JSON: nooit openbaar, conform besluit)

Onbekende paden (endpoint `None`, dus ook `/share-password/...`) vallen in Bridge-modus eveneens dicht.

## Regressietest 13h: wat er is toegevoegd

Onderdeel `phase_bridge_local` start zoals voorheen een tweede proces met `--bridge` op poort 5001 tegen dezelfde Pod. Nieuw:

| Check | Verwachting |
|---|---|
| `app.url_map` en `BRIDGE_PUBLIC_ENDPOINTS` uit `app.py` gelezen | import in een apart proces (`python -c`), geen server; faalt als de import breekt |
| elke naam op de openbare lijst bestaat als endpoint | een dode regel (zoals `/share-password/` vroeger) valt hier door de mand |
| 62 routes buiten de lijst vallen zonder sessie dicht | per route GET (of de eerste andere methode), zonder cookies: 3xx met `Location` naar `/bridge-login`. **Een nieuwe route die niet op de lijst staat en toch antwoordt, wordt hier met methode, pad en status gemeld.** |
| 10 openbare routes antwoorden zonder sessie | geen redirect naar `/bridge-login` (200, 302 naar het formulier, 400 bij lege crashmelding, 404 bij onbekend deeltoken zijn allemaal goed) |
| INFO-regel | 72 routes, 10 openbare namen, met de lijst |
| dode prefix `/share-password/x` valt dicht | redirect naar `/bridge-login` |
| wederpartij-pagina's zonder navigatie-elementen, met versieregel | `/verzoek`, `/verzoek/intentie/<id>`, `/verzoek/status/<token>`, `/verzoek/response/<token>`: status 200, geen van `class="header-nav"`, `class="bottom-nav"`, `bridge-banner`, `/bridge-logout`, `bell-link`, `id="sync-btn"`, `header-subtitle`; wél `id="app-version"`. Drie keer: lokaal, Bridge zonder login, Bridge met eigenaarssessie |
| kluispagina met eigenaarssessie behoudt de navigatie | `/` op de Bridge met sessie: header-nav, bottom-nav en bridge-banner aanwezig (bewaakt dat de kale opmaak niet per ongeluk de kluis raakt) |
| Offer-JSON, actieve intentie, zonder sessie | 200, `application/ld+json`, bevat de policy-uid |
| Offer-JSON, onbekend id, zonder sessie | inlogscherm (geen 404, dus geen lek over het bestaan van id's) |
| Offer-JSON, concept-intentie (via POST `/intenties/nieuw`, niet geactiveerd), zonder sessie | inlogscherm |
| Offer-JSON, concept-intentie, met eigenaarssessie | geen inlogscherm (200 of 404 als er nog geen Offer is) |
| Offer-JSON na intrekken van de intentie (POST `/intenties/<id>/withdraw` op de lokale app), zonder sessie | inlogscherm; met eigenaarssessie 200 ld+json |

De concept-intentie wordt in `finally` opgeruimd, net als de bestaande testketen. De testketen zelf (intentie, verzoek, Agreement, consentrecord) wordt vóór het opruimen ingetrokken; dat verandert niets aan de opschoning.

Waarom deze test op df34993 zou falen (redenering, niet gemeten; de oude stand is niet opnieuw gedraaid): de navigatiecontrole vindt `class="header-nav"` op alle vier de pagina's, en `/share-password/x` gaf zonder inlogredirect een 404.

## Uitkomst regressietest

```
MySolido regressietest 2026-09-21 12:07 -- scenario U, fase demo, CSS http://127.0.0.1:3000 (7.2.0), Flask http://127.0.0.1:5010
Resultaat: 151 geslaagd, 0 gefaald, 0 niet automatiseerbaar, 4 info (13s)
```

Alle acht demofasen (seed, profielvelden, intentie, Offer, acceptatie/Agreement, consentrecord, afronding, Bridge lokaal) geslaagd. De Pod-demostand in `.data/` is niet aangeraakt buiten wat de test zelf aanmaakt en weer opruimt; controle achteraf: geen records met "Regressietest" in intenties, verzoeken of toestemmingen. Volledige uitvoer en JSON staan in de scratchpad van deze sessie (niet in de repo).

## Gewijzigde bestanden (voor `git add`)

| Bestand | Status | Wat |
|---|---|---|
| `app.py` | M | `BRIDGE_PUBLIC_ENDPOINTS` (regels 82–97), `bridge_endpoint_is_public()` en `check_bridge_auth()` (783–808), docstring `intentie_policy_file` |
| `templates/base_public.html` | nieuw | kale openbare basistemplate |
| `templates/verzoek_formulier.html` | M | regel 1: erft van `base_public.html` |
| `templates/verzoek_intentie.html` | M | idem |
| `templates/verzoek_status.html` | M | idem |
| `templates/verzoek_response.html` | M | idem |
| `templates/verzoek_bevestiging.html` | M | idem (bevestiging na POST, ook een wederpartij-pagina) |
| `scripts/regressietest.py` | M | 13h: `NAV_MARKERS`, `ROUTE_SAMPLE_VALUES`, `_app_routes`, `_route_path`, `_to_login`, `_check_route_table`, `_check_public_pages_bare`, `_make_concept_intention`; uitbreiding `phase_bridge_local` |
| `docs/css-koppelvlakken.md` | M | §10, Bridge-rij: regelverwijzingen en omschrijving |
| `docs/mysolido_verslag_bridge-authenticatie_21-09-2026.md` | nieuw | dit verslag |

Niet-aangeraakte, al ongetrackte bestanden uit `git status` (van eerder vandaag): `MySolido_Roadmap_Policylaag_v1.md`, `docs/MySolido_Koersdocument_Modus.md`, `docs/mysolido_verslag_generale-repetitie-myterms_21-09-2026.md`, `prompt_mysolido_bridge_test.md`, `solid-forum-introductiepost-v2.md`, `solid-world-chat-teksten.md`.

Git meldt bij de vijf `verzoek_*.html` "LF will be replaced by CRLF": die bestanden waren al LF in de werkboom; de diff is per bestand één regel.

## Buiten dit verslag

- **Jouw eigen `python app.py` op poort 5000 (PID 13296) draait nog de code van vóór deze wijzigingen.** Er is geen reloader actief (geen `FLASK_DEBUG`), dus die ziet de nieuwe templates en de nieuwe openbare lijst pas na een herstart. Ik heb dat proces bewust laten staan en de test tegen een eigen vers proces op 5010 gedraaid, dat daarna weer is gestopt. Dat wijkt af van de opdracht "vers gestart op 5000"; de test zelf is verder identiek. Wil je de repetitie op 5000 vervolgen: proces stoppen en opnieuw starten.
- **Bevestigingspagina niet automatisch getest.** `verzoek_bevestiging.html` heeft wel de kale opmaak, maar de test rendert hem niet: hem tonen maakt een nieuw verzoekrecord aan. Even handmatig bekijken na een acceptatie lokaal volstaat.
- **VPS niet aangeraakt**, geen uitrol, geen ssh; dat doe jij volgens `docs/mysolido_uitrol-bridge_checklist.md`. Op de VPS geldt na uitrol dezelfde lijst; `--phase bridge` tegen de VPS is niet gedraaid.
- **Niet gecommit, niet gepusht**; jij leest de diff en commit zelf.
- **Bewust niet gedaan, komt in een eigen ronde:** badges op de verkeerde plek, Toestemmingen onbereikbaar op mobiel, einddatum Agreement vs consentrecord, Verwijderen op consentrecords, `_status` in de consent-JSON, auto-sync-vertraging, knop Inkomende verzoeken op de Bridge, hulpteksten, tijden in UTC, tabtitels.
- **Geen ondertitel op de openbare pagina's.** `base.html` toont "Jouw persoonlijke datakluis" of "Bridge (alleen-lezen)"; beide zijn tegen de eigenaar gericht. In plaats van nieuwe tekst te verzinnen is de ondertitel weggelaten. Wil je er een, dan hoort die bij de ronde hulpteksten.
- **Context processor blijft voor alle pagina's draaien** (`inject_globals` telt meldingen en nieuwe verzoeken, ook voor openbare pagina's). Onschuldig en buiten de opdracht; de centrale controle is niet aangeraakt.
- **Geen GitHub-issue of andere publieke tekst** over authenticatie; de repo is openbaar.
