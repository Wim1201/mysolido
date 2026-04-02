🇬🇧 **English** | 🇳🇱 [Nederlands](README.nl.md)

# 🛡️ MySolido

**Your personal data vault on your own PC.**

MySolido is open source software that runs a personal data vault (Solid Pod) on your own computer. No cloud, no third party, no subscription. Built on the [Solid protocol](https://solidproject.org) — the same W3C standard used by [Athumi](https://athumi.be) (Flanders) and the [Dutch Data Vault](https://jouw.id).

> *"The first Pod that needs no provider."*

🌐 [mysolido.com](https://mysolido.com) · 📦 [Download](https://github.com/Wim1201/mysolido/releases)

---

## What can MySolido do?

- **20 categories** — Identity, medical, financial, legal, insurance, and more
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
- **macOS support** — `.dmg` installer available, or manual installation via Terminal

---

## Bridge — Your vault, accessible anywhere

MySolido Bridge mirrors your local vault to a Dutch server. Your PC remains the master — the Bridge is a read-only copy.

- **Always reachable** — Open your vault on your phone via bridge.mysolido.com
- **Share links** — Share files via a secure URL, recipients don't need Solid
- **Backup** — Automatic second copy on a Dutch VPS
- **Secured** — HTTPS + password authentication, read-only (no uploads/deletes via internet)

Local is master. The Bridge syncs along.

🌐 **Live demo:** [bridge.mysolido.com](https://bridge.mysolido.com)

---

## Installation

### Requirements

- [Node.js](https://nodejs.org) v18 or higher
- [Python](https://python.org) 3.10 or higher
- Windows 10/11 (Mac/Linux experimental)

### Quick install (Windows)

Download the [latest release](https://github.com/Wim1201/mysolido/releases) and run `installeer-mysolido.bat`. The script automatically installs:

1. Node.js (if not present)
2. Python (if not present)
3. MySolido source code
4. Python dependencies
5. Community Solid Server
6. Starts the app and opens your browser

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

## Roadmap

### Available

* ODRL policy engine — sharing rules per folder (W3C ODRL 2.2)
* Consent management — consent records compliant with ISO/IEC TS 27560:2023
* Watermarks on share links — automatic watermark on PDFs and images
* macOS installer (.dmg)
* Bridge — always reachable via bridge.mysolido.com

### Planned

* **AI-ready vault** — Your documents, chat history and preferences safely available locally for personal AI agents
* Per-folder encryption
* OCR / document scanning
* A4DS/UMA authorisation (role-based access)
* EUDI Wallet / Jouw.id integration
* API connections (government services, insurers, banks)
* Portable installer (USB stick, no installation needed)

---

## Technology

| Component | Technology |
|-----------|-----------|
| Pod storage | [Community Solid Server](https://github.com/CommunitySolidServer/CommunitySolidServer) v7.1.8 |
| Interface | Flask (Python) |
| Protocol | [Solid](https://solidproject.org) (W3C standard) |
| Data format | RDF / Linked Data |
| Storage | Local on your own PC |
| Policies | ODRL 2.2 (W3C Recommendation) + JSON-LD |
| Consent | W3C Data Privacy Vocabulary v2.3 + ISO/IEC TS 27560:2023 |
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
