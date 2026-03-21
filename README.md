# 🛡️ MySolido

**Jouw persoonlijke datakluis op je eigen pc.**

MySolido is open source software die een persoonlijke datakluis (Solid Pod) op je eigen computer draait. Geen cloud, geen derde partij, geen abonnement. Gebouwd op het [Solid protocol](https://solidproject.org) — dezelfde W3C-standaard als [Athumi](https://athumi.be) (Vlaanderen) en de [Nederlandse Datakluis](https://jouw.id).

> *"De eerste Pod die geen provider nodig heeft."*

🌐 [mysolido.com](https://mysolido.com) · 📦 [Download](https://github.com/Wim1201/mysolido/releases)

---

## Wat kan MySolido?

- **20 categorieën** — Identiteit, medisch, financieel, juridisch, verzekeringen, en meer
- **Upload via drag & drop** — Bestanden slepen naar je kluis
- **Delen met rechten** — Alleen lezen, schrijven, tijdelijk, intrekbaar (via Solid WAC)
- **Deellinks** — Deel bestanden via een beveiligde link, zonder dat de ontvanger Solid nodig heeft. Optioneel wachtwoord en verloopdatum.
- **Zoeken** — Recursief zoeken over alle mappen
- **Inline preview** — PDF's en afbeeldingen direct in de browser bekijken
- **Prullenbak** — Verwijderde bestanden 30 dagen herstellen
- **Audit logboek** — Wie heeft wanneer wat gedaan
- **Dark mode** — Licht en donker thema
- **Backup** — Exporteer je hele kluis als ZIP
- **Dashboard** — Statistieken: aantal bestanden, opslaggrootte, mappen, actieve deellinks
- **Bridge-modus** — Read-only modus voor altijd-bereikbare kopie op een server (in ontwikkeling)

---

## Installatie

### Vereisten

- [Node.js](https://nodejs.org) v18 of hoger
- [Python](https://python.org) 3.10 of hoger
- Windows 10/11 (Mac/Linux experimenteel)

### Snelle installatie (Windows)

Download de [laatste release](https://github.com/Wim1201/mysolido/releases) en voer `installeer-mysolido.bat` uit. Het script installeert automatisch:

1. Node.js (als niet aanwezig)
2. Python (als niet aanwezig)
3. MySolido broncode
4. Python dependencies
5. Community Solid Server
6. Start de app en opent je browser

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

### Opstarten na installatie

```bash
# Windows: dubbelklik op
start-mysolido.bat

# Stoppen
stop-mysolido.bat
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

## Bridge (in ontwikkeling)

De Bridge is een altijd-bereikbare kopie van je kluis op een Nederlandse server. Je lokale pc blijft de master — de Bridge synchroniseert mee.

**Wat het oplost:**
- Je kluis is bereikbaar op je telefoon
- Deellinks werken via internet (niet alleen localhost)
- Je pc hoeft niet aan te staan
- Automatische backup

Start de Bridge met:
```bash
python app.py --bridge
```

---

## Technologie

| Component | Technologie |
|-----------|------------|
| Pod-opslag | [Community Solid Server](https://github.com/CommunitySolidServer/CommunitySolidServer) v7.1.8 |
| Protocol | [Solid](https://solidproject.org) (W3C-standaard) |
| Frontend | [Flask](https://flask.palletsprojects.com) (Python) |
| Data-formaat | RDF / Linked Data |
| Licentie | GPLv3 |

---

## Veelgestelde vragen

**Is dit niet gewoon een file manager?**
Nee. De data staat in een Solid pod met RDF-metadata. Elke Solid-compatibele app kan met je data werken. Het is interoperabele persoonlijke data-infrastructuur, niet alleen bestandsopslag.

**Waarom niet Nextcloud?**
Nextcloud is een self-hosted cloud — het vervangt Google Drive als server. MySolido is anders: het is een lokale desktop-kluis gebouwd op Solid. De data blijft op je pc, niet op een server. Ze zijn complementair, niet concurrerend.

**Wat als mijn pc crasht?**
Exporteer regelmatig een backup (ZIP) via de instellingen. Met de Bridge-dienst (binnenkort) heb je automatisch een kopie op een tweede locatie.

**Werkt het op Mac/Linux?**
De code is platform-onafhankelijk (Python + Node.js), maar de installer en start-scripts zijn nu Windows-specifiek. Mac/Linux gebruikers kunnen de handmatige installatie volgen.

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
- 💬 Solid Community Forum: [forum.solidproject.org](https://forum.solidproject.org)

---

## Licentie

[GPLv3](LICENSE) — Vrij te gebruiken, aan te passen en te distribueren. Afgeleide werken moeten ook open source zijn.

---

*MySolido — Jouw data. Op jouw pc. Jouw voorwaarden.*
