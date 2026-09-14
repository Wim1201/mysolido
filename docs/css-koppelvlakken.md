# CSS-koppelvlakken van MySolido

Inventaris van alle plekken waar MySolido afhankelijk is van de Community Solid Server (CSS).
Opgesteld op 14 september 2026 tegen de code op branch `main` (commit `2eeb238`), als
voorbereiding op het gelijktrekken van de CSS-versie en een latere migratie naar CSS v8.
Bijgewerkt op dezelfde dag na de upgrade naar CSS 7.2.0; de regels over versiepinning en
startcommando's beschrijven de situatie ná die upgrade.

Regelnummers verwijzen naar de bestanden op dat moment en verschuiven bij latere wijzigingen.

## Klassen

| Klasse | Betekenis | Verwachting bij een CSS-major |
|---|---|---|
| **A** | Standaard Solid Protocol: LDP, WAC, WebID, Solid-OIDC | Blijft stabiel |
| **B** | CSS-configuratie of CLI: vlaggen, configpresets, poort- en URL-aannames, npm-pinning | Kan wijzigen, meestal eenvoudig aan te passen |
| **C** | CSS-intern: bestandsstructuur in `.data/`, accountsysteem, interne endpoints, responsevormen | Kan zonder aankondiging wijzigen; hier zit het migratierisico |

## Samenvatting

MySolido gebruikt CSS op twee manieren:

1. **Via HTTP**, alleen voor accountcreatie, credentials, wachtwoordwijziging en de `/debug`-route.
   De overige HTTP-functies (`container_exists`, `create_container`, `search_pod`,
   `get_storage_stats`, `parse_container_contents`) zijn als `LEGACY` gemarkeerd en worden door
   geen enkele route meer aangeroepen.
2. **Via het bestandssysteem**, voor alles wat de gebruiker ziet: mappen, uploaden, verwijderen,
   verplaatsen, prullenbak, zoeken, statistieken, ACL-bestanden, ODRL-beleid, toestemmingen,
   intenties, verzoeken, deellinks, backup, Bridge-sync en AI-indexering. MySolido leest en
   schrijft daarbij rechtstreeks in `.data/<podnaam>/`, de map die CSS met de
   `FileDataAccessor` beheert. CSS serveert dezelfde bestanden aan externe Solid-apps.

Daardoor is het zwaartepunt van de afhankelijkheid **klasse C**: de on-disk indeling van CSS
(mapnaam per pod, `.acl`- en `.meta`-hulpbestanden, de `$.ext`-naamconventie, dotfiles als
gewone resources) en het CSS-accountsysteem (`/.account/`, `CSS-Account-Token`,
client credentials via `/.oidc/token`).

Telling: 11 items klasse A, 17 items klasse B, 49 items klasse C (77 in totaal).

## 1. Opstarten, CLI en configuratie

