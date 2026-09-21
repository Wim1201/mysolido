# MySolido — Demoprotocol MyTerms (variant A: pc handelt, telefoon toont)

| | |
|---|---|
| **Versie** | 20 september 2026, bijgewerkt 21 september 2026 na de generale repetitie (ronde 2: B1, B2, B4-B9 en cosmetiek), bij branch `myterms-demo` (versieregel onderaan elke pagina toont de commit-hash) |
| **Scenario** | Autoverzekering: intentie → Offer → acceptatie door "Verzekeraar X" → Agreement → consentrecord (ISO/IEC TS 27560) → intrekken. Stappen 0 t/m 8 uit `docs/mysolido_verslag_myterms-demo-inventarisatie_19-09-2026.md` §5 |
| **Rollen** | Eigenaar (Wim) in een gewoon browservenster op `http://127.0.0.1:5000`; wederpartij "Verzekeraar X" in een **andere browser** (repetitie 21-09: Edge voor de eigenaar, Chrome Incognito voor de wederpartij werkte goed en voorkomt verwarring); telefoon met `bridge.mysolido.com` als spiegel |
| **Inhoud** | Alleen handelingen en schermen. De spreektekst staat hier niet in |

---

## A. Voorbereiding (tien minuten vóór de demo)

1. **CSS controleren.** Draait de Community Solid Server op `http://127.0.0.1:3000`? Zo niet: `start-mysolido.bat` (start CSS én Flask) en daarna Flask weer stoppen, of alleen CSS starten zoals gewoonlijk.
2. **Flask vers starten.** Stop een eventueel draaiende Flask (`stop-mysolido.bat` of het venster sluiten). Start opnieuw vanuit `C:\Users\Wim\mysolido`:
   ```
   python app.py
   ```
   Waarom vers: de verzoeklimiet (standaard tien acceptaties per uur per IP) telt in het geheugen van het proces. Voor een oefenmiddag: zet vooraf `REQUEST_RATE_LIMIT=50` in `.env`.
3. **Schone startstand.** In een tweede terminal:
   ```
   python scripts/seed_demo.py --reset --yes
   ```
   Verwacht: het script toont eerst wat het verwijdert (alle intenties, verzoeken, Agreements, responses, toestemmingen), maakt het logboek, de prullenbak en het deelregister leeg en zet het demoprofiel opnieuw (35-44, postcodegebied 5611, auto benzine 2019, 5 schadevrije jaren, geen claims). De laatste regel zegt "Schone demostand". Controle: `http://127.0.0.1:5000/intenties` is leeg, `/verzoeken` is leeg, `/consent` is leeg, *Logboek* is leeg.
   **Ook de VPS:** de sync kopieert wel, maar wist niet. Na een eerdere run staan `intenties/`, `verzoeken/` en `toestemmingen/` op de Bridge nog vol; leeg ze daar (zie `docs/mysolido_uitrol-bridge_checklist.md`) vóór de eerste sync, anders toont de telefoon oude records.
4. **Vensters klaarzetten.**
   - Gewoon venster (eigenaar): `http://127.0.0.1:5000/profile` open, tabblad *Mijn gegevens* al eens bekeken.
   - Privévenster (wederpartij): leeg tabblad; de aanbodlink komt via het klembord (stap 4).
   - Telefoon: `https://bridge.mysolido.com` open en ingelogd met het Bridge-wachtwoord (sessie blijft 24 uur geldig). De Bridge moet de nieuwe code draaien: onderaan elke pagina staat "MySolido <hash> · Bridge" met dezelfde hash als op de pc ("· lokaal"). Klopt dat niet, eerst `docs/mysolido_uitrol-bridge_checklist.md` doorlopen.
