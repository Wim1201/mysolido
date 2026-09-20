# Regressietest MySolido + Community Solid Server

Checklist om vast te stellen of MySolido correct werkt met een bepaalde CSS-versie. Gebruik
deze lijst vóór en na een CSS-upgrade en vergelijk de uitkomsten.

Het grootste deel is geautomatiseerd in `scripts/regressietest.py`. De onderdelen die daar
niet in zitten staan hieronder als handmatige stappen.

## Uitgangspunten

- Alleen synthetische testdata. Geen echte namen, adressen of telefoonnummers.
- Alle testdata komt in één map in de Pod: `regressietest/`. Die map wordt na afloop
  verwijderd. Daarnaast maakt het script een wegwerp-testaccount met eigen Pod
  (`regressietest-pod`) aan om de account-API te testen; ook die wordt opgeruimd.
- Test nooit tegen de Bridge-VPS. Zet in de test-`.env` `BRIDGE_HOST=` leeg en
  `BRIDGE_AUTO_SYNC=false`, dan kan geen enkele handeling per ongeluk synchroniseren.
- Gebruik overal `127.0.0.1`, niet `localhost`: CSS behandelt die als verschillende
  identifiers.
- Client-credentials-tokens authenticeren niet op een `http://`-server. CSS controleert
  tokens met `@solid/access-token-verifier`, die alleen `https`-URI's als WebID en issuer
  accepteert; de CSS-log meldt dan "The URI claim could not be verified as secure". Het script
  legt dit als `INFO` vast en test de LDP-kant van CSS via de submap `regressietest/ldp/`, die
  het met de deelfunctie van MySolido tijdelijk publiek lees- en schrijfbaar maakt.

## Twee scenario's

- **Scenario U (upgradepad):** bestaande `.env` en `.data/`, gekopieerd uit de productieomgeving.
  Testdata in `regressietest/`, na afloop opgeruimd. Draai `python scripts/regressietest.py --scenario U`.
- **Scenario N (nieuwe installatie):** lege `.data/` en geen `.env`, zodat de auto-setup van Flask
  een verse account en Pod aanmaakt. Dit is de enige manier om te zien wat een gebruiker van de
  installer krijgt. Draai daarna `python scripts/regressietest.py --scenario N`; het script
  controleert dan ook of `.env` is geschreven en of het welkomstscherm verschijnt.

Draai beide scenario's op de huidige CSS-versie (nulmeting) en beide op de nieuwe versie.

## Voorbereiding

1. Maak een backup van `.env` en `.data/` buiten de repo.
2. Controleer dat poort 3000 en 5000 vrij zijn (`netstat -ano | findstr ":3000 "`).
3. Installeer de gepinde CSS-versie: `npm install` (nooit `npm install @solid/community-server`
   zonder versie).
4. Start de stack zoals een gebruiker dat doet: `start-mysolido.bat` (Windows) of
   `bash start-mysolido.sh` (macOS/Linux). Wacht tot beide poorten antwoorden.
5. Controleer welke CSS-versie echt draait: `.data/.internal/setup/current-server-version$.json`.

## Geautomatiseerd (`python scripts/regressietest.py --out resultaat.json`)