| Bestand | Functie | Klasse | Waarom |
|---|---|---|---|
| `start-mysolido.bat:71` | Start CSS met `node node_modules\@solid\community-server\bin\server.js -p 3000 -b http://127.0.0.1:3000 -f .data/ -c @css:config/file.json`; bij ontbrekende `node_modules` eerst `npm install` | B | CLI-vlaggen en de preset `@css:config/file.json` zijn CSS-CLI en kunnen per major van naam of inhoud veranderen; het pad `bin/server.js` is de `bin`-entry van het npm-pakket. |
| `start-mysolido.sh:52-56` | Zelfde `node .../bin/server.js`-commando, na `npm install` | B | Zelfde CLI-aanname; de versie komt uit `package.json`. |
| `README.md:138,141`, `README.nl.md:138,141` | `npm install @solid/community-server@7.2.0 --save-exact` en het `node .../bin/server.js`-startcommando | B | Documenteert dezelfde versie en CLI-vlaggen; `node node_modules/.bin/community-solid-server` werkte op Windows niet omdat dat bestand daar een POSIX-shellshim is. |
| `app.py:4018-4019` | Foutmeldingshint met `npm install` en het `node .../bin/server.js`-commando | B | Toont CLI-vlaggen aan de gebruiker; moet meebewegen met de scripts. |
| `installeer-mysolido.bat:246,258` | `npm install` zonder pakketnaam | B | Installeert de versie uit `package.json`; nooit meer ongepind. |
| `mysolido-installer.iss:255-265` | `npm install` zonder pakketnaam | B | Idem; `package.json` zit in de `[Files]`-sectie van de installer. |
| `mysolido-installer.iss:67-71` | Verwijdert bij deïnstallatie `node`, `python`, `node_modules`, maar laat `.data/` en `.env` staan | C | Bewust behoud van data, maar die data staat in de CSS-interne indeling en moet bij een major worden gemigreerd. |
| `installeer-mysolido.bat:291-309` | Controleert of poort 3000 en 5000 vrij zijn | B | Poortaanname, gekoppeld aan de `-p 3000` vlag. |
| `stop-mysolido.bat:20-26` | Stopt het proces dat op poort 3000 luistert | B | Zelfde poortaanname; geen CSS-API. |
| `start-mysolido.bat:82`, `start-mysolido.sh:62` | Wacht tot `http://127.0.0.1:3000` antwoordt | A | Gewone HTTP GET op de serverroot, werkt bij elke Solid-server. |
| `start-mysolido.bat:115-118` | `if not exist ".data\mysolido"` → roept `/init-folders` aan | C | Neemt aan dat pod `mysolido` als map `.data\mysolido` op schijf staat (FileDataAccessor-indeling, geen subdomein-pods). |
| `.env.example:3-4` | `CSS_BASE_URL=http://localhost:3000`, `SOLID_POD_URL=http://localhost:3000/<your-username>/` | B | De `-b` baseUrl van CSS moet exact overeenkomen; `localhost` en `127.0.0.1` zijn voor CSS verschillende identifiers. |
| `app.py:50-52` | Defaults `CSS_BASE_URL`, `SOLID_POD_URL`, `WEBID` op `http://127.0.0.1:3000` | B | Vaste poort- en host-aanname. |
| `app.py:435` | `auto_setup()` gebruikt hardcoded `css_base = 'http://127.0.0.1:3000'` en negeert `CSS_BASE_URL` | B | Setup werkt alleen als CSS precies op die baseUrl draait. |
| `.github/workflows/build-macos.yml:38,41` | Bundelt `start-mysolido.sh` en `package.json` in de macOS-app | B | Indirect: de macOS-build erft de versiepin en CLI-vlaggen uit die twee bestanden. |
| `package.json:13` | `"@solid/community-server": "7.2.0"` | B | De enige plek waar de CSS-versie staat; alle scripts, installers en README's volgen deze pin. |
| `.gitignore` | `.data/`, `.env`, `.data-backup*/` en `package-lock.json` uitgesloten | B | Context: de CSS-interne data en credentials leven buiten git; de lock wordt lokaal door `npm install` herschreven. |

## 2. Accountcreatie en credentials (`auto_setup`)

| Bestand | Functie | Klasse | Waarom |
|---|---|---|---|
| `app.py:422-431` | Setup overslaan als `.env` `CLIENT_ID` en `CLIENT_SECRET` bevat | C | Die twee waarden verwijzen naar records in `.data/.internal/accounts/`; `.env` en `.data/.internal/` zijn alleen samen geldig. |
| `app.py:442-457` | `GET /.account/` met `Accept: application/json`, leest `controls` | C | Het `/.account/`-endpoint en de `controls`-JSON zijn de CSS v7 account-API, geen Solid-standaard. |
| `app.py:460-482` | `POST controls.account.create` → `authorization`-token | C | Accountaanmaak is CSS-intern; de responsevorm (`authorization`) is CSS-specifiek. |
| `app.py:485-498` | `GET /.account/` met header `Authorization: CSS-Account-Token <token>` | C | Eigen autorisatieschema van CSS. |
| `app.py:501-528` | `POST controls.password.create` (fallbacks `register`, `html.password.register`) met `{email, password}` | C | De sleutels in `controls` zijn al eens gewijzigd, getuige de fallbacks. |
| `app.py:510` | Vast e-mailadres `user@mysolido.local` | C | Wordt de index-sleutel `.data/.internal/accounts/index/password/email/user@mysolido.local$.json`. |
| `app.py:531-550` | `POST controls.account.pod` met `{name: 'mysolido'}` | C | Pod-provisioning via de account-API is CSS-intern. |
| `app.py:552-553` | `pod_url = {css_base}/{pod_name}/`, `webid = {pod_url}profile/card#me` | B | Volgt het standaard pod-template van CSS in pad-modus; bij subdomein-modus of een ander template kloppen beide URL's niet. |
| `app.py:556-585` | `POST controls.account.clientCredentials` met `{name, webId}` → `{id, secret}` | C | Client credentials zijn een CSS-extensie; Solid-OIDC kent dit mechanisme niet. |
| `app.py:591-601` | Schrijft `.env` met `CSS_EMAIL`, `CSS_PASSWORD`, `CLIENT_ID`, `CLIENT_SECRET` | C | Bewaart CSS-accountgegevens in platte tekst; verlies van `.data/.internal/` maakt ze waardeloos. |