5. **Eerste sync.** Op de pc: *Profiel → Nu synchroniseren*. De status op het profiel ververst vanzelf van "Bezig…" naar "Gesynchroniseerd" met een nieuw tijdstip (Nederlandse tijd); dat kan enkele minuten duren, herladen is niet nodig. Op de telefoon herladen: lege intenties, lege toestemmingen. De schone stand staat nu op beide.
   **Altijd handmatig synchroniseren.** Auto-sync staat uit (`BRIDGE_AUTO_SYNC=false`) en zou intenties, verzoeken en toestemmingen ook niet meenemen: hij reageert alleen op bestandswijzigingen in de kluis. Sync 1 t/m 4 hieronder dus met de knop, en op de telefoon herladen tot het nieuwe tijdstip er staat.

---

## B. De acht stappen

Per stap: **Pc** (eigenaar), **Privé** (wederpartij), **Telefoon** (Bridge) en wanneer een sync nodig is. Een sync is alleen nodig als je op de telefoon iets nieuws wilt laten zien; zonder sync toont de telefoon de vorige stand.

### Stap 0 — Profiel: de vier velden

- **Pc:** *Profiel → Mijn gegevens.* Laat zien: kaart *Persoonlijk* met leeftijdscategorie 35-44, bij *Woonsituatie* het postcodegebied 5611 naast "Regio / provincie", bij *Voertuigen* auto / benzine / 2019, bij *Verzekeringen* het schadeverleden (5 schadevrije jaren, geen claims). Niets wijzigen.
- **Telefoon:** *Profiel → Mijn gegevens* toont hetzelfde, alleen-lezen: de velden zijn niet te wijzigen (keuzelijsten openen niet) en er is geen *Opslaan*. Geen sync nodig (staat er al door stap A5).

### Stap 1 — Intentie uitspreken

