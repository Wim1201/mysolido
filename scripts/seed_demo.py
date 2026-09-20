#!/usr/bin/env python3
"""Vul een lege MySolido-Pod met demodata voor de MyTerms-demo (subtaak 2, 20-09-2026).

Wat het doet, in deze volgorde:
  1. controleert dat de Pod-map bestaat en dat CSS op CSS_BASE_URL antwoordt;
  2. weigert als profiel/profiel.jsonld al bestaat (tenzij --force);
  3. maakt de twintig DEFAULT_FOLDERS aan die nog ontbreken (bestaande mappen blijven ongemoeid);
  4. schrijft profiel/profiel.jsonld met een fictief demoprofiel via PROFILE_ATTRIBUTES
     (35-44, postcodegebied 5611, auto benzine 2019, 5 schadevrije jaren, geen claims) en de
     vaste mappolicy profiel/.policy.jsonld;
  5. zet drie voorbeeldtekstbestanden in voertuigen/ en financieel/;
  6. print wat is aangemaakt.

Het script wist nooit iets en gebruikt dezelfde schrijfroutines als de app (pod_mkdir,
pod_write, set_profile_attribute, ensure_profiel_policy uit app.py). Importeren van app.py heeft
twee bijwerkingen: load_dotenv() en het aanmaken van de map temp/ in de projectmap; er start
geen server en er wordt niets in de Pod geschreven voordat dit script dat zelf doet.

Gebruik:
    python scripts/seed_demo.py            # weigert als er al een profiel is
    python scripts/seed_demo.py --force    # overschrijft profiel en voorbeeldbestanden
    python scripts/seed_demo.py --skip-css-check

Exitcodes: 0 gelukt, 1 geweigerd (profiel bestaat al), 2 omgevingsfout.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app as mysolido  # noqa: E402  (bijwerkingen: zie docstring)

# Fictief demoprofiel; sleutels zijn attribuutsleutels uit PROFILE_ATTRIBUTES.
# Bewust geen lopende autoverzekering: de demopersoon zoekt er juist een.
DEMO_PROFILE = {
    'age_category': '35-44',
    'postal_area': '5611',
    'housing_ownership': 'koop',
    'housing_type': 'tussenwoning',
    'region': 'Noord-Brabant',
    'household_size': 3,
    'children': [{'ageCategory': '5-12'}],
    'vehicle_type': 'auto',
    'vehicle_fuel': 'benzine',
    'vehicle_year': 2019,
    'insurances': [
        {'type': 'zorg', 'provider': 'Demo Zorgverzekeraar'},
        {'type': 'aansprakelijkheid', 'provider': 'Demo Verzekeringen'},
    ],
    'claims_history': {'claimFreeYears': 5, 'claimsLast3Years': False},
    'work_sector': 'ict',
    'employment_type': 'loondienst',
    'smoking_status': 'nee',
}

DEMO_FILES = {
    'voertuigen/demo-kentekenbewijs.txt': (
        "DEMOBESTAND - fictief kentekenbewijs\n"
        "Kenteken: XX-000-X (fictief)\n"
        "Merk/type: demo hatchback, benzine, bouwjaar 2019\n"
        "Dit bestand is aangemaakt door scripts/seed_demo.py voor de MyTerms-demo.\n"
    ),
    'voertuigen/demo-apk-rapport-2026.txt': (
        "DEMOBESTAND - fictief APK-rapport 2026\n"
        "Uitslag: goedgekeurd, geen adviespunten\n"
        "Dit bestand is aangemaakt door scripts/seed_demo.py voor de MyTerms-demo.\n"
    ),
    'financieel/demo-jaaroverzicht-2025.txt': (
        "DEMOBESTAND - fictief jaaroverzicht 2025\n"
        "Bedragen zijn verzonnen en dienen alleen om de per-veldselectie iets te laten zien.\n"
        "Dit bestand is aangemaakt door scripts/seed_demo.py voor de MyTerms-demo.\n"
    ),
}

PROFILE_PATH = 'profiel/profiel.jsonld'

# --reset (subtaak 5): schone startstand voor de demo. Alleen deze mappen en bestanden.
RESET_FOLDERS = ('intenties', 'verzoeken', 'toestemmingen')
RUNTIME_FILES = ('audit_log.json', 'notifications.json', 'trash.json', 'shares.json')


def reset_plan(pod_dir: str):
    """Wat --reset gaat verwijderen (Pod) en leegmaken (projectmap). Niets buiten deze lijst."""
    pod_files = []
    for folder in RESET_FOLDERS:
        folder_path = os.path.join(pod_dir, folder)
        if os.path.isdir(folder_path):
            for name in sorted(os.listdir(folder_path)):
                path = os.path.join(folder_path, name)
                if os.path.isfile(path):
                    pod_files.append(path)
    runtime_files = [str(ROOT / name) for name in RUNTIME_FILES if (ROOT / name).is_file()]
    return pod_files, runtime_files


def do_reset(pod_files, runtime_files):
    """Voer het plan uit: records, policies, agreements en responses weg; runtime-bestanden leeg."""
    for path in pod_files:
        os.remove(path)
    for path in runtime_files:
        try:
            with open(path, 'r', encoding='utf-8') as f:
                current = json.load(f)
        except (ValueError, OSError):
            current = []
        empty = {} if isinstance(current, dict) else []
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(empty, f)


def build_demo_profile() -> dict:
    """Bouw het profiel-JSON-LD uitsluitend via PROFILE_ATTRIBUTES (zelfde vorm als profiel_data_save)."""
    profile = {"@context": dict(mysolido.PROFILE_CONTEXT), "@type": "dpv:PersonalData"}
    for key, value in DEMO_PROFILE.items():
        if key not in mysolido.PROFILE_ATTRIBUTES:
            raise SystemExit(f"[FOUT] DEMO_PROFILE bevat onbekend attribuut '{key}'")
        mysolido.set_profile_attribute(profile, key, value)
    return profile


def check_environment(skip_css_check: bool) -> str:
    pod_dir = mysolido.get_pod_data_path()
    if not os.path.isdir(pod_dir):
        print(f"[FOUT] Pod-map ontbreekt: {pod_dir}. Start CSS en de app eerst één keer (auto-setup).")
        sys.exit(2)
    css_base = os.getenv('CSS_BASE_URL', mysolido.CSS_BASE_URL).rstrip('/')
    if not skip_css_check:
        try:
            r = requests.get(f'{css_base}/', headers={'Accept': 'text/turtle'}, timeout=10)
            if r.status_code not in (200, 401):
                print(f"[FOUT] CSS antwoordt met status {r.status_code} op {css_base}/")
                sys.exit(2)
        except requests.RequestException as exc:
            print(f"[FOUT] CSS niet bereikbaar op {css_base}: {exc!r} (gebruik --skip-css-check om toch te seeden)")
            sys.exit(2)
    return pod_dir


def main() -> None:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    parser = argparse.ArgumentParser(description='Vul een lege MySolido-Pod met demodata (MyTerms-demo).')
    parser.add_argument('--force', action='store_true', help='overschrijf een bestaand profiel en de voorbeeldbestanden')
    parser.add_argument('--skip-css-check', action='store_true', help='controleer niet of CSS op CSS_BASE_URL antwoordt')
    parser.add_argument('--reset', action='store_true',
                        help='schone demostand: verwijder de inhoud van intenties/, verzoeken/ en toestemmingen/, '
                             'zet het profiel opnieuw (impliceert --force) en maak de runtime-bestanden in de projectmap leeg; '
                             'vereist --yes')
    parser.add_argument('--yes', action='store_true', help='bevestig --reset zonder navraag')
    args = parser.parse_args()

    pod_dir = check_environment(args.skip_css_check)
    print(f"Pod-map: {pod_dir}")
    print(f"Pod-URL: {os.getenv('SOLID_POD_URL', mysolido.SOLID_POD_URL)}")

    if args.reset:
        pod_files, runtime_files = reset_plan(pod_dir)
        print()
        print("--reset gaat verwijderen (Pod):")
        for path in pod_files:
            print(f"  {os.path.relpath(path, pod_dir)}")
        if not pod_files:
            print("  (niets: de drie mappen zijn leeg of bestaan niet)")
        print("--reset gaat leegmaken (projectmap):")
        for path in runtime_files:
            print(f"  {os.path.basename(path)}")
        if not runtime_files:
            print("  (geen runtime-bestanden aanwezig)")
        print(f"--reset zet daarna {PROFILE_PATH} opnieuw (als --force).")
        if not args.yes:
            print()
            print("[GEWEIGERD] --reset vereist --yes. Er is niets gewijzigd.")
            sys.exit(1)
        do_reset(pod_files, runtime_files)
        args.force = True
        print(f"[OK] {len(pod_files)} bestanden verwijderd, {len(runtime_files)} runtime-bestanden leeggemaakt.")
        print()

    if mysolido.pod_exists(PROFILE_PATH) and not args.force:
        print(f"[GEWEIGERD] {PROFILE_PATH} bestaat al. Gebruik --force om het demoprofiel te overschrijven.")
        sys.exit(1)

    created_folders, existing_folders = [], []
    for folder in mysolido.DEFAULT_FOLDERS:
        if mysolido.pod_exists(folder):
            existing_folders.append(folder)
        elif mysolido.pod_mkdir(folder):
            created_folders.append(folder)
        else:
            print(f"[FOUT] Map {folder} kon niet worden aangemaakt")
            sys.exit(2)

    profile = build_demo_profile()
    mysolido.pod_mkdir('profiel')
    if not mysolido.pod_write(PROFILE_PATH, json.dumps(profile, indent=2, ensure_ascii=False)):
        print(f"[FOUT] {PROFILE_PATH} kon niet worden geschreven")
        sys.exit(2)
    policy_existed = mysolido.pod_exists('profiel/.policy.jsonld')
    mysolido.ensure_profiel_policy()

    written_files, skipped_files = [], []
    for rel_path, content in DEMO_FILES.items():
        if mysolido.pod_exists(rel_path) and not args.force:
            skipped_files.append(rel_path)
            continue
        mysolido.pod_write(rel_path, content)
        written_files.append(rel_path)

    print()
    print("Aangemaakt:")
    print(f"  mappen ({len(created_folders)} nieuw, {len(existing_folders)} bestonden al): "
          f"{', '.join(created_folders) or '-'}")
    print(f"  {PROFILE_PATH} ({'overschreven' if args.force else 'nieuw'})")
    print(f"  profiel/.policy.jsonld ({'bestond al' if policy_existed else 'nieuw'})")
    for rel_path in written_files:
        print(f"  {rel_path}")
    for rel_path in skipped_files:
        print(f"  ({rel_path} bestond al, overgeslagen)")
    print()
    print("Demoprofiel (scenario-attributen):")
    for key in ('age_category', 'postal_area', 'vehicle_type', 'claims_history'):
        value = mysolido.profile_attribute_value(profile, key)
        print(f"  {mysolido.attribute_urn(key):<45} {mysolido.attribute_value_label(key, value)}")
    print()
    if args.reset:
        print("Schone demostand: intenties/, verzoeken/ en toestemmingen/ zijn leeg; de mappolicies daarin maakt de app "
              "opnieuw aan bij het eerste record. Logboek, prullenbak en deelregister zijn leeg.")
    else:
        print("Niet aangeraakt: intenties/, verzoeken/, toestemmingen/ en alle overige bestaande bestanden.")


if __name__ == '__main__':
    main()