## 3. Wachtwoord wijzigen en tonen (Profile-pagina)

| Bestand | Functie | Klasse | Waarom |
|---|---|---|---|
| `app.py:1910-1935` | `POST controls.password.login` met `{email, password, remember}` → `authorization` | C | Inloggen op de CSS-account-API. |
| `app.py:1946-1962` | `POST controls.password.update` met `{oldPassword, newPassword}` | C | Wachtwoordbeheer via CSS-interne endpoint. |
| `app.py:1968-1985` | Herschrijft `CSS_PASSWORD=` in `.env` | C | Houdt `.env` synchroon met het CSS-account. |
| `app.py:1838-1849`, `templates/profile.html:51-83` | Toont WebID, `CSS_EMAIL` en `CSS_PASSWORD` voor login in externe Solid-apps | C | Werkt alleen zolang CSS de ingebouwde e-mail/wachtwoord-IDP op deze manier aanbiedt. |

## 4. Authenticatie en HTTP-toegang tot de Pod

| Bestand | Functie | Klasse | Waarom |
|---|---|---|---|
| `app.py:891-918` | `POST /.oidc/token` met `grant_type=client_credentials&scope=webid` en Basic-auth | C | Het `/.oidc/`-pad en de `client_credentials`-grant zijn CSS-specifiek. |
| `app.py:921-938` | `pod_request()` stuurt `Authorization: Bearer <token>` zonder DPoP | C | Solid-OIDC schrijft DPoP-gebonden tokens voor; CSS geeft een Bearer-token af omdat bij de tokenaanvraag geen DPoP-proof is meegestuurd, gedoogd gedrag dat kan verdwijnen. |
| `app.py:941-944` | `container_exists()`: `GET` met `Accept: text/turtle` | A | Standaard LDP; **ongebruikt** (legacy). |
| `app.py:947-955` | `create_container()`: `PUT` met `Link: <http://www.w3.org/ns/ldp#BasicContainer>; rel="type"` | A | Standaard LDP-containeraanmaak; **ongebruikt** (legacy). |
| `app.py:969-1027` | `parse_container_contents()`: regex op `ldp:contains`, `HEAD` voor `Content-Length` en `Last-Modified` | A | LDP-vocabulaire, maar de regex verwacht de prefix `ldp:` zoals CSS serialiseert; **ongebruikt** (legacy). |
| `app.py:1361-1389` | `search_pod()` over HTTP | A | Bouwt op `parse_container_contents`; **ongebruikt** (legacy). |
| `app.py:1778-1804` | `get_storage_stats()` over HTTP | A | Idem; **ongebruikt** (legacy). |
| `app.py:2209-2221` | `/debug`: `GET SOLID_POD_URL` als Turtle | A | Enige actieve HTTP-leesroute; standaard LDP-containerrepresentatie. |

## 5. WebID

| Bestand | Functie | Klasse | Waarom |
|---|---|---|---|
| `app.py:52-53`, `app.py:553` | WebID `http://127.0.0.1:3000/mysolido/profile/card#me` | B | De locatie `profile/card#me` komt uit het CSS-pod-template; MySolido leest het WebID-document zelf nooit, alleen de URL wordt in ACL's gezet. |
| `.data/mysolido/profile/card$.ttl`, `card.acl` | Door CSS aangemaakt WebID-document met publieke lees-ACL | A | Standaard WebID-profiel; MySolido raakt het niet aan. Het `pim:storage`-triple uit 7.2.0 staat in het sjabloon achter `{{#if linkStorage}}`; MySolido geeft die instelling bij het aanmaken van de Pod niet mee, dus het triple ontbreekt. |

