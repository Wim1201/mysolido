TRANSLATIONS = {
    "nl": {
        "app_subtitle": "Jouw persoonlijke datakluis",
        "bridge_subtitle": "Bridge (alleen-lezen)",
        "nav_vault": "Kluis",
        "nav_shared": "Gedeeld",
        "nav_trash": "Prullenbak",
        "nav_log": "Logboek",
        "nav_consent": "Toestemmingen",
        "nav_profile": "Profiel",
        "nav_search": "Zoeken",
        "nav_trash_short": "Prullen",
        "theme_toggle": "Thema wisselen",
        "sync_bridge": "Synchroniseer naar Bridge",
        "logout": "Uitloggen",
        "bridge_banner": "Je bekijkt deze kluis via de Bridge (alleen-lezen). Uploaden en bewerken doe je op je lokale MySolido.",
        "loading": "Laden...",
        "settings_language_title": "Taal",
        "save": "Opslaan",
    },
    "en": {
        "app_subtitle": "Your personal data vault",
        "bridge_subtitle": "Bridge (read-only)",
        "nav_vault": "Vault",
        "nav_shared": "Shared",
        "nav_trash": "Trash",
        "nav_log": "Audit log",
        "nav_consent": "Consent",
        "nav_profile": "Profile",
        "nav_search": "Search",
        "nav_trash_short": "Trash",
        "theme_toggle": "Toggle theme",
        "sync_bridge": "Sync to Bridge",
        "logout": "Log out",
        "bridge_banner": "You are viewing this vault via the Bridge (read-only). Upload and edit on your local MySolido.",
        "loading": "Loading...",
        "settings_language_title": "Language",
        "save": "Save",
    }
}


def get_translations(lang="nl"):
    return TRANSLATIONS.get(lang, TRANSLATIONS["nl"])