- **Pc:** *Profiel → Mijn intenties → Nieuwe intentie.* Kies categorie **Autoverzekering**: de geldigheidsduur springt op **2 weken** en onder "Welke gegevens wil je delen?" staan precies vier vinkjes aan: Leeftijdscategorie (35-44), Postcodegebied (5611), Voertuigtype (Auto), Schadeverleden. Brandstof en bouwjaar staan uit; wijs dat aan. Omschrijving: exact "Ik zoek een autoverzekering" (de tekst komt letterlijk terug op de pagina's). Onder *Voorwaarden (MyTerms)*: doel **Offerteberekening**, "Doorlevering aan derden niet toegestaan" aangevinkt, **Open aanbod**. Klik *Intentie opslaan (als concept)*.
- **Scherm:** de intentielijst met één regel, badge *Concept*, datum van vandaag als dd-mm-jjjj.

### Stap 2 — Gegevensselectie (is in stap 1 gebeurd; hier tonen)

- **Pc:** open de intentie. Kaart **Vastgelegde gegevens** met "Vastgelegd op <vandaag>; wijzigingen in je profiel daarna staan hier niet in." en vier regels met waarden. Dit is het snapshot: wie wil, past in *Mijn gegevens* de leeftijdscategorie aan en herlaadt de intentie: de vier regels veranderen niet. (Zet het daarna terug, of laat het staan; de intentie is toch al vastgelegd.)

### Stap 3 — Voorwaarden: de ODRL-Offer

- **Pc:** op dezelfde pagina de kaart **Voorwaarden (ODRL-aanbod)**: de zin "Iedereen die deze voorwaarden accepteert mag leeftijdscategorie, postcodegebied, voertuigtype en schadeverleden gebruiken, uitsluitend voor offerteberekening, tot <over twee weken>, en mag ze niet doorleveren." Klap *Bekijk ruwe ODRL policy (JSON-LD)* open: `"@type": "Offer"`, de vier `target`-urn's, de `purpose`- en `dateTime`-constraint, de `prohibition` met `distribute` en `transfer`. De link *Bekijk als bestand (JSON-LD)* opent de Offer als `application/ld+json`.
- **Onderscheid access/usage control:** de map `profiel/` heeft zijn `.acl` (CSS: wie erbij mag) en dit is de policy (Flask: waarvoor het gebruikt mag worden).
- **Sync 1:** *Profiel → Nu synchroniseren* (of het sync-icoon in de kop). Wachten tot de status "Gesynchroniseerd" met het nieuwe tijdstip toont.
- **Telefoon:** *Profiel → Mijn intenties → de intentie.* Zelfde kaarten, geen knoppen (Activeren, Aanbod intrekken en Verwijderen ontbreken). De JSON is uitklapbaar en de bestandslink werkt.

### Stap 4 — Activeren en aanbieden

- **Pc:** klik **Activeren**. Badge wordt *Actief*. In de bovenste kaart verschijnt de regel **Aanbodlink** met de volledige URL en de knop *Kopieer*. Klik *Kopieer* (knop toont kort "Gekopieerd").
- **Privé:** plak de link in de adresbalk van het privévenster (dit is de enige keer dat de adresbalk wordt gebruikt, en alleen om te plakken). Verwacht: pagina **Voorwaarden accepteren: Autoverzekering** met de zin, de uitklapbare JSON, de vier labels zónder waarden ("De waarden worden pas na acceptatie getoond."), het formulier naam / organisatie / e-mail, de zin dat de identiteit niet wordt geverifieerd, en het vinkje "Ik accepteer deze voorwaarden (urn:mysolido:policy:intention:…)". Nog niets invullen.
- **Sync 2** (facultatief): na sync toont de telefoon de intentie als *Actief* met de aanbodlink (op de Bridge is die link `https://bridge.mysolido.com/verzoek/intentie/…`; wie hem daar opent ziet de voorwaarden met de melding dat accepteren via de lokale kluis loopt).

### Stap 5 — Verzekeraar X accepteert de voorwaarden

- **Privé:** naam "Jan Jansen", organisatie exact "Verzekeraar X BV" (wordt letterlijk overgenomen als partijlabel), e-mail bijvoorbeeld `offerte@verzekeraar-x.nl`, vinkje aan, klik **Voorwaarden accepteren**. De invoervelden hebben de gewone MySolido-stijl; de tabtitel na accepteren is "Voorwaarden geaccepteerd".
- **Scherm (privé):** "Voorwaarden geaccepteerd" met de knop *Gegevens bekijken* en de statuslink. Klik *Gegevens bekijken*: de responspagina met badge *Geaccepteerd*, de kaart *Voorwaarden* met de zin nu beginnend met "Verzekeraar X BV mag …" en de Agreement-uid, en de vier waarden. Brandstof en bouwjaar staan er niet. Laat dit tabblad open.
- **Wat er is gebeurd:** bij een open aanbod is de acceptatie het sluitmoment: verzoekrecord, Agreement, response én consentrecord zijn in één keer geschreven. (Bij een gericht aanbod zou hier "wacht op bevestiging" staan en zou de eigenaar in stap 6 bevestigen.)

### Stap 6 — De eigenaar ziet de afspraak en het consentrecord

- **Pc:** *Profiel → Verzoeken*: één regel, badge **Geaccepteerd**, "Jan Jansen — Verzekeraar X BV", de vier labels. Open het: kaart **Acceptatie en Agreement** met de zin, de intentie, de wederpartij (Verzekeraar X BV · Jan Jansen, `urn:mysolido:party:…`), *Geaccepteerd op* (dd-mm-jjjj HH:MM in Nederlandse tijd, met de UTC-waarde uit het record ernaast), de geaccepteerde policy-uid, de sha256-hash van het aanbod, de Agreement-uid met *Bekijk Agreement (JSON-LD)*, de gevraagde gegevens en de gedeelde waarden, geldig tot, de response-link en **Bekijk consentrecord**.
- **Pc:** klik *Bekijk consentrecord* (of *Toestemmingen* in de navigatie): record **Autoverzekering — Verzekeraar X BV**, status *Actief*. In het detail de 27560-tabel: conform ISO/IEC TS 27560:2023, wederpartij met contactpersoon, doel met `dpv:ServiceProvision`, de vier gegevens met waarden en pd-term, geldigheid "geldig tot <einddatum van het aanbod> · de einddatum van het aanbod (…de Agreement heeft geen eigen einddatum)", doorlevering "Niet toegestaan (prohibition in de Agreement)", status `dpv:ConsentGiven`, één gebeurtenis "Toestemming gegeven", rechtsgrond `dpv:ExplicitlyExpressedConsent`, recht `eu-gdpr:A7-3`, jurisdictie `loc:NL`, de koppelingen naar intentie, verzoek en Agreement; aangemaakt/gewijzigd in Nederlandse tijd. Onder de tabel alleen *Intrekken* en de zin dat er een Agreement op rust en het record niet kan worden verwijderd. Onderaan de ruwe JSON, precies zoals het bestand in de Pod staat (geen `_status`).
- **Pc:** terug naar de intentie: kaart **Geaccepteerd door** met "Verzekeraar X BV op <vandaag> · Jan Jansen"; de knop Verwijderen is verdwenen.
- **Sync 3:** *Nu synchroniseren.*
- **Telefoon:** *Profiel → Toestemmingen → het record* (de knop *Toestemmingen* staat op het profiel, ook op de telefoon): dezelfde 27560-tabel, alleen-lezen (geen Intrekken, geen Verwijderen); *Mijn intenties → de intentie*: "Geaccepteerd door …" met de Agreement-uid. Dit is "de kluis in je zak: bewijs van de afspraak".

### Stap 7 — Wat de telefoon kan en niet kan

- **Telefoon:** laat zien dat er nergens een schrijfknop is (banner "Bridge (alleen-lezen)"), dat `/verzoeken` niet bestaat op de Bridge (de knop *Inkomende verzoeken* ontbreekt in *Profiel*; *Toestemmingen* staat er wel), en dat de aanbodlink op de Bridge de voorwaarden toont met de kopzin dat accepteren via de lokale kluis van de eigenaar gebeurt; onder de aanbodlink op het intentiedetail staat dezelfde uitleg. Het interne pod-adres staat niet op dashboard en profiel van de Bridge. De Bridge is een spiegel; er is geen retourkanaal.

### Stap 8 — Intrekken en het effect tonen

- **Pc:** *Toestemmingen → Intrekken* op het record (bevestig). Status wordt *Ingetrokken*; in het detail status `dpv:ConsentWithdrawn` en een tweede gebeurtenis "Toestemming ingetrokken" met het tijdstip (Nederlandse tijd), `Laatst gewijzigd` bijgewerkt. *Verwijderen* is er ook nu niet: het record blijft als bewijs.
- **Privé:** herlaad het tabblad met de gedeelde gegevens: alleen nog "Toestemming ingetrokken op <vandaag>" (ook als tabtitel), de uitleg dat de Agreement als bewijs blijft, en de Agreement-uid. Geen waarden meer. De statuslink toont dezelfde melding.
- **Pc:** *Verzoeken*: badge **Toestemming ingetrokken** in de regel van het verzoek; in het intentiedetail achter "Geaccepteerd door …" de toevoeging "(toestemming ingetrokken op <vandaag>)", direct achter de naam. *Bekijk Agreement (JSON-LD)* toont een ongewijzigde Agreement.
- **Facultatief, ter afsluiting:** op de intentie **Aanbod intrekken** (de bevestiging legt uit dat lopende afspraken blijven). Herlaad de aanbodlink in het privévenster: de voorwaarden zijn nog te lezen, maar zonder formulier en met "niet actief (status: ingetrokken)". Op de intentie verdwijnt de kaart *Acties* (er is niets meer te doen: ingetrokken, met Agreement).
- **Sync 4:** *Nu synchroniseren.*
- **Telefoon:** *Toestemmingen*: het record staat op *Ingetrokken* met beide gebeurtenissen; de intentie toont "(toestemming ingetrokken op …)".

---

## C. Bekende beperkingen die eerlijk benoemd worden

- **Identiteit van de wederpartij is zelfverklaard.** Naam, organisatie en e-mail worden niet geverifieerd; het formulier zegt dat. Bij een gericht aanbod bevestigt de eigenaar handmatig dat de zelfverklaarde partij de benoemde partij is.
- **WebID op 127.0.0.1.** De `assigner` in Offer en Agreement en de betrokkene in het consentrecord zijn `http://127.0.0.1:3000/mysolido/profile/card#me`: de lokale kluis, niet een publiek adres. Bewuste keuze voor de demo ("eerlijk over wat er draait").
- **De Bridge is een spiegel.** Sync gaat één richting (pc → VPS, `scp -r`); de telefoon toont alleen wat na de laatste sync op de pc stond. Accepteren op de Bridge kan niet; een retourkanaal bestaat niet.
- **Geen technische handhaving van de policy.** De Offer en de Agreement leggen vast wat mag; MySolido dwingt alleen de geldigheidstermijn en het intrekken af (responspagina sluit). Dat de verzekeraar de gegevens niet doorlevert, is een contractuele afspraak met bewijs, geen technische garantie.
- **Alleen intentiegebonden toestemmingen krijgen een 27560-record.** Het oude, generieke verzoekformulier en het handmatige toestemmingsformulier bestaan nog, maar horen niet in de demo.
- **Gedeelde waarden staan in het consentrecord en in de response.** Beide liggen in de Pod (`toestemmingen/`, `verzoeken/`) en gaan mee in sync en backup.

---

## D. Als er iets misgaat

| Symptoom | Oorzaak | Handeling |
|---|---|---|
| Acceptatie in het privévenster geeft alleen een rode melding en geen bevestigingspagina | verzoeklimiet bereikt (standaard tien per uur per IP) | Flask herstarten (teller staat in het geheugen); of vooraf `REQUEST_RATE_LIMIT=50` in `.env` |
| Aanbodlink ontbreekt op de intentie | intentie is nog concept, of al ingetrokken | *Activeren*; bij ingetrokken een nieuwe intentie aanmaken |
| Formulier zegt "niet actief (status: …)" | idem | idem |
| Telefoon toont oude stand | geen sync gedaan sinds de laatste handeling, of de sync loopt nog | *Nu synchroniseren* op de pc; de status op het profiel ververst vanzelf en kan enkele minuten op "Bezig…" staan (de hele pod gaat met `scp -r`); daarna herladen op de telefoon |
| Telefoon toont geen Offer-kaart, geen 27560-tabel of geen versieregel | oude code op de VPS | versieregel vergelijken; `docs/mysolido_uitrol-bridge_checklist.md` |
| Telefoon vraagt opnieuw om het Bridge-wachtwoord | sessie verlopen (24 uur) | inloggen; niets verloren |
| "Voor deze intentie zijn nog geen voorwaarden opgesteld." | record zonder Offer (alleen bij oude records) | knop *Voorwaarden opstellen* op de intentiepagina |
| Verwijderen van een intentie of een consentrecord weigert, of de knop ontbreekt | er rust een Agreement op | bedoeld gedrag; toon het als voorbeeld van "afspraken blijven" (intrekken kan wel) |
| Iets staat verkeerd en je wilt opnieuw beginnen | | `python scripts/seed_demo.py --reset --yes`, op de VPS `intenties/`, `verzoeken/` en `toestemmingen/` legen (sync wist niet), daarna *Nu synchroniseren*; profiel en demobestanden blijven, alles uit stap 1-8 is weg |
| Flask start niet: "poort in gebruik" | vorig proces draait nog | `stop-mysolido.bat`, of het proces op poort 5000 beëindigen; controleer met `netstat -ano \| findstr :5000` |
