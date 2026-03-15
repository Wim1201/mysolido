# MySolido

**Jouw data. Op jouw pc. Jouw voorwaarden.**

MySolido is een persoonlijke datakluis die op je eigen computer draait. Geen cloud, geen abonnement, geen derde partij. Gebouwd op het [Solid protocol](https://solidproject.org) — een open W3C-standaard ontwikkeld door Tim Berners-Lee.

🌐 **Website:** [mysolido.com](https://mysolido.com)

---

## Wat is MySolido?

MySolido installeert op je eigen pc en creëert een persoonlijke Solid Pod waar je documenten, medische gegevens, wachtwoorden en foto's veilig opslaat. Jij bepaalt wie erbij mag en hoe lang.

**De eerste Pod die geen provider nodig heeft.**

## Features

- **20 categorieën** — Identiteit, medisch, financieel, juridisch, en meer
- **Upload** — Drag & drop bestanden naar je kluis
- **Delen met rechten** — Alleen lezen, schrijven, tijdelijk, intrekbaar
- **Verloopdatums** — Gedeelde items vervallen automatisch
- **Zoeken** — Doorzoek alle mappen tegelijk (recursief)
- **Inline preview** — Bekijk PDF's en afbeeldingen direct
- **Prullenbak** — Herstel verwijderde bestanden (30 dagen)
- **Notificaties** — Belletje met ongelezen-count
- **Audit logboek** — Wie heeft wanneer wat bekeken
- **Profiel** — Opslagstatistieken en overzicht
- **Dark mode** — Licht en donker thema
- **Backup export** — Alles als ZIP downloaden
- **Responsive** — Werkt op desktop en mobiel

## Screenshots

*Screenshots worden binnenkort toegevoegd.*

## Technologie

| Component | Technologie |
|-----------|-------------|
| Pod-opslag | [Community Solid Server](https://github.com/CommunitySolidServer/CommunitySolidServer) v7.1.8 |
| Interface | Flask (Python) |
| Protocol | [Solid](https://solidproject.org) (W3C-standaard) |
| Data | RDF / Linked Data |
| Opslag | Lokaal op je eigen pc |

MySolido gebruikt dezelfde standaard als [Athumi](https://athumi.be) (Vlaamse overheid), de [Nederlandse Datakluis](https://www.nederlandsedatakluis.nl/) (Jouw.id) en de EU Digital Identity Wallet.

## Installatie

### Vereisten

- Windows 10+ of macOS
- [Node.js](https://nodejs.org) 18+
- [Python](https://python.org) 3.8+

### Stappen

```bash
# 1. Clone de repository
git clone https://github.com/Wim1201/mysolido.git
cd mysolido

# 2. Installeer Python dependencies
pip install -r requirements.txt

# 3. Start de Community Solid Server
npx @solid/community-server -p 3000 -f .data/ -c @css:config/file.json

# 4. Start de Flask app (in een tweede terminal)
python app.py

# 5. Open je browser
# Ga naar http://localhost:5000
```

Bij eerste gebruik verschijnt een welkomstscherm dat je door de setup leidt.

## Projectstructuur

```
mysolido/
├── app.py              # Flask applicatie
├── templates/          # HTML templates (Jinja2)
│   ├── base.html       # Layout met navbar
│   ├── index.html      # Dashboard + browse
│   └── welcome.html    # Welkomstscherm
├── static/
│   └── css/
│       └── style.css   # Styling (light + dark mode)
├── .data/              # Solid pod data (lokaal, niet in git)
├── requirements.txt    # Python dependencies
└── README.md
```

## Privacy

MySolido is gebouwd op het principe dat jouw data van jou is:

- **Geen cloud** — Alles draait lokaal op je pc
- **Geen tracking** — Geen analytics, geen cookies, geen telemetrie
- **Geen registratie** — Download en gebruik, zonder account
- **Geen derde partij** — Jouw data verlaat nooit je computer, tenzij jij dat wilt
- **Open source** — Controleer zelf wat de software doet

## Roadmap

- [ ] Encryptie per map
- [ ] OCR / documenten scannen
- [ ] AI-assistent op je eigen data (lokaal, zonder cloud)
- [ ] ODRL policy engine (juridisch afdwingbaar datagebruik)
- [ ] EUDI Wallet / Jouw.id koppeling
- [ ] API-koppelingen (MijnOverheid, verzekeraars, banken)

## Licentie

[MIT](LICENSE)

## Links

- 🌐 [mysolido.com](https://mysolido.com)
- 🔷 [Solid Protocol](https://solidproject.org)
- 🌐 [W3C Solid Community](https://www.w3.org/community/solid/)

---

*Gebouwd in Nederland* 🇳🇱
