🇬🇧 [English](README.md) | 🇳🇱 **Nederlands**

# 🛡️ MySolido

**Jouw persoonlijke datakluis op je eigen pc.**

MySolido is open source software die een persoonlijke datakluis (Solid Pod) op je eigen computer draait. Geen cloud, geen derde partij, geen abonnement. Gebouwd op het [Solid protocol](https://solidproject.org) — dezelfde W3C-standaard als [Athumi](https://athumi.be) (Vlaanderen) en de [Nederlandse Datakluis](https://jouw.id).

> *"De eerste Pod die geen provider nodig heeft."*

🌐 [mysolido.com](https://mysolido.com) · 📦 [Download](https://github.com/Wim1201/mysolido/releases)

---

## Wat kan MySolido?

- **25 categorieën** — Identiteit, medisch, financieel, juridisch, verzekeringen, huisdieren, opleiding, reizen, en meer
- **Upload via drag & drop** — Bestanden slepen naar je kluis
- **Delen met rechten** — Alleen lezen, schrijven, tijdelijk, intrekbaar (via Solid WAC)
- **Deellinks** — Deel bestanden via beveiligde token-URL's met optioneel wachtwoord en verloopdatum
- **Zoeken** — Recursief zoeken over alle mappen
- **Inline preview** — PDF's en afbeeldingen direct in de browser bekijken
- **Prullenbak** — Verwijderde bestanden 30 dagen herstellen
- **Audit logboek** — Wie heeft wanneer wat gedaan
- **Dark mode** — Licht en donker thema
- **Backup** — Exporteer je hele kluis als ZIP
- **Dashboard** — Statistieken: aantal bestanden, opslaggrootte, mappen, actieve deellinks
- **Bridge** — Je kluis bereikbaar via internet, op je telefoon, als read-only spiegel
- **ODRL policies** — Machine-leesbare deelregels per map (W3C Recommendation). Bepaal per map wie wat mag: alleen eigenaar, lezen toegestaan, of tijdelijk delen
- **Toestemmingen** — Leg vast wie toegang heeft tot jouw gegevens en waarom, conform ISO/IEC TS 27560:2023 en W3C Data Privacy Vocabulary
- **Watermerken** — Automatisch watermerk op PDF's en afbeeldingen bij deellinks. Origineel blijft onaangeroerd
- **Profielmodule** — Sla gestructureerde persoonlijke gegevens op (woonsituatie, gezin, voertuigen, verzekeringen, werk, gezondheid) als JSON-LD met W3C Data Privacy Vocabulary
- **Intentiemodule** — Maak anonieme intenties aan ("Ik zoek een autoverzekering") gekoppeld aan je profieldata. Basis voor de Intention Economy
- **Consent-verzoeken** — Externe partijen kunnen via de Bridge gegevens opvragen. Jij beoordeelt, keurt goed of wijst af — en kiest precies welke data je deelt
- **Foutmeldingen** — Optionele, anonieme foutrapportage om MySolido te verbeteren. Er worden nooit persoonsgegevens verstuurd
- **macOS ondersteuning** — `.dmg` installer beschikbaar, of handmatige installatie via Terminal

---

## De Intention Economy

MySolido is meer dan een digitale kluis. Het maakt een nieuw model mogelijk voor hoe consumenten omgaan met bedrijven — de **Intention Economy**.

**Hoe het nu werkt (het Google-model):** Je googelt "autoverzekering." Google verkoopt je zoekgedrag aan verzekeraars. Je krijgt advertenties. De verzekeraar betaalt Google. Jij krijgt niks.

**Hoe het werkt met MySolido:** In je kluis staan gestructureerde gegevens — gezinsgrootte, autogegevens, huidige verzekeringen. Als je een nieuwe polis wilt, maak je een intentie aan: "Ik zoek een autoverzekering." MySolido kan dit anoniem delen met de markt. Verzekeraars bieden op jouw intentie — zonder je naam te kennen. Jij kiest het beste aanbod, op jouw voorwaarden.

Dit wordt ook wel het "Omgekeerde Google" genoemd — in plaats van dat bedrijven je data oogsten, beheer jij het zelf en deel je het vrijwillig.

**Wat er vandaag al werkt:**
- **Profielmodule** — Gestructureerde attributen lokaal opgeslagen als JSON-LD
- **Intentiemodule** — Intenties aanmaken, beheren en activeren, gekoppeld aan je profiel
- **Consent-verzoeken** — Externe partijen (bijv. verzekeringsagenten) kunnen via de Bridge gegevens opvragen. Jij keurt goed of wijst af, en kiest precies welke data je deelt

**Wat er komt:**
- AI-assistent — Een lokale LLM die je kluis doorzoekt, documenten samenvat en je herinnert aan verlopende polissen
- Marktplaats — Anoniem matchen van intenties en aanbiedingen

De vragende partij betaalt — niet de consument.

---

## Bridge — Je kluis, overal bereikbaar

MySolido Bridge spiegelt je lokale kluis naar een Nederlandse server. Je pc blijft de master — de Bridge is een read-only kopie.

- **Altijd bereikbaar** — Open je kluis op je telefoon via bridge.mysolido.com
- **Deellinks** — Deel bestanden via een beveiligde URL, ontvangers hoeven geen Solid te hebben
- **Consent-verzoeken** — Externe partijen kunnen via de Bridge gegevens opvragen
- **Backup** — Automatische tweede kopie op een Nederlandse VPS
- **Beveiligd** — HTTPS + wachtwoord-authenticatie, read-only (geen uploads/deletes via internet)

Lokaal is master. De Bridge synchroniseert mee.

🌐 **Live demo:** [bridge.mysolido.com](https://bridge.mysolido.com)

---

## Installatie

### Vereisten

- [Node.js](https://nodejs.org) v18 of hoger
- [Python](https://python.org) 3.10 of hoger
- Windows 10/11 (Mac/Linux experimenteel)

### Snelle installatie (Windows)

Download de [laatste release](https://github.com/Wim1201/mysolido/releases) en voer `MySolido-Setup.exe` uit. De installer regelt alles automatisch.

### Handmatige installatie

```bash
# 1. Clone de repository
git clone https://github.com/Wim1201/mysolido.git
cd mysolido

# 2. Installeer Python dependencies
pip install -r requirements.txt

# 3. Installeer Community Solid Server
npm install @solid/community-server

# 4. Start CSS (terminal 1)
node node_modules/.bin/community-solid-server -p 3000 -f .data/ -c @css:config/file.json -b http://127.0.0.1:3000

# 5. Start MySolido (terminal 2)
python app.py
```

Open [http://localhost:5000](http://localhost:5000) in je browser.

Bij eerste opstart maakt MySolido automatisch een account en pod aan.

### macOS

Download `MySolido-Installer.dmg` van de [Releases](https://github.com/Wim1201/mysolido/releases) pagina.

Of handmatig installeren:

```bash
git clone https://github.com/Wim1201/mysolido.git
cd mysolido
npm install
pip3 install -r requirements.txt
bash start-mysolido.sh
```

> macOS kan een waarschuwing tonen over een onbekende ontwikkelaar. Ga naar Systeeminstellingen → Privacy en beveiliging → "Toch openen".

### Opstarten na installatie

```bash
# Windows: dubbelklik op
start-mysolido.bat

# macOS
bash start-mysolido.sh

# Stoppen
stop-mysolido.bat       # Windows
# macOS: Ctrl+C in terminal
```

---

## Hoe werkt het?

MySolido draait twee componenten op je pc:

1. **Community Solid Server (CSS)** — De pod-opslag op poort 3000. Dit is een open source W3C Solid server die je data beheert.
2. **Flask app** — De gebruikersinterface op poort 5000. Hier upload, bekijk, deel en beheer je je bestanden.

Je data staat in de `.data/` map op je eigen harde schijf. Niets verlaat je computer tenzij jij dat wilt.

```
┌─────────────────┐     ┌──────────────────┐
│  Flask UI :5000  │────→│  CSS Pod :3000   │
│  (jouw browser)  │     │  (.data/ map)    │
└─────────────────┘     └──────────────────┘
        ↑
   Jij werkt hier
```

---

## Voor verzekeringsagenten en tussenpersonen

MySolido biedt een nieuwe manier om klanten te bereiken — met hun toestemming.

1. U opent `bridge.mysolido.com/verzoek` en dient een gegevensverzoek in
2. Uw klant ziet het verzoek in zijn MySolido-kluis
3. De klant kiest precies welke gegevens hij deelt (bijv. voertuiggegevens, huidige polissen)
4. U ontvangt een tijdelijke, beveiligde link naar de goedgekeurde data
5. Elke toestemming wordt geregistreerd conform ISO 27560 — juridisch sterker dan cookiebanners

De gegevens mogen niet worden doorverkocht (afgedwongen via ODRL policy). Watermerken maken elk lek traceerbaar.

**Tarieven:** Per verzoek (€0,50–2) of maandelijks abonnement (€25–50/mnd). De vragende partij betaalt — niet de klant.

---

## Roadmap

### Beschikbaar

* ODRL policy engine — deelregels per map (W3C ODRL 2.2)
* Consent-module — toestemmingen conform ISO/IEC TS 27560:2023
* Watermerken op deellinks — automatisch watermerk op PDF's en afbeeldingen
* macOS installer (.dmg) en Windows installer (.exe)
* Bridge — altijd bereikbaar via bridge.mysolido.com
* Profielmodule — gestructureerde persoonlijke attributen met W3C DPV vocabulaire
* Intentiemodule — anonieme intenties gekoppeld aan profieldata
* Consent-verzoeken — externe partijen kunnen via de Bridge gegevens opvragen
* Anonieme foutmeldingen — opt-in, geen persoonsgegevens

### Gepland

* **AI-assistent** — Een lokale LLM die je kluis doorzoekt, documenten samenvat en je herinnert aan verlopende polissen — zonder cloud
* **Marktplaats** — Anoniem matchen van intenties en aanbiedingen (Intention Economy)
* Encryptie per map
* OCR / documenten scannen
* A4DS/UMA autorisatie (rolgebaseerde toegang)
* EUDI Wallet / Jouw.id koppeling
* API-koppelingen (MijnOverheid, verzekeraars, banken)
* Portable installer (USB-stick, geen installatie nodig)

---

## Technologie

| Component | Technologie |
|-----------|------------|
| Pod-opslag | [Community Solid Server](https://github.com/CommunitySolidServer/CommunitySolidServer) v7.1.9 |
| Protocol | [Solid](https://solidproject.org) (W3C-standaard) |
| Frontend | [Flask](https://flask.palletsprojects.com) (Python) |
| Data-formaat | RDF / Linked Data / JSON-LD |
| Policies | ODRL 2.2 (W3C Recommendation) |
| Consent | W3C Data Privacy Vocabulary v2.3 + ISO/IEC TS 27560:2023 |
| Profieldata | W3C DPV Personal Data Categories + JSON-LD |
| Watermerken | reportlab (PDF) + Pillow (afbeeldingen) |
| Bridge | Nederlandse VPS (mijn.host) + Nginx + Let's Encrypt |
| Licentie | GPLv3 |

---

## Privacy

* Je data staat op je eigen pc — niet in de cloud
* Geen account bij een derde partij nodig
* Geen telemetrie, geen tracking
* **Bridge optioneel** — De Bridge is een betaalde toevoeging. MySolido werkt volledig zonder, 100% offline
* **Foutmeldingen opt-in** — Anonieme foutrapportages worden alleen verstuurd als je dat zelf inschakelt in de instellingen. Er worden geen persoonsgegevens meegestuurd.

---

## Drie lagen bescherming bij delen

| Laag | Hoe |
|------|-----|
| **Technisch** | Watermerken op gedeelde documenten. Traceerbaar als het lekt. Geen downloadknop. |
| **Juridisch** | ODRL policies: machine-leesbare regels. "Alleen lezen, niet doorsturen, geldig tot datum X." Afdwingbaar. |
| **Registratie** | Elke toestemming vastgelegd conform ISO 27560 + W3C DPV. Bewijslast bij de aanvrager. |

Cookiebanners bieden nul bescherming. MySolido biedt drie lagen.

---

## Veelgestelde vragen

**Is dit niet gewoon een file manager?**
Nee. De data staat in een Solid pod met RDF-metadata. Elke Solid-compatibele app kan met je data werken. Het is interoperabele persoonlijke data-infrastructuur, niet alleen bestandsopslag.

**Waarom niet Nextcloud?**
Nextcloud is een self-hosted cloud — het vervangt Google Drive als server. MySolido is anders: het is een lokale desktop-kluis gebouwd op Solid. De data blijft op je pc, niet op een server. Ze zijn complementair, niet concurrerend.

**Wat als mijn pc crasht?**
Exporteer regelmatig een backup (ZIP) via de instellingen. Met de Bridge heb je automatisch een kopie op een tweede locatie.

**Werkt het op Mac/Linux?**
macOS wordt ondersteund met een `.dmg` installer en `start-mysolido.sh` launcher script. Linux-gebruikers kunnen de handmatige installatie volgen (Python + Node.js).

**Kan een partij die mijn gegevens ontvangt deze doorverkopen?**
Nee. De ODRL policy verbiedt distributie. Elke toestemming wordt geregistreerd met een specifiek doel. Doorverkopen is een overtreding van de afspraak en de AVG. Watermerken maken elk lek traceerbaar.

---

## Bijdragen

MySolido is open source onder de GPLv3-licentie. Bijdragen zijn welkom:

1. Fork de repository
2. Maak een feature branch (`git checkout -b feature/mijn-feature`)
3. Commit je wijzigingen (`git commit -m 'Voeg mijn feature toe'`)
4. Push naar de branch (`git push origin feature/mijn-feature`)
5. Open een Pull Request

---

## Links

- 🌐 Website: [mysolido.com](https://mysolido.com)
- 📦 Releases: [GitHub Releases](https://github.com/Wim1201/mysolido/releases)
- 🔷 Solid protocol: [solidproject.org](https://solidproject.org)
- 🌉 Bridge: [bridge.mysolido.com](https://bridge.mysolido.com) (live Bridge)
- 💬 Solid Community Forum: [forum.solidproject.org](https://forum.solidproject.org)

---

## Licentie

[GPLv3](LICENSE) — Vrij te gebruiken, aan te passen en te distribueren. Afgeleide werken moeten ook open source zijn.

---

*MySolido — Jouw data. Op jouw pc. Jouw voorwaarden.*
