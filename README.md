# MySolido — Jouw persoonlijke datakluis op je eigen pc

MySolido is een webapplicatie waarmee je belangrijke documenten veilig opslaat in je eigen Solid Pod. Geen cloud, geen bedrijf dat meekijkt — jij hebt volledige controle over je data. Ideaal voor iedereen die identiteitsbewijzen, medische dossiers, contracten en andere persoonlijke bestanden veilig wil bewaren.

![MySolido screenshot](static/screenshot.png)

## Features

- 20 voorgedefinieerde mappen (identiteit, medisch, financieel, etc.)
- Bestanden uploaden, downloaden, verplaatsen en verwijderen
- Inline weergave van PDF, afbeeldingen, audio en video
- Zoeken door je hele kluis
- Delen met andere Solid-gebruikers via WebID
- Toegangsbeheer met verloopdatum
- Prullenbak met automatische opschoning (30 dagen)
- Audit logboek van alle acties
- Volledige backup als ZIP-bestand
- Dark mode
- Responsive design (desktop + mobiel)

## Installatie

### Vereisten

- [Node.js](https://nodejs.org/) (v18+)
- [Python](https://www.python.org/) (v3.9+)
- Git

### Stap voor stap

```bash
# 1. Clone de repository
git clone https://github.com/wimdenherder/mysolido.git
cd mysolido

# 2. Installeer Community Solid Server
npm install

# 3. Installeer Python dependencies
pip install -r requirements.txt

# 4. Start de Solid server
npx @solid/community-server -p 3000 -f .data/ -c @css:config/file.json
```

> Laat dit terminalvenster open. Open een nieuw venster voor de volgende stappen.

```bash
# 5. Maak een account aan
#    Ga naar http://localhost:3000 in je browser
#    Klik op "Sign up" en maak een account aan (bijv. gebruikersnaam "wim")
#    Ga naar http://localhost:3000/.account/
#    Maak client credentials aan en kopieer CLIENT_ID en CLIENT_SECRET

# 6. Configureer de omgevingsvariabelen
cp .env.example .env
#    Vul CLIENT_ID en CLIENT_SECRET in het .env bestand

# 7. Start MySolido
python app.py

# 8. Open de app
#    Ga naar http://localhost:5000
```

Bij de eerste keer openen zie je het welkomstscherm. Klik op **"Kluis inrichten"** om de standaardmappen aan te maken.

## Technologie

| Component | Technologie |
|-----------|-------------|
| Protocol | [Solid](https://solidproject.org/) (Linked Data Platform) |
| Pod server | [Community Solid Server](https://github.com/CommunitySolidServer/CommunitySolidServer) v7.1 |
| Backend | Python / Flask |
| Frontend | HTML, CSS, vanilla JavaScript |
| Authenticatie | Client Credentials (OAuth 2.0) |

## Licentie

MIT

## Links

- [mysolido.com](https://mysolido.com)