## 6. Bestandsopslag via het bestandssysteem

Dit is de kern van MySolido. Alle onderstaande functies gaan langs CSS heen.

| Bestand | Functie | Klasse | Waarom |
|---|---|---|---|
| `app.py:136-140` | `get_pod_data_path()` → `<projectmap>/.data/<podnaam>` | C | Neemt aan dat CSS met `-f .data/` draait en pod `X` op `.data/X/` bewaart; klopt niet bij subdomein-pods of een andere backend. |
| `app.py:152-162` | `url_to_relative_path()`: knipt `SOLID_POD_URL` van de URL en doet `unquote` | C | Aanname van een één-op-één afbeelding tussen URL-pad en schijfpad, zonder de `$.ext`-conventie of de identifier-normalisatie van CSS. |
| `app.py:165-205` | `pod_write`, `pod_delete`, `pod_mkdir`, `pod_exists` | C | Schrijft buiten CSS om; omzeilt `.meta`-metadata, locking en cache van CSS; content-type volgt uit de extensie die CSS afleidt. |
| `app.py:208-259` | `list_folder_filesystem()`: slaat dotfiles, `.acl` en `.meta` over | C | Hardcodeert de hulpbron-suffixen van de FileDataAccessor. |
| `app.py:262-299` | `search_pod_filesystem()` | C | Zelfde filter op `.acl`/`.meta`. |
| `app.py:302-352` | `get_pod_stats_filesystem()` | C | Zelfde filter, plus `_trash` als eigen systeemmap. |
| `app.py:1106-1110` | `is_pod_empty()` met `SYSTEM_NAMES = {'profile', 'README', '.acl', '_trash'}` | C | Verwacht de bestanden die het CSS-pod-template aanmaakt; op schijf heet het README-bestand `README$.markdown`, dus dit is in stap 3 te controleren. |
| `app.py:1187-1217` | `/upload` → `pod_write` | C | Bestand landt direct op schijf; CSS ziet het bij de volgende request. |
| `app.py:1220-1284` | `/delete`: mappen via `shutil.rmtree`, bestanden naar `_trash/` via `shutil.copy2` en `os.remove` | C | Verwijdert ook `.meta`/`.acl` van CSS niet mee bij losse bestanden; `_trash/` is een gewone container voor CSS. |
| `app.py:1287-1314` | `/create-folder` → `os.makedirs` | C | Maakt een container zonder LDP-request; CSS leidt het containertype af uit de map. |
| `app.py:1317-1357` | `/move` → `shutil.move` | C | Verplaatst zonder bijbehorende `.acl`/`.meta`. |
| `app.py:1408-1446` | `/view/...`, `/download/...` → `send_file` van schijf | C | Leest buiten CSS en dus buiten WAC om. |
| `app.py:1683-1752` | Prullenbak herstellen en definitief verwijderen | C | `shutil.move` en `pod_delete` op de CSS-map. |
| `app.py:2236-2261` | `/init-folders` → `pod_mkdir` voor `DEFAULT_FOLDERS` | C | Maakt twintig containers rechtstreeks op schijf. |
| `app.py:2180-2206` | `/settings/backup`: zip van `.data/<pod>` zonder dotfiles, `.acl` en `.meta` | C | Backup volgt de CSS-indeling; `.policy.jsonld`, `.mysolido/share_links.json` en alle ACL's vallen erbuiten. |
| `app.py:3960`, `ai_service.py:480-503` | AI-indexering met `os.walk` over de pod-map | C | Leest de CSS-map rechtstreeks. |

## 7. WAC / ACL

