# MySolido — Uitrolchecklist Bridge (VPS) voor de MyTerms-demo

| | |
|---|---|
| **Versie** | 20 september 2026; hoort bij branch `myterms-demo` vanaf commit `5bfacf3` (of later, na commit van subtaak 5) |
| **Doel** | De Bridge op `bridge.mysolido.com` draait dezelfde code als de pc, zodat de telefoon intenties met Offer-kaart, Agreements en 27560-consentrecords toont. Lokaal bewezen met de regressietestfase "Bridge-modus lokaal" (13h); deze checklist is voor de VPS zelf |
| **Uitgangspunten** | De VPS is niet aangeraakt tijdens subtaak 2 t/m 5. Inloggegevens, host en sleutel staan in `.env` (`BRIDGE_HOST`, `BRIDGE_SSH_KEY`, `BRIDGE_PATH`) en worden hier niet herhaald. De Bridge draait dezelfde `app.py` met `--bridge` op een kopie van `.data/<pod>/` (zie `ontwikkeling/css-koppelvlakken.md` §10). Doe dit niet vlak voor de demo; plan een uur, inclusief terugdraaien |

Elke stap heeft een **Verwacht** en een **Terug** (hoe je de stap ongedaan maakt). Stop bij de eerste afwijking en draai terug.

---

## 1. Vooraf op de pc

1. **Commit en push** de branch `myterms-demo` (subtaak 5 staat nog ongecommit als je dit leest vóór de commit). Noteer de korte hash: `git rev-parse --short HEAD`. Dit is de **doelhash**.
   - Verwacht: `git status` schoon (op de bekende ongetrackte markdownbestanden na); de branch staat op de remote.
2. **Lokale controle van de code die je gaat uitrollen:** `python scripts/regressietest.py --phase demo` tegen een vers gestarte Flask (`REQUEST_RATE_LIMIT=100 python app.py`). Onderdeel 13h start zelf een tweede proces met `--bridge` op poort 5001.
   - Verwacht: 0 gefaald; in het bijzonder "Bridge lokaal: …" allemaal PASS.
3. **Afhankelijkheden:** bekijk of `requirements.txt` sinds de hash die op de VPS draait is veranderd: `git diff <vps-hash>..<doelhash> -- requirements.txt package.json`. Subtaak 2 t/m 5 hebben géén nieuwe Python-pakketten toegevoegd (`bcrypt`, `requests`, `flask`, `python-dotenv` waren er al); `git`, dat de versieregel gebruikt, is op de VPS aanwezig als de app daar via `git clone` staat. Zonder `git` valt de versieregel terug op `VERSION` uit `app.py` ("1.4.0-myterms").
4. **Nieuwe, optionele `.env`-sleutels:** `MYSOLIDO_PORT` (standaard 5000) en `REQUEST_RATE_LIMIT` (standaard 10). Op de VPS zijn ze niet nodig; de Bridge accepteert niets, dus de limiet speelt daar niet.

## 2. Inloggen en de huidige stand vastleggen

5. **SSH naar de VPS** met de host en sleutel uit `.env` (dezelfde die `sync_bridge.py` gebruikt).
   - Verwacht: shell op de VPS.
6. **App-map en proces vinden:**
   ```
   ps aux | grep -E "app.py|gunicorn|flask" | grep -v grep
   systemctl list-units --type=service | grep -i -E "mysolido|bridge|flask"
   ```
   - Verwacht: één proces `python … app.py --bridge` (of een gunicorn/systemd-variant) en het pad van de app-map (de map met `app.py`, `templates/` en `.data/`).
   - Noteer: het pad, de servicenaam (of dat het een `screen`/`tmux`/`nohup`-proces is) en de gebruiker waaronder het draait.
7. **Huidige code vastleggen** in de app-map:
   ```
   git status --short
   git rev-parse --short HEAD
   git branch --show-current
   ```
   - Verwacht: schone werkboom (geen lokale wijzigingen op de VPS) en de hash die nu draait: de **oude hash**. Schrijf hem op; dat is je terugdraaipunt.
   - Als er wél lokale wijzigingen zijn: stop, en bekijk eerst wat het is (`git diff`). Niet overschrijven zonder te weten wat het was.
8. **Configuratie op de VPS bekijken (niet wijzigen):** `cat .env` op de VPS, alleen om te zien dat `SOLID_POD_URL` naar dezelfde podnaam wijst als op de pc (`mysolido`) en dat `BRIDGE_PASSWORD` is ingesteld. `SHARE_BASE_URL` moet daar `https://bridge.mysolido.com` zijn: die waarde wordt vanaf subtaak 5 gebruikt voor de aanbodlink op de intentiepagina.
   - Verwacht: podnaam gelijk; `SHARE_BASE_URL` gezet. Ontbreekt `SHARE_BASE_URL`, dan toont de aanbodlink op de Bridge het interne adres van de VPS; voeg de sleutel toe vóór de herstart.

