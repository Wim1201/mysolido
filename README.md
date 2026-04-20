🇬🇧 **English** | 🇳🇱 [Nederlands](README.nl.md)

# 🛡️ MySolido

**Your personal data vault on your own PC.**

MySolido is open source software that runs a personal data vault (Solid Pod) on your own computer. No cloud, no third party, no subscription. Built on the [Solid protocol](https://solidproject.org) — the same W3C standard used by [Athumi](https://athumi.be) (Flanders) and the [Dutch Data Vault](https://jouw.id).

> *"The first Pod that needs no provider."*

🌐 [mysolido.com](https://mysolido.com) · 📦 [Download](https://github.com/Wim1201/mysolido/releases)

---

## What can MySolido do?

- **25 categories** — Identity, medical, financial, legal, insurance, pets, education, travel, and more
- **Drag & drop upload** — Drop files into your vault
- **Sharing with permissions** — Read-only, write, temporary, revocable (via Solid WAC)
- **Share links** — Share files via secure token URLs with optional password and expiry
- **Search** — Recursive search across all folders
- **Inline preview** — View PDFs and images directly in the browser
- **Trash** — Recover deleted files for 30 days
- **Audit log** — Who accessed what and when
- **Dark mode** — Light and dark theme
- **Backup** — Export your entire vault as ZIP
- **Dashboard** — Statistics: file count, storage size, folders, active share links
- **Bridge** — Access your vault from anywhere, on your phone, as a read-only mirror
- **ODRL policies** — Machine-readable sharing rules per folder (W3C Recommendation). Control who can do what: owner only, read allowed, or temporary sharing
- **Consent management** — Record who has access to your data and why, compliant with ISO/IEC TS 27560:2023 and W3C Data Privacy Vocabulary
- **Watermarks** — Automatic watermark on PDFs and images when viewed via share links. The original stays untouched
- **Profile module** — Store structured personal attributes (housing, family, vehicles, insurance, work, health) as JSON-LD with W3C Data Privacy Vocabulary
- **Intention module** — Create anonymous intentions ("I'm looking for car insurance") linked to your profile data. Foundation for the Intention Economy
- **Consent requests** — External parties can request access to your data via the Bridge. You review, approve or reject — and choose exactly which data to share
- **Crash reporting** — Optional, anonymous error reporting to help improve MySolido. No personal data is ever sent
- **AI assistant** — Local RAG pipeline (Ollama + ChromaDB) that searches your documents. Hybrid mode available: local indexing + cloud API for answers. Your files never leave your PC during indexing
- **Bilingual** — Full Dutch/English support, switchable in settings
- **OCR** — Text recognition for scanned documents. Local (Tesseract) or cloud (Mistral OCR, EU)
- **macOS support** — `.dmg` installer available, or manual installation via Terminal

---

## The Intention Economy

MySolido is more than a file vault. It enables a new model for how consumers interact with businesses — the **Intention Economy**.

**How it works today (the Google model):** You search for "car insurance." Google sells your search behaviour to insurers. You get ads. The insurer pays Google. You get nothing.

**How it works with MySolido:** Your vault contains structured data — family size, car details, current insurance. When you want a new policy, you create an intention: "I'm looking for car insurance." MySolido can share this anonymously with the market. Insurers bid on your intention — without knowing your name. You choose the best offer, on your terms.

This is sometimes called the "Reverse Google" — instead of companies harvesting your data, you control it and share it voluntarily.

**What's built today:**
- **Profile module** — Structured attributes stored locally as JSON-LD
- **Intention module** — Create, manage and activate intentions linked to your profile
- **Consent requests** — External parties (e.g. insurance agents) can request data access via the Bridge. You approve or reject, choosing exactly which data to share

**What's coming:**
- AI assistant — A local LLM that searches your vault, summarises documents, reminds you of expiring policies
- Marketplace — Anonymous matching of intentions and offers

The requesting party pays — not the consumer.

---

## Bridge — Your vault, accessible anywhere

MySolido Bridge mirrors your local vault to a Dutch server. Your PC remains the master — the Bridge is a read-only copy.

- **Always reachable** — Open your vault on your phone via bridge.mysolido.com
- **Share links** — Share files via a secure URL, recipients don't need Solid
- **Consent requests** — External parties can submit data requests via the Bridge
- **Backup** — Automatic second copy on a Dutch VPS
- **Secured** — HTTPS + password authentication, read-only (no uploads/deletes via internet)

Local is master. The Bridge syncs along.

🌐 **Live demo:** [bridge.mysolido.com](https://bridge.mysolido.com)

---

## Connecting external Solid apps

MySolido is a fully-fledged Solid pod — you can connect any Solid-compatible app to it.

### Login URL

Use your WebID as the login URL:

```
http://127.0.0.1:3000/mysolido/profile/card#me
```

### Credentials

Find your CSS account e-mail and password on the Profile page in MySolido under **Solid app login** / **Inloggen in Solid apps**. The password is auto-generated on first start and stored locally in your `.env`; you can reveal, copy, and change it from that page.

### Example apps

- [Umai](https://umai.app) — recipe management
- [Solid Data Browser](https://solidcommunity.net) — generic pod browser
- Any other app listed at [solidproject.org/apps](https://solidproject.org/apps)

### Limitations

Because MySolido runs on your own machine (`127.0.0.1`), your WebID is not publicly resolvable. This means:

- External apps can connect to your pod only from the same machine (or via a Bridge if configured)
- Other users cannot reference your WebID from their own apps without a publicly resolvable URL

For use cases that require publicly resolvable WebIDs (sharing data across machines, multi-user scenarios), setting up a Bridge is recommended.

---

## Installation

### Requirements

- [Node.js](https://nodejs.org) v18 or higher
- [Python](https://python.org) 3.10 or higher
- Windows 10/11 (Mac/Linux experimental)

### Quick install (Windows)

Download the [latest release](https://github.com/Wim1201/mysolido/releases) and run `MySolido-Setup.exe`. The installer sets up everything automatically.

### Manual installation

```bash
# 1. Clone the repository
git clone https://github.com/Wim1201/mysolido.git
cd mysolido

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Install Community Solid Server
npm install @solid/community-server

# 4. Start CSS (terminal 1)
node node_modules/.bin/community-solid-server -p 3000 -f .data/ -c @css:config/file.json -b http://127.0.0.1:3000

# 5. Start MySolido (terminal 2)
python app.py
```

Open <http://localhost:5000> in your browser.

On first launch, MySolido automatically creates an account and pod.

No login required — MySolido runs on your own PC. The Solid server on port 3000 is managed automatically; you only interact with port 5000.

### macOS

Download `MySolido-Installer.dmg` from the [Releases](https://github.com/Wim1201/mysolido/releases) page.

Or install manually:

```bash
git clone https://github.com/Wim1201/mysolido.git
cd mysolido
npm install
pip3 install -r requirements.txt
bash start-mysolido.sh
```

> macOS may show a warning about an unknown developer. Go to System Settings → Privacy & Security → "Open Anyway".

### Starting after installation

```bash
# Windows: double-click
start-mysolido.bat

# macOS
bash start-mysolido.sh

# Stop
stop-mysolido.bat       # Windows
# macOS: Ctrl+C in terminal
```

---

## How does it work?

MySolido runs two components on your PC:

1. **Community Solid Server (CSS)** — Pod storage on port 3000. An open source W3C Solid server that manages your data.
2. **Flask app** — The user interface on port 5000. This is where you upload, view, share and manage your files.

Your data lives in the `.data/` folder on your own hard drive. Nothing leaves your computer unless you choose to share it.

```
┌─────────────────┐     ┌──────────────────┐
│  Flask UI :5000  │────→│  CSS Pod :3000   │
│  (your browser)  │     │  (.data/ folder) │
└─────────────────┘     └──────────────────┘
        ↑
   You work here
```

---

## For insurance agents and intermediaries

MySolido offers a new way to reach clients — with their permission.

1. You open `bridge.mysolido.com/verzoek` and submit a data request
2. Your client sees the request in their MySolido vault
3. They choose exactly which data to share (e.g. vehicle details, current policies)
4. You receive a temporary, secure link to the approved data
5. Every consent is registered according to ISO 27560 — legally stronger than cookie banners

The data cannot be resold (enforced via ODRL policy). Watermarks make any leak traceable.

**Pricing:** Per request (€0.50–2) or monthly subscription (€25–50/month). The requesting party pays — not the client.

---

## Roadmap

### Available

* ODRL policy engine — sharing rules per folder (W3C ODRL 2.2)
* Consent management — consent records compliant with ISO/IEC TS 27560:2023
* Watermarks on share links — automatic watermark on PDFs and images
* macOS installer (.dmg) and Windows installer (.exe)
* Bridge — always reachable via bridge.mysolido.com
* Profile module — structured personal attributes with W3C DPV vocabulary
* Intention module — anonymous intentions linked to profile data
* Consent requests — external parties can request data via the Bridge
* Anonymous crash reporting — opt-in, no personal data sent
* AI assistant — Local RAG pipeline (Ollama + ChromaDB) with optional hybrid mode (Claude API). Your files stay local
* Bilingual interface — Full Dutch/English, switchable in settings
* OCR — Local (Tesseract) or cloud (Mistral, EU) text recognition for scanned documents
* Trust & Transparency page — mysolido.com/trust

### Planned

* **Marketplace** — Anonymous matching of intentions and offers (Intention Economy)
* Per-folder encryption
* A4DS/UMA authorisation (role-based access)
* EUDI Wallet / Jouw.id integration
* API connections (government services, insurers, banks)
* Portable installer (USB stick, no installation needed)

---

## Technology

| Component | Technology |
|-----------|-----------|
| Pod storage | [Community Solid Server](https://github.com/CommunitySolidServer/CommunitySolidServer) v7.1.9 |
| Interface | Flask (Python) |
| Protocol | [Solid](https://solidproject.org) (W3C standard) |
| Data format | RDF / Linked Data / JSON-LD |
| Policies | ODRL 2.2 (W3C Recommendation) |
| Consent | W3C Data Privacy Vocabulary v2.3 + ISO/IEC TS 27560:2023 |
| Profile data | W3C DPV Personal Data Categories + JSON-LD |
| Watermarks | reportlab (PDF) + Pillow (images) |
| Bridge | Dutch VPS (mijn.host) + Nginx + Let's Encrypt |

MySolido uses the same standard as [Athumi](https://athumi.be) (Flemish government), the [Dutch Data Vault](https://jouw.id) (Upod) and the EU Digital Identity Wallet — fully interoperable.

---

## Privacy

* **No cloud** — Everything runs locally on your PC
* **No tracking** — No analytics, no cookies, no telemetry
* **No registration** — Download and use, no account needed
* **No third party** — Your data never leaves your computer unless you choose to share
* **Open source** — Verify what the software does yourself
* **Bridge optional** — The Bridge is an optional add-on. MySolido works fully offline without it
* **Crash reporting opt-in** — Anonymous error reports are only sent if you enable them in settings. No personal data is included.

---

## Three layers of protection when sharing

| Layer | How |
|-------|-----|
| **Technical** | Watermarks on shared documents. Traceable if leaked. No download button. |
| **Legal** | ODRL policies: machine-readable rules. "Read only, do not distribute, valid until date X." Enforceable. |
| **Registration** | Every consent recorded per ISO 27560 + W3C DPV. Burden of proof on the requester. |

Cookie banners offer zero protection. MySolido offers three layers.

---

## FAQ

**Isn't this just a file manager?**
No. Your data is stored in a Solid pod with RDF metadata. Any Solid-compatible app can work with your data. It's interoperable personal data infrastructure, not just file storage.

**Why not Nextcloud?**
Nextcloud is a self-hosted cloud — it replaces Google Drive as a server. MySolido is different: it's a local desktop vault built on Solid. Your data stays on your PC, not on a server. They're complementary, not competing.

**What if my PC crashes?**
Export regular backups (ZIP) via the settings. With the Bridge, you automatically have a copy on a second location.

**Does it work on Mac/Linux?**
macOS is supported with a `.dmg` installer and `start-mysolido.sh` launcher script. Linux users can follow the manual installation (Python + Node.js).

**Can a party that receives my data resell it?**
No. The ODRL policy prohibits distribution. Every consent is registered with a specific purpose. Reselling violates the agreement and GDPR. Watermarks make any leak traceable.

---

## Contributing

MySolido is open source under the GPLv3 license. Contributions are welcome:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Commit your changes (`git commit -m 'Add my feature'`)
4. Push to the branch (`git push origin feature/my-feature`)
5. Open a Pull Request

---

## Links

- 🌐 Website: [mysolido.com](https://mysolido.com)
- 📦 Releases: [GitHub Releases](https://github.com/Wim1201/mysolido/releases)
- 🔷 Solid protocol: [solidproject.org](https://solidproject.org)
- 🌉 Bridge: [bridge.mysolido.com](https://bridge.mysolido.com) (live Bridge)
- 💬 Solid Community Forum: [forum.solidproject.org](https://forum.solidproject.org)

---

## License

[GPLv3](LICENSE) — Free to use, modify and distribute. Derivative works must also be open source.

---

*MySolido — Your data. On your PC. Your terms.*