| Bestand | Functie | Klasse | Waarom |
|---|---|---|---|
| `app.py:1449-1476` | `build_acl_content()`: `acl:Authorization`, `acl:agent`, `acl:agentClass foaf:Agent`, `acl:accessTo`, `acl:default`, `acl:mode` | A | Standaard WAC-vocabulaire in Turtle. |
| `app.py:1479-1493` | `write_acl()`: schrijft `<pad>.acl` op schijf, of verwijdert het als er geen shares zijn | C | WAC schrijft discovery via `Link rel="acl"` voor; de `.acl`-suffix naast het bestand is de FileDataAccessor-conventie van CSS. |
| `app.py:1496-1536`, `app.py:1650-1669` | `/share` en `/revoke` → `write_acl` | C | Bouwt op de bestandsplaatsing hierboven. |
| `.data/mysolido/.acl`, `README.acl` | Door CSS aangemaakte root-ACL's | A | Standaard WAC; MySolido raakt ze niet aan, maar vertrouwt erop dat de root-ACL alleen de eigenaar toegang geeft (zie deellinks). |

## 8. ODRL-beleid, toestemmingen, intenties, verzoeken en profiel

De inhoud van deze bestanden is standaard (ODRL 2.2, DPV, JSON-LD). De opslag is klasse C.

| Bestand | Functie | Klasse | Waarom |
|---|---|---|---|
| `app.py:2276-2282`, `app.py:2423-2434` | `.policy.jsonld` in elke standaardmap | C | Dotfile in de containermap; CSS serveert het als gewone resource `<map>/.policy.jsonld`, MySolido verbergt het in de eigen listing. |
| `app.py:2499-2524`, `app.py:2666-2671` | `toestemmingen/<id>.jsonld` | C | Directe schrijfactie op schijf. |
| `app.py:2926-2940` | `profiel/profiel.jsonld` | C | Idem. |
| `app.py:3109-3132` | `intenties/.policy.jsonld` en `intenties/*.jsonld` | C | Idem. |
| `app.py:3383-3397`, `app.py:3439-3462` | `verzoeken/*.jsonld` en `verzoeken/.policy.jsonld` | C | Idem; `verzoeken` wordt ook door het publieke aanvraagformulier beschreven. |
| `app.py:2332-2386` | `build_policy()`: ODRL `Set` met `permission`/`prohibition` | A | Standaard ODRL 2.2 JSON-LD, onafhankelijk van CSS. |

## 9. Deellinks

| Bestand | Functie | Klasse | Waarom |
|---|---|---|---|
| `share_links.py:8-15` | `.data/<pod>/.mysolido/share_links.json` met tokens en bcrypt-hashes | C | Verborgen map binnen de CSS-pod-map; CSS zou dit bestand als resource `/mysolido/.mysolido/share_links.json` serveren als de geërfde root-ACL dat toestond. |
| `app.py:1548-1577` | `/share-link/create` controleert het bestand op schijf | C | Bouwt op `safe_pod_path`. |
| `app.py:1580-1634` | `/share/<token>` serveert het bestand via Flask, met optionele watermerk | C | CSS speelt geen rol; de link werkt alleen via Flask of de Bridge. |

## 10. Bridge

| Bestand | Functie | Klasse | Waarom |
|---|---|---|---|
| `sync_bridge.py:43-53` | `get_pod_data_path()` → `.data/<podnaam>` relatief aan de werkmap | C | Zelfde indelingsaanname als `app.py`, maar zonder `PROJECT_DIR`. |
| `sync_bridge.py:56-120` | `scp -r` van de hele pod-map naar `BRIDGE_PATH` (`/home/bridge/.data/`) | C | De Bridge draait dezelfde Flask in `--bridge`-modus op een kopie van de CSS-map, zonder CSS en zonder `.internal/`. |
| `app.py:41`, `app.py:764-786` | `BRIDGE_MODE` blokkeert schrijfroutes | B | Context: de Bridge heeft geen CSS-account nodig omdat hij nooit via HTTP naar CSS praat. |

## 11. CSS-interne bestanden die MySolido niet aanraakt maar wel nodig heeft