| # | Onderdeel | Wat wordt gecontroleerd |
|---|---|---|
| 1 | Server start | CSS antwoordt op 3000, Flask op 5000, versie uit `.data/.internal/setup`, wel/geen welkomstscherm |
| 2 | Accountcreatie | `/.account/` bereikbaar, account aanmaken, e-mail/wachtwoord registreren, `CSS-Account-Token` werkt |
| 3 | Pod aanmaken | Test-Pod via account-API, Pod-map verschijnt als `.data/<podnaam>/`, test-WebID publiek leesbaar |
| 4 | Credentials | Client credentials aanmaken; token via `/.oidc/token` bevat de juiste `webid`-claim (voor `.env` en voor het testaccount); Pod-root publiek leesbaar volgens het CSS-template; Bearer-token op beschermde map (info, zie https-beperking) |
| 5 | WebID | WebID-document publiek leesbaar, bevat `solid:oidcIssuer`; aanwezigheid `pim:storage` (info) |
| 6 | Bestanden | Map en submap aanmaken, uploaden, bekijken, downloaden, zoeken, verplaatsen, prullenbak (verwijderen, herstellen, definitief) |
| 7 | Roundtrip Flask → CSS | Nieuwe map erft de eigenaar-ACL (anoniem 401); submap `ldp/` publiek gemaakt via deelfunctie; upload via Flask is via CSS leesbaar met juiste content-type; Flask-map is een LDP-container |
| 8 | Roundtrip CSS → Flask | PUT via CSS staat op schijf en verschijnt in de MySolido-listing; DELETE via CSS verwijdert van schijf; resource zonder extensie (info) |
| 8a | Identifier-normalisatie | Bestandsnaam met spaties en hoofdletters via Flask, map met spatie via Flask en via CSS (`%20`), dubbele extensies, content-type die niet bij de extensie past (`$.ext`-conventie), hoofdletters, resource zonder extensie, PUT en GET met dubbele slash; per geval wat op schijf staat en wat de listing toont (info) |
| 9 | WAC | Zonder ACL 401; publieke share geeft 200; publiek schrijven geweigerd; intrekken verwijdert `.acl` en geeft weer 401; share met specifieke WebID schrijft `acl:agent`-regel en blijft anoniem 401; positieve toegang met WebID-token niet automatiseerbaar op http |
| 10 | Deellink | Aanmaken met wachtwoord, wachtwoordpagina, fout wachtwoord geweigerd, juist wachtwoord levert bestand, intrekken geeft 404; register niet publiek via CSS |
| 11 | ODRL | Policy als `.policy.jsonld` op de submap, regel correct opgebouwd, teruggelezen in Flask, verborgen in listing; zichtbaarheid via CSS (info) |
| 12 | Toestemming | Record weggeschreven, velden correct, detailpagina, niet publiek via CSS, `.jsonld` door CSS geserveerd als `application/ld+json`, intrekken, verwijderen |
| 13 | Consentrequest | Publiek formulier schrijft verzoek, statustoken, statuspagina, eigenaar ziet verzoek, afwijzen, statuspagina toont afgewezen |
| 13a | Demodata (seed) | `scripts/seed_demo.py` op een Pod zonder `profiel/profiel.jsonld`: exit 0, twintig standaardmappen, demoprofiel met de vier scenariowaarden (35-44, 5611, auto, 5 schadevrije jaren / geen claims), `profiel/.policy.jsonld`, drie voorbeeldbestanden; tweede run zonder `--force` weigert met exit 1 en laat alles staan. Bestond het profiel al, dan alleen de weigering (info voor de rest). De demodata blijft na de run staan |
| 13b | Profielvelden | Opslaan via `/profiel-data` schrijft `pd:AgeRange`, `pd:PostalCode` en `mysolido:claimsHistory` naast de bestaande velden; formulier leest ze terug; ongeldig postcodegebied (geen 4 cijfers) wordt niet opgeslagen, de rest wel; oorspronkelijk profiel wordt teruggezet |
| 13c | Intentie | `/intenties/nieuw` toont attributen per veld plus doel, doorleververbod en aanbodvorm; autoverzekering met vier attributen levert `mysolido:sharedAttributes` met precies die vier urn's, de profielwaarden, label/valueLabel en één `capturedAt`; `purpose` = `urn:mysolido:purpose:quote_calculation`; `noOnwardTransfer` true; `offerMode` open; geen `sharedProfileData`; 2 weken = 14 dagen; detailpagina toont "Vastgelegd op" en blijft gelijk na een profielwijziging (snapshot); gericht aanbod zonder naam geweigerd, met naam opgeslagen als `targetedParty` (met `@id`); oud record met `sharedProfileData` blijft leesbaar; testrecords en policybestanden opgeruimd |
| 13d | Intentiepolicy | Na aanmaken staat `intenties/<uuid>.policy.jsonld` naast het record: `odrl:Offer`, uid `urn:mysolido:policy:intention:<uuid>`, `assigner` = WEBID, één permission `use` met de vier attribuut-urn's in recordvolgorde, constraints `purpose eq` en `dateTime lteq validThrough`, prohibition `distribute`+`transfer` bij doorleververbod en afwezig zonder, assignee alleen bij gericht aanbod met dezelfde `@id` als `targetedParty`; record bevat `mysolido:policy`; detailpagina toont de Nederlandse samenvatting (vier labels, doel, doorleverzin), de ruwe JSON-LD en "Vastgelegd op dd-mm-jjjj"; `GET /intenties/<uuid>/policy.jsonld` geeft `application/ld+json`; intentie zonder attributen geweigerd; "Voorwaarden opstellen" maakt een ontbrekende Offer aan; policybestand niet in listing, zoekresultaten of intentieoverzicht; verwijderen van de intentie neemt de Offer mee; opruimen |
| 13e | Acceptatie en Agreement | Open intentie aanmaken en activeren; `/verzoek/intentie/<uuid>` toont zin, JSON-LD en vier labels zonder waarden; POST zonder vinkje geweigerd; POST met vinkje schrijft verzoek met `intention`, `acceptedPolicy`, `acceptedAt` (hele seconden), `acceptedPolicyHash` (klopt met sha256 van het bestand), `party`, status `geaccepteerd`, `agreement`, `responseLink`, `validUntil` = `validThrough`; `verzoeken/<uuid>.agreement.jsonld` met `@type` Agreement, uid, assigner, assignee op permission én prohibition, regels gelijk aan de Offer, `mysolido:offer`/`request`/`acceptedAt`/`offerHash`; `_response.json` met precies de vier attributen; responspagina toont zin, Agreement-uid en vier waarden, niet brandstof of bouwjaar; statuspagina geaccepteerd; intentie heeft `acceptedBy`, detailpagina "Geaccepteerd door", verwijderen geblokkeerd; eigenaarsdetail met hash en Agreement-link; `GET /verzoeken/<uuid>/agreement.jsonld` ld+json; concept-intentie: voorwaarden zonder formulier, POST geweigerd; gericht aanbod: status `wacht-op-bevestiging` zonder Agreement, na Goedkeuren `geaccepteerd` met assignee = `targetedParty.@id`, tweede goedkeuring geweigerd; `.agreement.jsonld` niet in listing, zoeken of verzoekenoverzicht; opruimen (ook Agreements en responses) |
| 14 | Backup | Zip-export bevat testbestand; dotfiles/ACL's/deellinkregister in zip (info) |
| 15 | Restore | Bestand verwijderd, uit zip teruggezet, via CSS weer leesbaar |
| 16 | HTTP-laag | `/debug` leest de Pod-root via CSS (de root is publiek, dus dit bewijst geen authenticatie) |
| 17 | Probes 7.2.0 | Dubbele slash (GET en PUT), dubbele slug, Link-header, storage description, `/.notifications/`, webhook-kanaal (alles info) |
| 18 | Bridge-sync module | Module vindt de Pod-map en de testmap; `is_configured()` (info) |
| 18a | Persistentie aanmaken | `regressietest/acl-map/` met eigen `.acl` (publiek lezen) en `regressietest/policy-map/` met `.policy.jsonld`; CSS volgt de ACL, policy-map blijft eigenaar-only |
| 19 | Opruimen | Publieke share op submap ingetrokken; testmap weg via Flask en niet meer via CSS; hulpmappen die niet vooraf bestonden weg; test-Pod-map weg. Met `--keep-persist` blijven `acl-map/` en `policy-map/` staan |