## 3. Code bijwerken

9. **Ophalen en uitchecken:**
   ```
   git fetch origin
   git checkout myterms-demo
   git pull --ff-only origin myterms-demo
   git rev-parse --short HEAD
   ```
   - Verwacht: de doelhash uit stap 1. Bij `--ff-only`-weigering: er staat iets lokaals op de VPS (stap 7); niet forceren.
   - Terug: `git checkout <oude hash>` (detached) of `git checkout <oude branch>`; daarna stap 11.
10. **Afhankelijkheden** (alleen als stap 3 een verschil liet zien): `pip install -r requirements.txt` in de virtualenv van de app (zie het pad van de Python in `ps aux`).
    - Verwacht: geen fouten. Terug: niet nodig, pakketten blijven compatibel met de oude code.

## 4. Herstarten en controleren

11. **Service herstarten** zoals hij nu draait: `sudo systemctl restart <servicenaam>` als het een service is; anders het oude proces stoppen (`kill <pid>`) en op dezelfde manier opnieuw starten (`python app.py --bridge`, in dezelfde `screen`/`tmux`, als dezelfde gebruiker, vanuit de app-map).
    - Verwacht: nieuw proces zichtbaar in `ps aux`; in de log (journal of het venster) de regel "=== MySolido Bridge ===" en "Start op http://127.0.0.1:5000  (versie <doelhash>)".
    - Terug: stap 9-terug plus opnieuw herstarten.
12. **Versieregel op de Bridge:** open `https://bridge.mysolido.com` op de pc, log in met het Bridge-wachtwoord, scroll naar de voettekst.
    - Verwacht: "MySolido <doelhash> · Bridge". Staat er de oude hash: het oude proces draait nog (stap 11); staat er "1.4.0-myterms": `git` ontbreekt in de omgeving van de service (geen blokkade, wel noteren).
13. **Leesroutes op de Bridge** (nog met de oude Pod-inhoud; er zijn dus mogelijk geen intenties): `/intenties`, `/consent`, `/profiel-data`, `/verzoek/intentie/00000000-0000-0000-0000-000000000000` (verwacht: pagina "Intentie niet gevonden", geen 500), `/verzoeken` (verwacht 403).
    - Verwacht: geen foutpagina's. Een 500 betekent een template- of importfout: log bekijken, terugdraaien.

## 5. Gegevens synchroniseren en op de telefoon controleren

14. **Op de pc:** schone demostand (`python scripts/seed_demo.py --reset --yes`) of de stand die je wilt tonen; daarna *Profiel → Synchroniseer naar Bridge*. Wacht tot de status "success" zegt.
    - Verwacht: `scp -r` kopieert `.data/mysolido/` inclusief `intenties/`, `verzoeken/` (met `.agreement.jsonld` en `_response.json`), `toestemmingen/` en de dotfile-policies. Let op: bestanden die alleen op de VPS bestaan blijven daar staan (sync overschrijft, wist niet); na een `--reset` op de pc kunnen op de VPS dus oude records blijven. Wil je de Bridge ook schoon, verwijder dan op de VPS de inhoud van die drie mappen in `<BRIDGE_PATH>/mysolido/` vóór de sync.
15. **Op de telefoon:** inloggen op `https://bridge.mysolido.com`; voettekst met doelhash; *Profiel → Mijn intenties*, *Toestemmingen*; bij een gesynchroniseerde testintentie: Offer-kaart, "Geaccepteerd door", consentrecord met 27560-tabel, alle zonder knoppen; `…/policy.jsonld` en `…/agreement.jsonld` openen als JSON.
    - Verwacht: identiek aan wat de lokale testfase 13h controleert.
16. **Aanbodlink op de Bridge:** open een actieve intentie op de telefoon; de aanbodlink begint met `https://bridge.mysolido.com/verzoek/intentie/`. Openen geeft de voorwaarden met de melding dat accepteren via de lokale kluis loopt.

## 6. Terugdraaien (als het moet)

17. Op de VPS in de app-map: `git checkout <oude hash>` (of de oude branch), service herstarten (stap 11), voettekst controleren (oude code heeft géén versieregel: dan staat er niets onderaan, dat is het bewijs dat de oude code draait). De Pod-kopie op de VPS blijft zoals hij is; oude code negeert de nieuwe velden, maar toont `<uuid>.policy.jsonld` en `<uuid>.agreement.jsonld` wél als bestanden in de kluislisting (die verbergregel zit pas in de nieuwe code).

## 7. Vastleggen

18. Noteer in het logboek van de taak: datum, oude hash, doelhash, servicenaam, of `git` beschikbaar was, en de uitkomst van stap 12, 13 en 15. Dat beantwoordt vraag 4 uit het inventarisatieverslag ("welke codeversie draait op de Bridge") voortaan met één blik op de voettekst.