| Bestand | Functie | Klasse | Waarom |
|---|---|---|---|
| `.data/.internal/accounts/**` | Accountrecords, wachtwoordindex, pod-index, `clientCredentials` | C | `CLIENT_ID`/`CLIENT_SECRET` in `.env` verwijzen hiernaar; zonder deze map faalt `get_access_token()` en `change_css_password()`. |
| `.data/.internal/setup/current-server-version$.json` | Versiemarker van CSS (nu `7.1.9`) | C | CSS voert bij een versiesprong migraties uit (zie `v6-migration$.json`); een v8 zal dit opnieuw doen. |
| `.data/.internal/idp/keys/` | JWKS en cookie-secret van de IDP | C | Tokens uit `/.oidc/token` zijn hiermee ondertekend. |
| `.data/.internal/setup/current-base-url$.json` | Opgeslagen baseUrl | C | Verklaart waarom `localhost` versus `127.0.0.1` niet uitwisselbaar is. |

## Wat feitelijk is getest

De regressietest staat in `scripts/regressietest.py`, met de handmatige checklist en de
werkwijze in `scripts/regressietest.md`. Beide scenario's (U: bestaande Pod, N: verse
installatie) zijn gedraaid op 7.1.9 en op 7.2.0.

- **De roundtrip loopt via de schijf en is in beide richtingen getest.** Wat MySolido op schijf
  zet komt via `GET` op CSS terug met de juiste content-type; wat via `PUT` op CSS binnenkomt
  staat op schijf en verschijnt in de MySolido-listing. Getest met namen met spaties,
  hoofdletters, dubbele extensies, een content-type die niet bij de extensie past, een
  resource zonder extensie en paden met dubbele slashes.
- **Vastgesteld feit: client-credentials-tokens gelden op http als anoniem.** De
  tokenverificatie van CSS eist `https`-URI's voor WebID en issuer. De HTTP-laag van
  MySolido heeft daardoor nooit als eigenaar gewerkt; `/debug` slaagt alleen omdat de
  Pod-root publiek is. Om de LDP-kant van CSS toch te testen maakt het script een submap via
  de eigen deelfunctie van MySolido tijdelijk publiek lees- en schrijfbaar.
- **De account-API is getest via een wegwerp-testaccount** (account, e-mail/wachtwoord, Pod,
  client credentials) en in scenario N via de echte auto-setup.
- **WAC is getest via CSS**: zonder eigen `.acl` 401, na een publieke share 200, schrijven
  geweigerd, na intrekken weer 401, en een share met een specifieke WebID schrijft de
  `acl:agent`-regel. Een submap met eigen `.acl` en een submap met `.policy.jsonld` zijn na
  een herstart en na de upgrade opnieuw gecontroleerd.
- **Vastgesteld feit: het upgradepad 7.1.9 → 7.2.0 is stil.** Alleen
  `.data/.internal/setup/current-server-version$.json` verandert; geen nieuwe bestanden,
  geen gewijzigde `.meta` of accountrecords, geen migratiemeldingen.
- **Deellinks, ODRL-beleid, toestemmingen, consentrequests, backup en restore, de
  Bridge-sync-module en de Bridge read-only modus** zijn allemaal geautomatiseerd getest. De
  scp naar de Bridge-VPS en de positieve WebID-toegang met een token zijn bewust niet
  geautomatiseerd; zie de checklist.

## Bekende tekortkomingen (niet in deze ronde)

Vastgesteld tijdens de regressietest van 14 september 2026 (`scripts/regressietest.py`) op
CSS 7.1.9 en bevestigd op 7.2.0. Bewust niet opgelost in deze ronde, alleen vastgelegd.