Statussen: `PASS`, `FAIL`, `SKIP` (niet automatiseerbaar), `INFO` (gedrag vastgelegd voor
vergelijking, geen oordeel).

## Geautomatiseerd, aparte run: ACL en policy na een herstart of upgrade

1. Draai de volledige run met `--keep-persist`, zodat `regressietest/acl-map/` en
   `regressietest/policy-map/` blijven staan.
2. Stop de servers en start ze opnieuw (of installeer eerst de nieuwe CSS-versie).
3. Draai `python scripts/regressietest.py --phase persist`. Controleert dat de `.acl` en de
   `.policy.jsonld` nog op schijf staan, dat CSS de ACL nog volgt (anoniem 200 op het gedeelde
   bestand, schrijven geweigerd, policy-map en testmap 401) en dat Flask de policy nog leest.
   Zonder `--keep-persist` ruimt deze fase `regressietest/` daarna op.

## Geautomatiseerd, aparte run: demodata, profielvelden en intentie (MyTerms-demo)

`python scripts/regressietest.py --phase demo` draait alleen de onderdelen 13a tot en met 13e
tegen de lopende CSS en Flask, zonder testaccount of testmap. Handig na wijzigingen aan
`PROFILE_ATTRIBUTES`, het profielformulier, het intentieformulier, de intentiepolicy of de
acceptatie. Let op: als de Pod nog
geen `profiel/profiel.jsonld` heeft, vult deze run de Pod met de demodata van
`scripts/seed_demo.py` en laat die staan.