| Tekortkoming | Waar | Gevolg |
|---|---|---|
| Backup-export mist dotfiles | `app.py` `export_backup()` | `.policy.jsonld`, alle `.acl`-bestanden en `.mysolido/share_links.json` zitten niet in de zip. Na een restore zijn ODRL-beleid, deelrechten en deellinks weg. |
| Client-credentials-token geldt op http als anoniem | `app.py` `get_access_token()`, `pod_request()` | De tokenverificatie van CSS eist `https`-URI's voor WebID en issuer (CSS-log: "The URI claim could not be verified as secure"). Op `http://127.0.0.1:3000` telt elk token als anoniem, dus **de HTTP-laag van MySolido heeft nooit als eigenaar gewerkt**; `/debug` slaagt alleen omdat de Pod-root publiek is. Dat het token als Bearer zonder DPoP wordt gebruikt is daardoor ondergeschikt: het gaat pas tellen als MySolido ooit via https én via HTTP zou werken. Bestaand gedrag, buiten deze klus. |
| `$.ext`-conventie onbekend | `list_folder_filesystem()`, `url_to_relative_path()` | Een resource die CSS opslaat als `naam$.ext` (content-type past niet bij de extensie, of er is geen extensie) toont MySolido letterlijk als `naam$.ext`; de listing-URL bevat die schijfnaam en komt niet overeen met de CSS-identifier. |
| Welkomstscherm verschijnt nooit (latente bug) | `app.py` `is_pod_empty()` | Vergelijkt met `README`, terwijl CSS `README$.markdown` op schijf zet. Een nieuwe gebruiker ziet na de eerste start een leeg dashboard zonder standaardmappen; bevestigd in scenario N op 7.1.9 en 7.2.0. |
| Automatische mapaanmaak in `start-mysolido.bat` is dode code | `start-mysolido.bat:115` | Controleert `.data\mysolido` pas nadat Flask draait, maar de auto-setup heeft de Pod dan al aangemaakt. `/init-folders` wordt nooit aangeroepen. |
| "Draait al"-controle in `start-mysolido.bat` te grof | `start-mysolido.bat:51` | `findstr "127.0.0.1:5000"` telt ook sockets in TIME_WAIT. Tot ongeveer twee minuten na een stop weigert het script te starten en opent het alleen de browser. |
| `auto_setup()` negeert `CSS_BASE_URL` | `app.py:435` | De eerste setup werkt alleen als CSS precies op `http://127.0.0.1:3000` draait. |
| Twee verschillende trash-id's | `app.py:1261`, `trash.py:27` | De bestandsnaam in `_trash/` en de `trash_id` in `trash.json` komen uit verschillende UUID's; herstellen werkt alleen omdat `trash_url` apart wordt opgeslagen. |

## Uitkomst van de upgrade 7.1.9 → 7.2.0 (14 september 2026)

Getest met `scripts/regressietest.py` in twee scenario's: U (bestaande Pod van 7.1.9) en N
(verse installatie). Resultaten per versie identiek: U 93 geslaagd en 0 gefaald, N 95 geslaagd
en 1 gefaald (het welkomstscherm, zie hierboven), persistentie van ACL en policy na herstart én
na de upgrade 9 van 9, Bridge-modus 7 van 7. De JSON-uitvoer staat buiten de repo naast de
backup van `.data/`.

- **De upgrade zelf** wijzigde in `.data/` alleen `.internal/setup/current-server-version$.json`
  (`7.1.9` → `7.2.0`). Geen nieuwe bestanden, geen gewijzigde `.meta`, geen gewijzigde
  accountrecords, geen migratiemeldingen in de log.
- **Dubbele slashes** worden in 7.2.0 genormaliseerd: `.../ldp//bestand.txt` gaf op 7.1.9 een
  401, op 7.2.0 een 200 en een PUT landt op `.../ldp/bestand.txt`. Verwacht volgens de changelog;
  MySolido maakt zelf nooit dubbele slashes.
- **`pim:storage`** verscheen niet, ook niet in een Pod die 7.2.0 zelf aanmaakte. Het sjabloon
  zet het triple alleen bij `linkStorage`, en MySolido geeft die instelling niet mee.
- **Ongewijzigd**: dubbele slug (tweede POST krijgt een UUID-naam, geen 500), resource zonder
  extensie wordt `naam$.txt`, storage description op `/<pod>/.well-known/solid` geeft 200,
  `/.notifications/` geeft 400, het webhook-kanaal `WebhookChannel2023` geeft 200.
- **Startmethode**: `node node_modules/.bin/community-solid-server` werkt op Windows niet (het
  `.bin`-bestand is daar een POSIX-shellshim). Alle scripts en documentatie gebruiken sinds deze
  ronde `node node_modules/@solid/community-server/bin/server.js`, de `bin`-entry van het pakket.

## Aandachtspunten v8

Afgeleid van de C-items hierboven. CSS v8 bestaat op dit moment alleen als alpha; onderstaande
punten zijn de plekken die bij de migratie als eerste breken en dus als eerste getest moeten
worden, met `scripts/regressietest.py` op een kopie van `.data/`.

1. **On-disk indeling van de bestandsbackend.** Vrijwel alles in MySolido hangt aan `.data/<podnaam>/`,
   de suffixen `.acl` en `.meta`, dotfiles als gewone resources en de `$.ext`-conventie. Verandert
   v8 de standaardbackend, de mapindeling of de hulpbron-suffixen, dan breken `get_pod_data_path()`,
   `url_to_relative_path()`, alle `pod_*`-functies, de listings, backup, `sync_bridge.py`,
   `share_links.py`, de AI-indexering en de `.data\mysolido`-controle in `start-mysolido.bat` tegelijk.
   Pin in v8 expliciet de bestandsbackend in de configuratie en vergelijk de mapstructuur van een
   verse Pod met die van 7.2.0 vóór er code wordt aangepast.
2. **Accountsysteem.** `auto_setup()` en `change_css_password()` gebruiken `/.account/`, de
   `controls`-JSON, `CSS-Account-Token`, `password.create`, `account.pod` en `account.clientCredentials`.
   Deze API is in v7 nieuw ingevoerd en kan in v8 opnieuw wijzigen. De code leest `controls`
   dynamisch en heeft fallbacks voor `password.create`; scenario N van de regressietest is de test.
3. **Koppeling `.env` ↔ `.data/.internal/`.** `CLIENT_ID`, `CLIENT_SECRET` en `CSS_PASSWORD` verwijzen
   naar records in `.data/.internal/accounts/`. Als v8 die opslag migreert of hersleutelt, moeten de
   credentials opnieuw worden aangemaakt. Backup altijd als paar maken.
4. **Migraties en versiemarker.** CSS houdt `.internal/setup/current-server-version$.json` bij en
   voerde bij v6 → v7 een migratie uit. Reken bij v8 opnieuw op een migratie; draai die eerst op een
   kopie en controleer daarna ACL's, policies en deellinks met `--phase persist`.
5. **Client credentials en Bearer.** `/.oidc/token` met `client_credentials` is een CSS-extensie. Omdat
   tokens op http toch als anoniem gelden, is de impact van een wijziging in v8 klein: alleen
   `get_access_token()` en `/debug`. Overweeg de HTTP-laag te verwijderen of, als hij ooit echt nodig
   is, over te stappen op https met DPoP.
6. **WAC versus ACP.** MySolido schrijft WAC-`.acl`-bestanden naast resources en vertrouwt op de
   eigenaar-only root-ACL uit het Pod-sjabloon. Kiest v8 standaard voor ACP of een andere
   ACL-plaatsing, dan stoppen deelrechten stilzwijgend met werken. Controleer de
   autorisatiecomponent in de v8-configuratie en de WAC-tests uit de regressietest.
7. **Pod-sjabloon.** De WebID op `profile/card#me`, `README$.markdown` en de publieke leesregel op de
   Pod-root komen uit het sjabloon. `WEBID`-default, `SYSTEM_NAMES` in `is_pod_empty()` en de
   `/debug`-route hangen eraan.
8. **Identifier-normalisatie.** 7.2.0 normaliseert dubbele slashes; MySolido gaat uit van een
   één-op-één afbeelding tussen URL-pad en schijfpad. Gaat v8 verder normaliseren (hoofdletters,
   Unicode, percent-encoding), dan wijken listing-URL's af van CSS-identifiers. De normalisatiegevallen
   in de regressietest zijn de detectie.
9. **CLI en configuratie.** De vlaggen `-p`, `-b`, `-f`, `-c` en de preset `@css:config/file.json`
   zitten in `start-mysolido.bat`, `start-mysolido.sh`, de README's, de macOS-instructies en de hint
   in `app.py`. Eén wijziging in v8 raakt al die plekken; `package.json` blijft de enige plek voor
   de versie.
10. **`pim:storage`.** Wil MySolido dat externe Solid-apps de Pod via het WebID vinden, dan moet de
    Pod-aanmaak in `auto_setup()` de `linkStorage`-instelling meegeven zodra de account-API dat
    toelaat; nu ontbreekt het triple.