## Geautomatiseerd, aparte run: Bridge read-only modus

De Bridge is dezelfde Flask-app met `--bridge`. Omdat Flask altijd op poort 5000 draait, kan
dit niet tegelijk met de normale modus.

1. Stop de normale Flask (proces op poort 5000). CSS mag blijven draaien.
2. Zet in de test-`.env` een bekend wachtwoord: `BRIDGE_PASSWORD=<plaintext>`. De app hasht
   het bij het opstarten.
3. Start `python app.py --bridge` en wacht tot poort 5000 antwoordt.
4. Draai `python scripts/regressietest.py --phase bridge --bridge-password <plaintext>`.
   Controleert: redirect naar login, fout wachtwoord geweigerd, inloggen, lezen van de
   Pod-map, uploaden geblokkeerd, publiek verzoekformulier zonder login, Pod-inhoud zonder
   login geblokkeerd.
5. Stop de Bridge-Flask.

## Handmatig (niet automatiseerbaar)

| Onderdeel | Stap | Verwacht |
|---|---|---|
| Verse setup | Verwijder `.env` en `.data/` in een wegwerpkopie, start `start-mysolido.bat` | Account en Pod worden aangemaakt, `.env` geschreven, welkomstscherm verschijnt |
| Bridge-sync scp | `POST /bridge-sync` met geldige `BRIDGE_HOST` | Pod-map staat op de VPS; alleen uitvoeren tegen een test-VPS |
| Externe Solid-app | Log met `CSS_EMAIL`/`CSS_PASSWORD` van de Profile-pagina in bij een externe Solid-app | Login slaagt, Pod zichtbaar |
| Wachtwoord wijzigen | Profile-pagina, nieuw CSS-wachtwoord | `.env` bijgewerkt, inloggen met nieuw wachtwoord werkt |
| Watermerk op deellink | Deel een PDF of afbeelding met watermerk aan | Gedownload bestand toont watermerk |
| Browser-UI | Open http://127.0.0.1:5000 en klik door dashboard, map, bestand, deellink | Geen foutpagina's, flash-meldingen kloppen |
| Stoppen | `stop-mysolido.bat` | Beide poorten vrij, geen zombie-processen |

## Rapportage

Leg per onderdeel vast: slaagt / faalt / niet automatiseerbaar, plus de CSS-versie waarmee
getest is. Bewaar de JSON-uitvoer van het script per versie en vergelijk de `INFO`-regels:
daar zitten de gedragsverschillen tussen CSS-versies.
