#!/usr/bin/env python3
"""MySolido regression test for the Community Solid Server (CSS) integration.

Runs against an already running stack (CSS on 127.0.0.1:3000 and Flask on 127.0.0.1:5000)
and reports PASS / FAIL / SKIP / INFO per check.

Scenarios:
  U  upgrade path: existing .env and .data/ (default)
  N  new installation: Flask's auto-setup created .env and the Pod just before this run

All test data is synthetic and lives in one folder inside the Pod (``regressietest/``) plus a
throwaway CSS test account with its own Pod. Everything is removed at the end, except when
``--keep-persist`` is given: then ``regressietest/acl-map/`` and ``regressietest/policy-map/``
stay behind so that ``--phase persist`` can verify after a server restart (or a CSS upgrade)
that their ACL and ODRL policy are still honoured. The script never contacts the Bridge VPS.

Why the LDP checks use a public sub-folder: CSS verifies access tokens with
@solid/access-token-verifier, which only accepts ``https`` WebID and issuer claims. On a plain
``http://127.0.0.1:3000`` server a client-credentials token therefore never authenticates as
the owner (the CSS log says "The URI claim could not be verified as secure"). The script makes
``regressietest/ldp/`` publicly readable and writable through MySolido's own share function so
that CSS's LDP behaviour can still be exercised without a token.

Usage:
    python scripts/regressietest.py [--scenario U|N] [--out results.json] [--keep] [--keep-persist]
    python scripts/regressietest.py --phase persist [--keep-persist] [--out results.json]
    python scripts/regressietest.py --phase bridge --bridge-password <password> [--out results.json]

The ``bridge`` phase expects Flask to run in read-only Bridge mode (``python app.py --bridge``)
and needs the plaintext Bridge password that was configured for that run.

See scripts/regressietest.md for the manual checklist that accompanies this script.
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import time
import zipfile
from datetime import datetime
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
TEST_FOLDER = 'regressietest'
LDP_FOLDER = 'ldp'
ACL_FOLDER = 'acl-map'
POLICY_FOLDER = 'policy-map'
TIMEOUT = 20
REDIRECT = (301, 302, 303, 307, 308)
ANSI = re.compile(r'\x1b\[[0-9;]*m')
DEFAULT_FOLDERS_SAMPLE = ('identiteit', 'medisch', 'financieel')
# Demodata (MyTerms-demo, subtaak 2): scripts/seed_demo.py maakt deze twintig mappen aan
DEFAULT_FOLDERS_ALL = (
    'identiteit', 'medisch', 'financieel', 'wonen', 'zakelijk',
    'werk', 'voertuigen', 'juridisch', 'media', 'accounts',
    'gezin', 'abonnementen', 'inbox', 'verzekeringen',
    'huisdieren', 'opleiding', 'reizen', 'digitaal-testament',
    'persoonlijk', 'projecten',
)
SEED_SCRIPT = ROOT / 'scripts' / 'seed_demo.py'
SEED_FILES = ('voertuigen/demo-kentekenbewijs.txt', 'voertuigen/demo-apk-rapport-2026.txt',
              'financieel/demo-jaaroverzicht-2025.txt')
ATTR = 'urn:mysolido:attribute:'
SCENARIO_ATTRIBUTES = ('age_category', 'postal_area', 'vehicle_type', 'claims_history')


# --- helpers -----------------------------------------------------------------------------

def load_env(path: Path) -> dict:
    """Minimal .env parser (KEY=VALUE lines, # comments)."""
    env = {}
    if not path.exists():
        return env
    for raw in path.read_text(encoding='utf-8-sig').splitlines():
        line = raw.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def actions(value) -> list:
    """Normalise an ODRL action field (string or list) to a list."""
    if isinstance(value, list):
        return value
    return [value] if value else []


def jwt_claims(token: str) -> dict:
    parts = token.split('.')
    if len(parts) != 3:
        return {}
    payload = parts[1] + '=' * (-len(parts[1]) % 4)
    try:
        return json.loads(base64.urlsafe_b64decode(payload))
    except (ValueError, json.JSONDecodeError):
        return {}


def last_css_log_line(pattern: str) -> str:
    """Last line of css.log matching ``pattern`` (ANSI colours stripped), or ''."""
    log = ROOT / 'css.log'
    if not log.exists():
        return ''
    matches = [ANSI.sub('', line) for line in log.read_text(encoding='utf-8', errors='replace').splitlines()
               if pattern in line]
    return matches[-1].strip() if matches else ''


def css_version() -> str:
    marker = ROOT / '.data' / '.internal' / 'setup' / 'current-server-version$.json'
    if marker.exists():
        return str(json.loads(marker.read_text(encoding='utf-8')).get('payload', '?'))
    return 'onbekend'


def disk_names(folder: Path, prefix: str) -> list:
    if not folder.exists():
        return []
    return sorted(p.name + ('/' if p.is_dir() else '') for p in folder.iterdir() if p.name.lower().startswith(prefix.lower()))


class Report:
    """Collects check results and prints them as they happen."""

    def __init__(self):
        self.items = []

    def add(self, status, name, detail=''):
        self.items.append({'status': status, 'name': name, 'detail': str(detail)[:500]})
        suffix = f'  -- {detail}' if detail else ''
        print(f'  [{status:<4}] {name}{suffix}')

    def ok(self, name, detail=''):
        self.add('PASS', name, detail)

    def fail(self, name, detail=''):
        self.add('FAIL', name, detail)

    def skip(self, name, detail=''):
        self.add('SKIP', name, detail)

    def info(self, name, detail=''):
        self.add('INFO', name, detail)

    def check(self, name, condition, detail_ok='', detail_fail=''):
        if condition:
            self.ok(name, detail_ok)
        else:
            self.fail(name, detail_fail or detail_ok)
        return bool(condition)

    def counts(self):
        out = {'PASS': 0, 'FAIL': 0, 'SKIP': 0, 'INFO': 0}
        for item in self.items:
            out[item['status']] += 1
        return out


class Ctx:
    """Test context: configuration, HTTP sessions and bookkeeping."""

    def __init__(self, args):
        self.scenario = args.scenario
        self.env = load_env(ROOT / '.env')
        self.css_base = (args.css_base or self.env.get('CSS_BASE_URL') or 'http://127.0.0.1:3000').rstrip('/')
        self.pod_url = self.env.get('SOLID_POD_URL') or f'{self.css_base}/mysolido/'
        if not self.pod_url.endswith('/'):
            self.pod_url += '/'
        self.webid = self.env.get('WEBID') or f'{self.pod_url}profile/card#me'
        self.client_id = self.env.get('CLIENT_ID', '')
        self.client_secret = self.env.get('CLIENT_SECRET', '')
        self.flask_base = args.flask_base.rstrip('/')
        pod_name = self.pod_url.rstrip('/').split('/')[-1]
        self.pod_dir = ROOT / '.data' / pod_name
        self.test_dir = self.pod_dir / TEST_FOLDER
        self.test_url = f'{self.pod_url}{TEST_FOLDER}/'
        self.ldp_dir = self.test_dir / LDP_FOLDER
        self.ldp_rel = f'{TEST_FOLDER}/{LDP_FOLDER}'
        self.ldp_url = f'{self.test_url}{LDP_FOLDER}/'
        self.flask = requests.Session()
        self._token = None
        self.report = Report()
        self.run_id = secrets.token_hex(3)
        self.pre_existing = {
            name: (self.pod_dir / name).exists()
            for name in ('_trash', 'toestemmingen', 'verzoeken', 'intenties', 'profiel', '.mysolido', TEST_FOLDER)
        }
        self.seeded = False

    @property
    def token(self):
        if self._token is None:
            self._token = css_token(self, self.client_id, self.client_secret)
        return self._token


def css_token(ctx: Ctx, client_id: str, client_secret: str) -> str:
    """Client-credentials token exactly like app.get_access_token() does it."""
    auth = base64.b64encode(f'{client_id}:{client_secret}'.encode()).decode()
    r = requests.post(
        f'{ctx.css_base}/.oidc/token',
        data={'grant_type': 'client_credentials', 'scope': 'webid'},
        headers={'Authorization': f'Basic {auth}',
                 'Content-Type': 'application/x-www-form-urlencoded'},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    return r.json()['access_token']


def css(ctx: Ctx, method: str, url: str, token: str | None = None, **kwargs):
    headers = kwargs.pop('headers', {})
    if token:
        headers['Authorization'] = f'Bearer {token}'
    kwargs.setdefault('timeout', TIMEOUT)
    kwargs.setdefault('allow_redirects', False)
    return requests.request(method, url, headers=headers, **kwargs)


def flask(ctx: Ctx, method: str, path: str, **kwargs):
    kwargs.setdefault('timeout', TIMEOUT)
    kwargs.setdefault('allow_redirects', False)
    return ctx.flask.request(method, f'{ctx.flask_base}{path}', **kwargs)


def upload(ctx: Ctx, name: str, content: bytes, folder: str = TEST_FOLDER):
    return flask(ctx, 'POST', '/upload', data={'upload_folder': folder},
                 files={'file': (name, content, 'text/plain')})


def share(ctx: Ctx, resource_url: str, resource_path: str, folder_path: str, webid: str, level: str):
    return flask(ctx, 'POST', '/share', data={'resource_url': resource_url, 'resource_path': resource_path,
                                              'folder_path': folder_path, 'webid': webid,
                                              'access_level': level, 'expires': ''})


def revoke(ctx: Ctx, resource_url: str, resource_path: str, webid: str):
    return flask(ctx, 'POST', '/revoke', data={'resource_url': resource_url, 'webid': webid,
                                               'resource_path': resource_path})


def trash_entry(ctx: Ctx, filename: str):
    trash_file = ROOT / 'trash.json'
    if not trash_file.exists():
        return None
    for entry in json.loads(trash_file.read_text(encoding='utf-8')):
        if entry.get('filename') == filename and entry.get('original_folder') == TEST_FOLDER:
            return entry
    return None


def trash_path(ctx: Ctx, entry: dict) -> Path:
    """On-disk path of a trashed file, derived from its trash_url like app.py does."""
    rel = entry['trash_url'][len(ctx.pod_url):]
    return ctx.pod_dir / rel


def newest_share_link(ctx: Ctx, file_path: str):
    links_file = ctx.pod_dir / '.mysolido' / 'share_links.json'
    if not links_file.exists():
        return None
    links = [l for l in json.loads(links_file.read_text(encoding='utf-8')).get('links', [])
             if l.get('file_path') == file_path]
    return links[-1] if links else None


def run_phase(ctx: Ctx, name: str, fn, *args):
    print(f'\n== {name} ==')
    try:
        return fn(ctx, *args)
    except Exception as exc:  # noqa: BLE001 - report and carry on with the next phase
        ctx.report.fail(f'{name}: onverwachte fout', repr(exc))
        return None


# --- phases ------------------------------------------------------------------------------

def phase_preflight(ctx: Ctx):
    rep = ctx.report
    rep.check('.env gevonden met CLIENT_ID en CLIENT_SECRET',
              bool(ctx.client_id and ctx.client_secret),
              f'Pod {ctx.pod_url}', '.env ontbreekt of is onvolledig')
    rep.check('Pod-map op schijf aanwezig', ctx.pod_dir.is_dir(), str(ctx.pod_dir), f'{ctx.pod_dir} ontbreekt')
    try:
        r = css(ctx, 'GET', ctx.css_base + '/', headers={'Accept': 'text/turtle'})
        rep.check('CSS antwoordt op poort 3000', r.status_code in (200, 401),
                  f'status {r.status_code}, X-Powered-By: {r.headers.get("X-Powered-By", "-")}',
                  f'status {r.status_code}')
    except requests.RequestException as exc:
        rep.fail('CSS antwoordt op poort 3000', repr(exc))
    rep.info('CSS-versie volgens .data/.internal/setup', css_version())
    readme = disk_names(ctx.pod_dir, 'README')
    rep.info('README van het Pod-template op schijf', readme or 'ontbreekt')
    try:
        r = flask(ctx, 'GET', '/')
        rep.check('Flask antwoordt op poort 5000', r.status_code == 200, f'status {r.status_code}', f'status {r.status_code}')
        welcome = 'init-folders-welcome' in r.text
        if ctx.scenario == 'N':
            rep.check('Scenario N: welkomstscherm op verse Pod', welcome, '',
                      f'dashboard getoond; is_pod_empty() vergelijkt met "README", op schijf staat {readme}')
        else:
            rep.info('Welkomstscherm op dashboard', 'ja' if welcome else 'nee, dashboard getoond')
    except requests.RequestException as exc:
        rep.fail('Flask antwoordt op poort 5000', repr(exc))
    if ctx.scenario == 'N':
        rep.check('Scenario N: auto-setup schreef .env met CSS_EMAIL, WEBID en credentials',
                  bool(ctx.env.get('CSS_EMAIL') and ctx.env.get('WEBID') and ctx.client_id),
                  f'CSS_EMAIL {ctx.env.get("CSS_EMAIL")}', f'sleutels: {sorted(ctx.env)}')
        rep.check('Scenario N: WEBID in .env wijst naar 127.0.0.1', '127.0.0.1' in ctx.webid, ctx.webid, ctx.webid)
        present = [f for f in DEFAULT_FOLDERS_SAMPLE if (ctx.pod_dir / f).is_dir()]
        rep.info('Scenario N: standaardmappen aangemaakt bij eerste start', f'{present or "geen"} (start-mysolido.bat roept /init-folders alleen aan als .data\\mysolido nog niet bestaat)')
        cards = disk_names(ctx.pod_dir / 'profile', 'card')
        rep.info('Scenario N: WebID-document op schijf', cards or 'ontbreekt')
    rep.check('Testmap bestaat nog niet', not ctx.pre_existing[TEST_FOLDER], TEST_FOLDER,
              f'{ctx.test_dir} bestaat al; eerst opruimen')


def phase_account(ctx: Ctx):
    """Create a throwaway account, Pod and client credentials via the CSS account API."""
    rep = ctx.report
    email = f'regressietest-{ctx.run_id}@mysolido.local'
    pod_name = f'regressietest-pod-{ctx.run_id}'

    r = css(ctx, 'GET', f'{ctx.css_base}/.account/', headers={'Accept': 'application/json'})
    if not rep.check('Account-API bereikbaar (/.account/)', r.status_code == 200,
                     f'status {r.status_code}', f'status {r.status_code}'):
        return None
    controls = r.json().get('controls', {})
    create_url = controls.get('account', {}).get('create')
    if not rep.check('controls.account.create aanwezig', bool(create_url), create_url, json.dumps(controls)[:300]):
        return None

    r = requests.post(create_url, json={}, headers={'Content-Type': 'application/json'}, timeout=TIMEOUT)
    authorization = None
    if r.headers.get('Content-Type', '').startswith('application/json'):
        authorization = r.json().get('authorization')
    if not rep.check('Account aanmaken', r.status_code in (200, 201) and bool(authorization),
                     f'status {r.status_code}', f'status {r.status_code}: {r.text[:200]}'):
        return None
    auth_hdr = {'Authorization': f'CSS-Account-Token {authorization}', 'Accept': 'application/json'}
    json_hdr = dict(auth_hdr, **{'Content-Type': 'application/json'})

    r = requests.get(f'{ctx.css_base}/.account/', headers=auth_hdr, timeout=TIMEOUT)
    full = r.json().get('controls', {}) if r.status_code == 200 else {}
    pw_url = full.get('password', {}).get('create')
    pod_ctl = full.get('account', {}).get('pod')
    cred_url = full.get('account', {}).get('clientCredentials')
    if not rep.check('controls bevatten password.create, account.pod en account.clientCredentials',
                     bool(pw_url and pod_ctl and cred_url), '', f'status {r.status_code}: {r.text[:300]}'):
        return None

    password = secrets.token_urlsafe(16)
    r = requests.post(pw_url, json={'email': email, 'password': password}, headers=json_hdr, timeout=TIMEOUT)
    rep.check('E-mail/wachtwoord registreren', r.status_code in (200, 201),
              f'status {r.status_code}', f'status {r.status_code}: {r.text[:200]}')

    r = requests.post(pod_ctl, json={'name': pod_name}, headers=json_hdr, timeout=TIMEOUT)
    body = r.json() if r.headers.get('Content-Type', '').startswith('application/json') else {}
    pod_url = body.get('pod') or f'{ctx.css_base}/{pod_name}/'
    webid = body.get('webId') or f'{pod_url}profile/card#me'
    if not rep.check('Test-Pod aanmaken', r.status_code in (200, 201), pod_url,
                     f'status {r.status_code}: {r.text[:200]}'):
        return None
    test_pod_dir = ROOT / '.data' / pod_name
    rep.check('Test-Pod staat op schijf als .data/<podnaam>/', test_pod_dir.is_dir(),
              str(test_pod_dir), 'map niet gevonden')
    r = css(ctx, 'GET', webid.split('#')[0], headers={'Accept': 'text/turtle'})
    rep.check('Test-WebID publiek bereikbaar met solid:oidcIssuer', r.status_code == 200 and 'oidcIssuer' in r.text,
              webid, f'status {r.status_code}')
    r = css(ctx, 'GET', pod_url, headers={'Accept': 'text/turtle'})
    rep.check('Test-Pod-root bereikbaar', r.status_code == 200, f'status {r.status_code}', f'status {r.status_code}')

    r = requests.post(cred_url, json={'name': 'regressietest', 'webId': webid}, headers=json_hdr, timeout=TIMEOUT)
    cred = r.json() if r.status_code in (200, 201) else {}
    if not rep.check('Client credentials aanmaken', bool(cred.get('id') and cred.get('secret')),
                     'id en secret ontvangen', f'status {r.status_code}: {r.text[:200]}'):
        return None
    account = {'authorization': authorization, 'controls': full, 'pod_url': pod_url, 'webid': webid,
               'pod_dir': test_pod_dir, 'client_id': cred['id'], 'client_secret': cred['secret'], 'email': email}
    try:
        token = css_token(ctx, cred['id'], cred['secret'])
        claims = jwt_claims(token)
        rep.check('Testaccount: token via /.oidc/token met webid-claim', claims.get('webid') == webid,
                  f'iss {claims.get("iss")}', f'claims {json.dumps(claims)[:200]}')
        account['token'] = token
    except requests.RequestException as exc:
        rep.fail('Testaccount: token via /.oidc/token met webid-claim', repr(exc))
    return account


def phase_webid_credentials(ctx: Ctx):
    rep = ctx.report
    r = css(ctx, 'GET', ctx.webid.split('#')[0], headers={'Accept': 'text/turtle'})
    rep.check('WebID-document publiek leesbaar', r.status_code == 200, f'status {r.status_code}', f'status {r.status_code}')
    rep.check('WebID bevat solid:oidcIssuer', 'oidcIssuer' in r.text, '', r.text[:200])
    has_storage = 'pim/space#storage' in r.text or 'pim:storage' in r.text
    rep.info('WebID bevat pim:storage (7.2.0-changelog)', 'ja' if has_storage else 'nee')
    try:
        claims = jwt_claims(ctx.token)
        rep.check('Client credentials uit .env leveren een access token met webid-claim',
                  claims.get('webid') == ctx.webid,
                  f'iss {claims.get("iss")}, client_id {claims.get("client_id", "-")}',
                  f'claims {json.dumps(claims)[:200]}')
    except Exception as exc:  # noqa: BLE001
        rep.fail('Client credentials uit .env leveren een access token met webid-claim', repr(exc))
        return
    r = css(ctx, 'GET', ctx.pod_url, headers={'Accept': 'text/turtle'})
    rep.check('Pod-root publiek leesbaar (CSS-pod-template geeft foaf:Agent Read op de root)',
              r.status_code == 200, f'status {r.status_code}', f'status {r.status_code}')


def phase_files(ctx: Ctx):
    rep = ctx.report

    r = flask(ctx, 'POST', '/create-folder', data={'folder_path': '', 'folder_name': TEST_FOLDER})
    rep.check('Flask: map aanmaken', r.status_code in REDIRECT and ctx.test_dir.is_dir(), TEST_FOLDER,
              f'status {r.status_code}, map bestaat: {ctx.test_dir.is_dir()}')
    r = css(ctx, 'GET', ctx.test_url, headers={'Accept': 'text/turtle'})
    rep.check('Nieuwe map erft eigenaar-ACL: anoniem 401', r.status_code == 401, f'status {r.status_code}', f'status {r.status_code}')
    r = css(ctx, 'GET', ctx.test_url, token=ctx.token, headers={'Accept': 'text/turtle'})
    reason = last_css_log_line('BearerWebIdExtractor')
    rep.info('Bearer-token (client credentials) op beschermde map',
             f'status {r.status_code}; css.log: {reason.split("warn: ")[-1] if reason else "geen melding"}')

    r = flask(ctx, 'POST', '/create-folder', data={'folder_path': TEST_FOLDER, 'folder_name': LDP_FOLDER})
    rep.check('Flask: submap aanmaken', r.status_code in REDIRECT and ctx.ldp_dir.is_dir(), ctx.ldp_rel,
              f'status {r.status_code}')
    share(ctx, ctx.ldp_url, ctx.ldp_rel + '/', TEST_FOLDER, 'public', 'readwrite')
    acl = ctx.ldp_dir / '.acl'
    rep.check('Flask: submap publiek lees/schrijfbaar via deelfunctie (.acl in map)',
              acl.exists() and 'acl:Write' in acl.read_text(encoding='utf-8') and 'acl:default' in acl.read_text(encoding='utf-8'),
              'ldp/.acl', 'geen .acl met acl:Write en acl:default')
    r = css(ctx, 'GET', ctx.ldp_url, headers={'Accept': 'text/turtle'})
    rep.check('CSS ziet de Flask-map als LDP-container', r.status_code == 200 and 'BasicContainer' in r.text,
              f'status {r.status_code}', f'status {r.status_code}: {r.text[:150]}')

    content = b'MySolido regressietest roundtrip ' + secrets.token_hex(8).encode()
    r = upload(ctx, 'roundtrip.txt', content, ctx.ldp_rel)
    on_disk = ctx.ldp_dir / 'roundtrip.txt'
    rep.check('Flask: bestand uploaden', r.status_code in REDIRECT and on_disk.exists() and on_disk.read_bytes() == content,
              'roundtrip.txt', f'status {r.status_code}, op schijf: {on_disk.exists()}')
    r = css(ctx, 'GET', ctx.ldp_url + 'roundtrip.txt')
    rep.check('Roundtrip Flask -> CSS: upload via CSS leesbaar', r.status_code == 200 and r.content == content,
              f'status {r.status_code}', f'status {r.status_code}')
    ctype = r.headers.get('Content-Type', '')
    rep.check('CSS geeft text/plain voor .txt', ctype.startswith('text/plain'), ctype, ctype or '-')

    css_content = b'geschreven via CSS ' + secrets.token_hex(8).encode()
    r = css(ctx, 'PUT', ctx.ldp_url + 'van-css.txt', data=css_content, headers={'Content-Type': 'text/plain'})
    rep.check('CSS: PUT bestand', r.status_code in (201, 204, 205), f'status {r.status_code}',
              f'status {r.status_code}: {r.text[:150]}')
    van_css = ctx.ldp_dir / 'van-css.txt'
    rep.check('Roundtrip CSS -> Flask: PUT staat op schijf', van_css.exists() and van_css.read_bytes() == css_content,
              'van-css.txt', 'niet gevonden of inhoud afwijkend')
    r = flask(ctx, 'GET', f'/browse/{ctx.ldp_rel}')
    rep.check('Roundtrip CSS -> Flask: bestand in MySolido-listing', r.status_code == 200 and 'van-css.txt' in r.text,
              '', f'status {r.status_code}')

    r = css(ctx, 'DELETE', ctx.ldp_url + 'van-css.txt')
    rep.check('CSS: DELETE bestand', r.status_code in (200, 204, 205) and not van_css.exists(),
              f'status {r.status_code}', f'status {r.status_code}')

    r = flask(ctx, 'GET', f'/view/{ctx.ldp_rel}/roundtrip.txt')
    rep.check('Flask: bestand bekijken', r.status_code == 200 and r.content == content, '', f'status {r.status_code}')
    r = flask(ctx, 'GET', f'/download/{ctx.ldp_rel}/roundtrip.txt')
    rep.check('Flask: bestand downloaden',
              r.status_code == 200 and r.content == content and 'attachment' in r.headers.get('Content-Disposition', ''),
              '', f'status {r.status_code}')
    r = flask(ctx, 'GET', '/search', params={'q': 'roundtrip'})
    rep.check('Flask: zoeken vindt testbestand', r.status_code == 200 and 'roundtrip.txt' in r.text, '', f'status {r.status_code}')

    flask(ctx, 'POST', '/create-folder', data={'folder_path': ctx.ldp_rel, 'folder_name': 'sub'})
    upload(ctx, 'verplaats.txt', b'verplaats mij', ctx.ldp_rel)
    r = flask(ctx, 'POST', '/move', data={'resource_url': ctx.ldp_url + 'verplaats.txt',
                                         'target_folder': f'{ctx.ldp_rel}/sub', 'folder_path': ctx.ldp_rel})
    moved = ctx.ldp_dir / 'sub' / 'verplaats.txt'
    rep.check('Flask: bestand verplaatsen', moved.exists() and not (ctx.ldp_dir / 'verplaats.txt').exists(),
              'ldp/sub/verplaats.txt', f'status {r.status_code}')
    r = css(ctx, 'GET', ctx.ldp_url + 'sub/verplaats.txt')
    rep.check('CSS ziet verplaatst bestand op nieuwe plek', r.status_code == 200, f'status {r.status_code}', f'status {r.status_code}')

    upload(ctx, 'prullenbak.txt', b'naar de prullenbak')
    r = flask(ctx, 'POST', '/delete', data={'resource_url': ctx.test_url + 'prullenbak.txt', 'folder_path': TEST_FOLDER})
    entry = trash_entry(ctx, 'prullenbak.txt')
    in_trash = bool(entry) and trash_path(ctx, entry).exists()
    rep.check('Flask: verwijderen naar prullenbak', in_trash and not (ctx.test_dir / 'prullenbak.txt').exists(),
              '_trash/', f'status {r.status_code}, trash.json-entry: {bool(entry)}')
    if entry:
        flask(ctx, 'POST', '/trash/restore', data={'trash_id': entry['trash_id']})
        rep.check('Flask: herstellen uit prullenbak', (ctx.test_dir / 'prullenbak.txt').exists(),
                  'prullenbak.txt', 'bestand niet terug')
        flask(ctx, 'POST', '/delete', data={'resource_url': ctx.test_url + 'prullenbak.txt', 'folder_path': TEST_FOLDER})
        entry2 = trash_entry(ctx, 'prullenbak.txt')
        if entry2:
            flask(ctx, 'POST', '/trash/delete', data={'trash_id': entry2['trash_id']})
            rep.check('Flask: definitief verwijderen uit prullenbak', not trash_path(ctx, entry2).exists(),
                      '', 'bestand staat nog in _trash/')
        else:
            rep.fail('Flask: definitief verwijderen uit prullenbak', 'geen tweede trash-entry gevonden')
    return content


def phase_normalisation(ctx: Ctx):
    """Identifier normalisation cases inside the public ldp/ folder; mostly recorded as INFO."""
    rep = ctx.report
    listing = lambda: flask(ctx, 'GET', f'/browse/{ctx.ldp_rel}').text  # noqa: E731

    # 1. file name with spaces and capitals, uploaded through Flask (Flask keeps the name as-is)
    name = 'Bestand Met Spatie.txt'
    upload(ctx, name, b'spatie', ctx.ldp_rel)
    r_enc = css(ctx, 'GET', ctx.ldp_url + 'Bestand%20Met%20Spatie.txt')
    r_raw = css(ctx, 'GET', ctx.ldp_url + name)
    html = listing()
    rep.info('Normalisatie: upload "Bestand Met Spatie.txt" via Flask',
             f'op schijf {disk_names(ctx.ldp_dir, "Bestand")}; CSS GET %20-gecodeerd {r_enc.status_code}, '
             f'ongecodeerd {r_raw.status_code}; listing toont naam: {name in html}; '
             f'listing-URL gecodeerd: {"Bestand%20Met" in html}')
    r = flask(ctx, 'GET', f'/view/{ctx.ldp_rel}/Bestand%20Met%20Spatie.txt')
    rep.check('Normalisatie: Flask opent bestand met spatie', r.status_code == 200 and r.content == b'spatie',
              '', f'status {r.status_code}')

    # 2. folder with a space: Flask normalises, CSS accepts a percent-encoded container name
    r = flask(ctx, 'POST', '/create-folder', data={'folder_path': ctx.ldp_rel, 'folder_name': 'Map Met Spatie'})
    rep.info('Normalisatie: Flask-map "Map Met Spatie"', f'op schijf {disk_names(ctx.ldp_dir, "map")}')
    r = css(ctx, 'PUT', ctx.ldp_url + 'map%20via%20css/', headers={'Content-Type': 'text/turtle',
                                                                    'Link': '<http://www.w3.org/ns/ldp#BasicContainer>; rel="type"'}, data='')
    r2 = css(ctx, 'GET', ctx.ldp_url + 'map%20via%20css/', headers={'Accept': 'text/turtle'})
    html = listing()
    rep.info('Normalisatie: CSS PUT container "map%20via%20css/"',
             f'PUT {r.status_code}, GET {r2.status_code}; op schijf {disk_names(ctx.ldp_dir, "map via")}; '
             f'listing toont "map via css": {"map via css" in html}')
    upload(ctx, 'in-spatiemap.txt', b'x', f'{ctx.ldp_rel}/map via css')
    r = css(ctx, 'GET', ctx.ldp_url + 'map%20via%20css/in-spatiemap.txt')
    rep.info('Normalisatie: upload via Flask in map met spatie, GET via CSS', f'status {r.status_code}')

    # 3. double extensions and content-type mismatch (the $.ext convention of the file backend)
    upload(ctx, 'notities.backup.txt', b'dubbele extensie', ctx.ldp_rel)
    r = css(ctx, 'GET', ctx.ldp_url + 'notities.backup.txt')
    rep.check('Normalisatie: dubbele extensie via Flask, CSS leest als text/plain',
              r.status_code == 200 and r.headers.get('Content-Type', '').startswith('text/plain'),
              r.headers.get('Content-Type', ''), f'status {r.status_code}, {r.headers.get("Content-Type")}')
    cases = [('rapport.pdf.txt', 'text/plain'), ('data.txt.json', 'application/json'), ('mismatch.txt', 'application/json')]
    for fname, ctype in cases:
        r = css(ctx, 'PUT', ctx.ldp_url + fname, data=b'{}', headers={'Content-Type': ctype})
        r2 = css(ctx, 'GET', ctx.ldp_url + fname)
        stem = fname.split('.')[0]
        html = listing()
        shown = [n for n in disk_names(ctx.ldp_dir, stem) if n in html]
        rep.info(f'Normalisatie: CSS PUT "{fname}" als {ctype}',
                 f'PUT {r.status_code}; op schijf {disk_names(ctx.ldp_dir, stem)}; GET {r2.status_code} '
                 f'{r2.headers.get("Content-Type", "-")}; listing toont {shown or "niets"}')

    # 4. capitals: Windows file systems are case-insensitive, CSS identifiers are not
    upload(ctx, 'HoofdLetters.TXT', b'HOOFD', ctx.ldp_rel)
    r_exact = css(ctx, 'GET', ctx.ldp_url + 'HoofdLetters.TXT')
    r_lower = css(ctx, 'GET', ctx.ldp_url + 'hoofdletters.txt')
    rep.info('Normalisatie: "HoofdLetters.TXT" via Flask',
             f'op schijf {disk_names(ctx.ldp_dir, "hoofd")}; CSS GET exact {r_exact.status_code} '
             f'{r_exact.headers.get("Content-Type", "-")}; GET kleine letters {r_lower.status_code}')
    r = css(ctx, 'PUT', ctx.ldp_url + 'UPPER.txt', data=b'upper', headers={'Content-Type': 'text/plain'})
    html = listing()
    rep.info('Normalisatie: CSS PUT "UPPER.txt"', f'PUT {r.status_code}; op schijf {disk_names(ctx.ldp_dir, "upper")}; listing toont UPPER.txt: {"UPPER.txt" in html}')

    # 5. resource without extension and double slashes
    r = css(ctx, 'PUT', ctx.ldp_url + 'zonder-extensie', data=b'zonder extensie', headers={'Content-Type': 'text/plain'})
    html = listing()
    names = disk_names(ctx.ldp_dir, 'zonder-extensie')
    r2 = css(ctx, 'GET', ctx.ldp_url + 'zonder-extensie')
    rep.info('Normalisatie: CSS PUT "zonder-extensie" als text/plain',
             f'PUT {r.status_code}; op schijf {names}; GET {r2.status_code} {r2.headers.get("Content-Type", "-")}; '
             f'listing toont {[n for n in names if n in html] or "niets"}')
    r = css(ctx, 'GET', f'{ctx.ldp_url}/roundtrip.txt')
    rep.info('Normalisatie: GET met dubbele slash .../ldp//roundtrip.txt', f'status {r.status_code}')
    r = css(ctx, 'PUT', f'{ctx.ldp_url}/dubbel.txt', data=b'dubbel', headers={'Content-Type': 'text/plain'})
    landed = [str(p.relative_to(ctx.pod_dir)) for p in ctx.pod_dir.rglob('dubbel*')]
    rep.info('Normalisatie: PUT met dubbele slash .../ldp//dubbel.txt',
             f'status {r.status_code}, Location {r.headers.get("Location", "-")}, op schijf: {landed or "nergens"}')
    r = css(ctx, 'PUT', f'{ctx.pod_url}/{TEST_FOLDER}/{LDP_FOLDER}/dubbel-root.txt', data=b'dubbel', headers={'Content-Type': 'text/plain'})
    landed = [str(p.relative_to(ctx.pod_dir)) for p in ctx.pod_dir.rglob('dubbel-root*')]
    rep.info('Normalisatie: PUT met dubbele slash na Pod-root .../mysolido//regressietest/...',
             f'status {r.status_code}, op schijf: {landed or "nergens"}')


def phase_wac(ctx: Ctx, account):
    rep = ctx.report
    res_rel = f'{TEST_FOLDER}/wac-test.txt'
    res_url = ctx.test_url + 'wac-test.txt'
    acl_file = ctx.test_dir / 'wac-test.txt.acl'
    upload(ctx, 'wac-test.txt', b'WAC test')

    r = css(ctx, 'GET', res_url)
    rep.check('WAC: bestand zonder eigen ACL is niet publiek', r.status_code == 401, f'status {r.status_code}', f'status {r.status_code}')
    share(ctx, res_url, res_rel, TEST_FOLDER, '', 'public')
    rep.check('WAC: Flask schrijft .acl met publieke leesregel',
              acl_file.exists() and 'foaf:Agent' in acl_file.read_text(encoding='utf-8'),
              'wac-test.txt.acl', 'geen .acl of geen foaf:Agent')
    r = css(ctx, 'GET', res_url)
    rep.check('WAC: CSS past de ACL toe (publiek lezen = 200)', r.status_code == 200, f'status {r.status_code}', f'status {r.status_code}')
    r = css(ctx, 'PUT', res_url, data=b'x', headers={'Content-Type': 'text/plain'})
    rep.check('WAC: publiek schrijven blijft geweigerd', r.status_code in (401, 403), f'status {r.status_code}', f'status {r.status_code}')
    revoke(ctx, res_url, res_rel, 'public')
    rep.check('WAC: intrekken verwijdert .acl', not acl_file.exists(), '', '.acl bestaat nog')
    r = css(ctx, 'GET', res_url)
    rep.check('WAC: na intrekken weer 401', r.status_code == 401, f'status {r.status_code}', f'status {r.status_code}')

    if account:
        share(ctx, res_url, res_rel, TEST_FOLDER, account['webid'], 'read')
        acl_text = acl_file.read_text(encoding='utf-8') if acl_file.exists() else ''
        r_anon = css(ctx, 'GET', res_url)
        rep.check('WAC: delen met specifieke WebID schrijft acl:agent-regel, anoniem blijft 401',
                  f'acl:agent <{account["webid"]}>' in acl_text and r_anon.status_code == 401,
                  '', f'anoniem {r_anon.status_code}, acl bevat WebID: {account["webid"] in acl_text}')
        if account.get('token'):
            r = css(ctx, 'GET', res_url, token=account['token'])
            rep.skip('WAC: positieve toegang met het WebID-token',
                     f'status {r.status_code}; client-credentials-tokens authenticeren niet op http (verifier eist https)')
        revoke(ctx, res_url, res_rel, account['webid'])
        rep.check('WAC: intrekken WebID-share verwijdert .acl', not acl_file.exists(), '', '.acl bestaat nog')
    else:
        rep.skip('WAC: delen met specifieke WebID', 'geen testaccount beschikbaar')


def phase_share_link(ctx: Ctx):
    rep = ctx.report
    content = b'gedeeld via deellink ' + secrets.token_hex(4).encode()
    upload(ctx, 'deellink.txt', content)
    password = 'Regressie-Test-' + secrets.token_hex(3)
    r = flask(ctx, 'POST', '/share-link/create', data={'file_path': f'{TEST_FOLDER}/deellink.txt',
                                                       'file_name': 'deellink.txt', 'expires_days': '1',
                                                       'password': password})
    link = newest_share_link(ctx, f'{TEST_FOLDER}/deellink.txt')
    rep.check('Deellink: aanmaken met wachtwoord', r.status_code in REDIRECT and link is not None,
              '', f'status {r.status_code}, link gevonden: {link is not None}')
    if link:
        anon = requests.Session()
        url = f'{ctx.flask_base}/share/{link["token"]}'
        r = anon.get(url, timeout=TIMEOUT)
        rep.check('Deellink: wachtwoordpagina getoond', r.status_code == 200 and 'name="password"' in r.text,
                  '', f'status {r.status_code}')
        r = anon.post(url, data={'password': 'fout-wachtwoord'}, timeout=TIMEOUT)
        rep.check('Deellink: fout wachtwoord geeft geen bestand', r.content != content, '', 'bestand geleverd')
        r = anon.post(url, data={'password': password}, timeout=TIMEOUT)
        rep.check('Deellink: juist wachtwoord levert bestand', r.status_code == 200 and r.content == content,
                  '', f'status {r.status_code}')
        flask(ctx, 'POST', '/share-link/revoke', data={'link_id': link['id']})
        r = anon.get(url, timeout=TIMEOUT)
        rep.check('Deellink: na intrekken 404', r.status_code == 404, f'status {r.status_code}', f'status {r.status_code}')
    register = f'{ctx.pod_url}.mysolido/share_links.json'
    r = css(ctx, 'GET', register)
    rep.check('Deellink-register niet publiek via CSS', r.status_code in (401, 403, 404),
              f'status {r.status_code}', f'status {r.status_code}')


def phase_policy(ctx: Ctx):
    rep = ctx.report
    r = flask(ctx, 'POST', f'/policy/{ctx.ldp_rel}', data={'rule': 'read-no-download'})
    policy_file = ctx.ldp_dir / '.policy.jsonld'
    policy = json.loads(policy_file.read_text(encoding='utf-8')) if policy_file.exists() else {}
    rep.check('ODRL: policy weggeschreven als .policy.jsonld',
              policy.get('@type') == 'Set' and policy.get('uid') == f'urn:mysolido:policy:{LDP_FOLDER}',
              '', f'status {r.status_code}, bestand: {policy_file.exists()}')
    anyone_read = any(p.get('assignee') == 'urn:mysolido:anyone' and 'read' in actions(p.get('action'))
                      for p in policy.get('permission', []))
    distribute = any('distribute' in actions(p.get('action')) for p in policy.get('prohibition', []))
    rep.check('ODRL: regel "lezen, niet downloaden" correct opgebouwd', anyone_read and distribute,
              '', f'anyone_read={anyone_read}, distribute={distribute}')
    r = flask(ctx, 'GET', f'/policy/{ctx.ldp_rel}')
    rep.check('ODRL: policy teruggelezen in Flask', r.status_code == 200 and 'value="read-no-download" selected' in r.text,
              '', f'status {r.status_code}')
    r = flask(ctx, 'GET', f'/browse/{ctx.ldp_rel}')
    rep.check('ODRL: .policy.jsonld verborgen in MySolido-listing', '.policy.jsonld' not in r.text, '', 'zichtbaar in listing')
    r = css(ctx, 'GET', ctx.ldp_url + '.policy.jsonld')
    rep.info('ODRL: .policy.jsonld via CSS opvraagbaar', f'status {r.status_code}, Content-Type {r.headers.get("Content-Type")}')
    r = css(ctx, 'GET', ctx.ldp_url, headers={'Accept': 'text/turtle'})
    rep.info('ODRL: .policy.jsonld in ldp:contains van CSS', 'ja' if '.policy.jsonld' in r.text else 'nee')


def phase_consent_request(ctx: Ctx):
    rep = ctx.report
    cdir = ctx.pod_dir / 'toestemmingen'
    before = {p.name for p in cdir.glob('*.jsonld')} if cdir.exists() else set()
    title = 'Regressietest toestemming ' + secrets.token_hex(3)
    r = flask(ctx, 'POST', '/consent/new', data={'title': title, 'description': 'Synthetische testdata',
                                                 'receiver': 'Testorganisatie BV', 'purpose': 'other',
                                                 'category': 'other', 'expires': '', 'note': ''})
    new = [p for p in cdir.glob('*.jsonld') if p.name not in before] if cdir.exists() else []
    rep.check('Toestemming: record weggeschreven', len(new) == 1, '', f'status {r.status_code}, nieuwe bestanden: {len(new)}')
    if new:
        record_file = new[0]
        cid = record_file.stem
        rec = json.loads(record_file.read_text(encoding='utf-8'))
        rep.check('Toestemming: JSON-LD velden correct',
                  rec.get('@type') == 'dpv:ConsentRecord' and rec.get('dct:title') == title
                  and rec.get('dpv:hasConsentStatus') == 'dpv:ConsentGiven',
                  cid, json.dumps(rec)[:200])
        r = flask(ctx, 'GET', f'/consent/{cid}')
        rep.check('Toestemming: detailpagina leest record terug', r.status_code == 200 and title in r.text,
                  '', f'status {r.status_code}')
        r = css(ctx, 'GET', f'{ctx.pod_url}toestemmingen/{cid}.jsonld')
        rep.check('Toestemming: record niet publiek via CSS', r.status_code == 401, f'status {r.status_code}', f'status {r.status_code}')
        copy = ctx.ldp_dir / 'consent-copy.jsonld'
        shutil.copyfile(record_file, copy)
        r = css(ctx, 'GET', ctx.ldp_url + 'consent-copy.jsonld')
        rep.check('Toestemming: CSS serveert .jsonld als application/ld+json',
                  r.status_code == 200 and 'ld+json' in r.headers.get('Content-Type', '') and r.json().get('dct:title') == title,
                  r.headers.get('Content-Type', ''), f'status {r.status_code}, {r.headers.get("Content-Type")}')
        copy.unlink()
        flask(ctx, 'POST', f'/consent/{cid}/withdraw')
        rec = json.loads(record_file.read_text(encoding='utf-8'))
        rep.check('Toestemming: intrekken zet status dpv:ConsentWithdrawn',
                  rec.get('dpv:hasConsentStatus') == 'dpv:ConsentWithdrawn', '', rec.get('dpv:hasConsentStatus'))
        flask(ctx, 'POST', f'/consent/{cid}/delete')
        rep.check('Toestemming: verwijderen', not record_file.exists(), '', 'bestand bestaat nog')

    vdir = ctx.pod_dir / 'verzoeken'
    before_v = {p.name for p in vdir.glob('*.jsonld')} if vdir.exists() else set()
    anon = requests.Session()
    r = anon.post(f'{ctx.flask_base}/verzoek',
                  data={'name': 'Test Aanvrager', 'organization': 'Testorganisatie BV',
                        'email': 'aanvrager@example.test', 'category': 'anders',
                        'purpose': 'Regressietest van MySolido', 'requested_data': ['naam'],
                        'agreed_terms': 'yes'},
                  timeout=TIMEOUT, allow_redirects=False)
    new_v = [p for p in vdir.glob('*.jsonld') if p.name not in before_v and not p.name.startswith('.')] if vdir.exists() else []
    rep.check('Consentrequest: verzoek via publiek formulier weggeschreven', r.status_code == 200 and len(new_v) == 1,
              '', f'status {r.status_code}, nieuwe bestanden: {len(new_v)}')
    if new_v:
        request_file = new_v[0]
        rid = request_file.stem
        rec = json.loads(request_file.read_text(encoding='utf-8'))
        token = rec.get('mysolido:statusToken', '')
        rep.check('Consentrequest: JSON-LD velden correct en statustoken in bevestiging',
                  rec.get('@type') == 'mysolido:ConsentRequest' and rec.get('mysolido:status') == 'nieuw'
                  and bool(token) and token in r.text,
                  rid, json.dumps(rec)[:200])
        rep.check('Consentrequest: policy voor verzoeken/ aangemaakt', (vdir / '.policy.jsonld').exists(),
                  '', '.policy.jsonld ontbreekt')
        r = anon.get(f'{ctx.flask_base}/verzoek/status/{token}', timeout=TIMEOUT)
        rep.check('Consentrequest: publieke statuspagina teruglezen', r.status_code == 200, '', f'status {r.status_code}')
        r = flask(ctx, 'GET', f'/verzoeken/{rid}')
        rep.check('Consentrequest: eigenaar ziet verzoek', r.status_code == 200 and 'Test Aanvrager' in r.text,
                  '', f'status {r.status_code}')
        flask(ctx, 'POST', f'/verzoeken/{rid}/reject', data={'reason': 'Regressietest'})
        rec = json.loads(request_file.read_text(encoding='utf-8'))
        rep.check('Consentrequest: afwijzen zet status afgewezen',
                  rec.get('mysolido:status') == 'afgewezen' and rec.get('mysolido:rejectionReason') == 'Regressietest',
                  '', rec.get('mysolido:status'))
        r = anon.get(f'{ctx.flask_base}/verzoek/status/{token}', timeout=TIMEOUT)
        rep.check('Consentrequest: statuspagina toont afgewezen', r.status_code == 200 and 'badge-afgewezen' in r.text,
                  '', f'status {r.status_code}')
        request_file.unlink()
        rep.ok('Consentrequest: testverzoek opgeruimd')


def phase_backup_restore(ctx: Ctx, content):
    rep = ctx.report
    r = flask(ctx, 'POST', '/settings/export')
    ok = r.status_code == 200 and r.headers.get('Content-Type', '').startswith('application/zip')
    rep.check('Backup: zip-export', ok, f'{len(r.content)} bytes', f'status {r.status_code}')
    if not ok:
        return
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    names = zf.namelist()
    target = f'{ctx.ldp_rel}/roundtrip.txt'
    rep.check('Backup: bevat testbestand met juiste inhoud',
              target in names and (content is None or zf.read(target) == content),
              target, f'{len(names)} bestanden, testbestand ontbreekt of afwijkend')
    dot_included = any(n.endswith('.policy.jsonld') or n.endswith('.acl') for n in names)
    rep.info('Backup: .policy.jsonld en .acl in zip', 'ja' if dot_included else 'nee, dotfiles en .acl worden overgeslagen')
    rep.info('Backup: .mysolido/share_links.json in zip', 'ja' if any('share_links.json' in n for n in names) else 'nee')
    if target not in names:
        return
    original = ctx.ldp_dir / 'roundtrip.txt'
    original.unlink()
    r = css(ctx, 'GET', ctx.ldp_url + 'roundtrip.txt')
    gone = r.status_code == 404
    with zf.open(target) as src, open(original, 'wb') as dst:
        shutil.copyfileobj(src, dst)
    r = css(ctx, 'GET', ctx.ldp_url + 'roundtrip.txt')
    rep.check('Restore: bestand uit zip teruggezet en via CSS leesbaar',
              gone and r.status_code == 200 and (content is None or r.content == content),
              '', f'na verwijderen 404: {gone}, na terugzetten status {r.status_code}')


def phase_debug(ctx: Ctx):
    r = flask(ctx, 'GET', '/debug')
    ctx.report.check('Flask /debug: HTTP-lezing van Pod-root via CSS (root is publiek)',
                     r.status_code == 200 and 'ldp:contains' in r.text and TEST_FOLDER in r.text,
                     '', f'status {r.status_code}: {r.text[:150]}')


def phase_probes(ctx: Ctx):
    """Behaviour probes for the 7.2.0 changelog items; recorded as INFO for comparison."""
    rep = ctx.report
    locations = []
    for _ in range(2):
        r = css(ctx, 'POST', ctx.ldp_url, data=b'slug', headers={'Content-Type': 'text/plain', 'Slug': 'slug-test.txt'})
        locations.append(f'{r.status_code} {r.headers.get("Location", "-")}')
    rep.info('Probe dubbele slug: twee POSTs met Slug slug-test.txt',
             f'{" | ".join(locations)}; op schijf {disk_names(ctx.ldp_dir, "slug-test")}')
    r = css(ctx, 'HEAD', ctx.pod_url)
    link = r.headers.get('Link', '')
    rep.info('Probe Link-header op Pod-root', link[:300] or '-')
    m = re.search(r'<([^>]+)>;\s*rel="http://www\.w3\.org/ns/solid/terms#storageDescription"', link)
    if m:
        r = css(ctx, 'GET', m.group(1), headers={'Accept': 'text/turtle'})
        rep.info('Probe storage description', f'{m.group(1)} -> status {r.status_code}')
    else:
        rep.info('Probe storage description', 'geen storageDescription-link op Pod-root')
    r = css(ctx, 'GET', f'{ctx.css_base}/.notifications/', headers={'Accept': 'application/ld+json'})
    rep.info('Probe notificaties: GET /.notifications/', f'status {r.status_code}')
    r = css(ctx, 'GET', f'{ctx.css_base}/.notifications/WebhookChannel2023/', headers={'Accept': 'application/ld+json'})
    rep.info('Probe webhook-kanaal: GET /.notifications/WebhookChannel2023/', f'status {r.status_code}')


def phase_bridge_sync(ctx: Ctx):
    rep = ctx.report
    cwd = os.getcwd()
    try:
        os.chdir(ROOT)
        sys.path.insert(0, str(ROOT))
        import sync_bridge  # noqa: PLC0415 - imported here on purpose, needs cwd = project root
        path = sync_bridge.get_pod_data_path()
        rep.check('Bridge-sync: module vindt de Pod-map',
                  path is not None and Path(path).resolve() == ctx.pod_dir.resolve(),
                  str(path), f'{path!r}, verwacht {ctx.pod_dir}')
        rep.check('Bridge-sync: testmap valt binnen de sync-bron',
                  path is not None and (Path(path) / TEST_FOLDER).is_dir(), TEST_FOLDER, 'niet gevonden')
        rep.info('Bridge-sync: is_configured()', str(sync_bridge.is_configured()))
        rep.skip('Bridge-sync: daadwerkelijke scp naar de Bridge-VPS', 'extern systeem, bewust niet aangeraakt')
    finally:
        os.chdir(cwd)


def phase_persist_setup(ctx: Ctx):
    """Create the two sub-folders whose ACL and policy must survive a server restart or upgrade."""
    rep = ctx.report
    acl_url = f'{ctx.test_url}{ACL_FOLDER}/'
    acl_rel = f'{TEST_FOLDER}/{ACL_FOLDER}'
    flask(ctx, 'POST', '/create-folder', data={'folder_path': TEST_FOLDER, 'folder_name': ACL_FOLDER})
    upload(ctx, 'open.txt', b'openbaar leesbaar', acl_rel)
    share(ctx, acl_url, acl_rel + '/', TEST_FOLDER, '', 'public')
    acl_file = ctx.test_dir / ACL_FOLDER / '.acl'
    rep.check('Persistentie: submap met eigen .acl (publiek lezen) aangemaakt',
              acl_file.exists() and 'foaf:Agent' in acl_file.read_text(encoding='utf-8'), acl_rel, 'geen .acl')
    r = css(ctx, 'GET', acl_url + 'open.txt')
    rep.check('Persistentie: CSS volgt de .acl (anoniem 200)', r.status_code == 200, f'status {r.status_code}', f'status {r.status_code}')

    policy_rel = f'{TEST_FOLDER}/{POLICY_FOLDER}'
    flask(ctx, 'POST', '/create-folder', data={'folder_path': TEST_FOLDER, 'folder_name': POLICY_FOLDER})
    flask(ctx, 'POST', f'/policy/{policy_rel}', data={'rule': 'read'})
    policy_file = ctx.test_dir / POLICY_FOLDER / '.policy.jsonld'
    rep.check('Persistentie: submap met .policy.jsonld (regel "read") aangemaakt', policy_file.exists(), policy_rel, 'geen .policy.jsonld')
    r = css(ctx, 'GET', f'{ctx.test_url}{POLICY_FOLDER}/')
    rep.check('Persistentie: policy-map zonder .acl blijft eigenaar-only (anoniem 401)', r.status_code == 401,
              f'status {r.status_code}', f'status {r.status_code}')


def phase_persist_check(ctx: Ctx, keep: bool):
    """After a restart or upgrade: are the ACL and the policy from the previous run still honoured?"""
    rep = ctx.report
    acl_url = f'{ctx.test_url}{ACL_FOLDER}/'
    acl_rel = f'{TEST_FOLDER}/{ACL_FOLDER}'
    policy_rel = f'{TEST_FOLDER}/{POLICY_FOLDER}'
    rep.info('CSS-versie volgens .data/.internal/setup', css_version())
    acl_file = ctx.test_dir / ACL_FOLDER / '.acl'
    rep.check('Persistentie: .acl van vorige run nog op schijf', acl_file.exists(), acl_rel, 'ontbreekt')
    r = css(ctx, 'GET', acl_url + 'open.txt')
    rep.check('Persistentie: CSS leest de .acl na herstart (anoniem 200)', r.status_code == 200, f'status {r.status_code}', f'status {r.status_code}')
    r = css(ctx, 'PUT', acl_url + 'open.txt', data=b'x', headers={'Content-Type': 'text/plain'})
    rep.check('Persistentie: schrijven blijft geweigerd (alleen lezen gedeeld)', r.status_code in (401, 403), f'status {r.status_code}', f'status {r.status_code}')
    r = css(ctx, 'GET', f'{ctx.test_url}{POLICY_FOLDER}/')
    rep.check('Persistentie: policy-map blijft eigenaar-only (anoniem 401)', r.status_code == 401, f'status {r.status_code}', f'status {r.status_code}')
    r = css(ctx, 'GET', ctx.test_url)
    rep.check('Persistentie: testmap zelf blijft eigenaar-only (anoniem 401)', r.status_code == 401, f'status {r.status_code}', f'status {r.status_code}')
    r = flask(ctx, 'GET', f'/policy/{policy_rel}')
    rep.check('Persistentie: Flask leest de .policy.jsonld na herstart', r.status_code == 200 and 'value="read" selected' in r.text,
              '', f'status {r.status_code}')
    r = flask(ctx, 'GET', f'/browse/{acl_rel}')
    rep.check('Persistentie: Flask toont de acl-map na herstart', r.status_code == 200 and 'open.txt' in r.text, '', f'status {r.status_code}')
    if keep:
        rep.skip('Persistentie: opruimen', '--keep-persist opgegeven, mappen blijven staan')
        return
    revoke(ctx, acl_url, acl_rel + '/', 'public')
    rep.check('Persistentie: publieke share ingetrokken', not acl_file.exists(), '', '.acl bestaat nog')
    r = flask(ctx, 'POST', '/delete', data={'resource_url': ctx.test_url, 'folder_path': ''})
    rep.check('Persistentie: testmap verwijderd', r.status_code in REDIRECT and not ctx.test_dir.exists(), TEST_FOLDER,
              f'status {r.status_code}, bestaat nog: {ctx.test_dir.exists()}')


def phase_cleanup(ctx: Ctx, account, keep_persist: bool):
    rep = ctx.report
    revoke(ctx, ctx.ldp_url, ctx.ldp_rel + '/', 'public')
    rep.check('Opruimen: publieke share op submap ingetrokken', not (ctx.ldp_dir / '.acl').exists(), '', 'ldp/.acl bestaat nog')
    if keep_persist:
        r = flask(ctx, 'POST', '/delete', data={'resource_url': ctx.ldp_url, 'folder_path': TEST_FOLDER})
        rep.check('Opruimen: ldp-submap verwijderd via Flask', r.status_code in REDIRECT and not ctx.ldp_dir.exists(),
                  ctx.ldp_rel, f'status {r.status_code}')
        for p in ctx.test_dir.iterdir():
            if p.is_file():
                p.unlink()
        rep.info('Opruimen: acl-map en policy-map blijven staan voor --phase persist',
                 ', '.join(sorted(p.name for p in ctx.test_dir.iterdir())))
    else:
        r = flask(ctx, 'POST', '/delete', data={'resource_url': ctx.test_url, 'folder_path': ''})
        rep.check('Opruimen: testmap verwijderd via Flask', r.status_code in REDIRECT and not ctx.test_dir.exists(),
                  TEST_FOLDER, f'status {r.status_code}, bestaat nog: {ctx.test_dir.exists()}')
        if ctx.test_dir.exists():
            shutil.rmtree(ctx.test_dir, ignore_errors=True)
    r = css(ctx, 'GET', ctx.ldp_url, headers={'Accept': 'text/turtle'})
    rep.check('Opruimen: CSS geeft verwijderde submap niet meer terug', r.status_code in (401, 404),
              f'status {r.status_code}', f'status {r.status_code}')
    if ctx.seeded:
        rep.info('Opruimen: demodata van seed_demo.py (standaardmappen, profiel/, voorbeeldbestanden) blijft staan',
                 'bedoeld als demostand; verwijder handmatig als dat niet gewenst is')
    for name in ('_trash', 'toestemmingen', 'verzoeken', 'intenties', '.mysolido'):
        path = ctx.pod_dir / name
        if ctx.pre_existing[name] or not path.exists():
            continue
        leftovers = [x for x in path.rglob('*') if x.is_file() and x.name not in ('.policy.jsonld', 'share_links.json')]
        if leftovers:
            rep.info(f'Opruimen: {name}/ bevat nog bestanden en blijft staan', ', '.join(x.name for x in leftovers)[:200])
        else:
            shutil.rmtree(path, ignore_errors=True)
            rep.ok(f'Opruimen: {name}/ verwijderd (bestond niet voor de test)')
    if account:
        acc_url = account['controls'].get('account', {}).get('account')
        if acc_url:
            r = requests.delete(acc_url, headers={'Authorization': f'CSS-Account-Token {account["authorization"]}'},
                                timeout=TIMEOUT)
            rep.info('Opruimen: testaccount verwijderen via account-API', f'status {r.status_code}')
        else:
            rep.info('Opruimen: testaccount verwijderen via account-API', 'geen account-URL in controls')
        if account['pod_dir'].exists():
            shutil.rmtree(account['pod_dir'], ignore_errors=True)
            rep.ok('Opruimen: test-Pod-map van schijf verwijderd', str(account['pod_dir']))
    rep.info('Opruimen: runtime-bestanden in projectmap (trash.json, shares.json, audit_log.json, notifications.json)',
             'blijven staan, vallen onder .gitignore')


def phase_bridge_mode(ctx: Ctx, password: str):
    """Checks against Flask running with --bridge (read-only mode). No CSS involved."""
    rep = ctx.report
    anon = requests.Session()
    r = anon.get(f'{ctx.flask_base}/', timeout=TIMEOUT, allow_redirects=False)
    rep.check('Bridge: onaangemelde bezoeker gaat naar login', r.status_code in REDIRECT and 'bridge-login' in r.headers.get('Location', ''),
              '', f'status {r.status_code}, Location {r.headers.get("Location")}')
    r = anon.post(f'{ctx.flask_base}/bridge-login', data={'password': 'fout-wachtwoord'}, timeout=TIMEOUT, allow_redirects=False)
    rep.check('Bridge: fout wachtwoord geweigerd', r.status_code == 200 and 'name="password"' in r.text, '', f'status {r.status_code}')
    r = anon.post(f'{ctx.flask_base}/bridge-login', data={'password': password}, timeout=TIMEOUT, allow_redirects=False)
    rep.check('Bridge: inloggen met Bridge-wachtwoord', r.status_code in REDIRECT, '', f'status {r.status_code}')
    ctx.test_dir.mkdir(parents=True, exist_ok=True)
    (ctx.test_dir / 'bridge-check.txt').write_bytes(b'bridge')
    try:
        r = anon.get(f'{ctx.flask_base}/browse/{TEST_FOLDER}', timeout=TIMEOUT)
        rep.check('Bridge: leest de gesynchroniseerde Pod-map', r.status_code == 200 and 'bridge-check.txt' in r.text,
                  '', f'status {r.status_code}')
        r = anon.post(f'{ctx.flask_base}/upload', data={'upload_folder': TEST_FOLDER},
                      files={'file': ('blokkeer.txt', b'x', 'text/plain')}, timeout=TIMEOUT, allow_redirects=False)
        rep.check('Bridge: uploaden geblokkeerd (read-only)',
                  r.status_code in REDIRECT and not (ctx.test_dir / 'blokkeer.txt').exists(),
                  '', f'status {r.status_code}, bestand aangemaakt: {(ctx.test_dir / "blokkeer.txt").exists()}')
        r = requests.get(f'{ctx.flask_base}/verzoek', timeout=TIMEOUT, allow_redirects=False)
        rep.check('Bridge: publiek verzoekformulier zonder login bereikbaar', r.status_code == 200, '', f'status {r.status_code}')
        r = requests.get(f'{ctx.flask_base}/browse/{TEST_FOLDER}', timeout=TIMEOUT, allow_redirects=False)
        rep.check('Bridge: Pod-inhoud zonder login niet bereikbaar', r.status_code in REDIRECT, '', f'status {r.status_code}')
    finally:
        (ctx.test_dir / 'bridge-check.txt').unlink(missing_ok=True)
        if not any(ctx.test_dir.iterdir()):
            ctx.test_dir.rmdir()


# --- demodata, profielvelden en intentie (MyTerms-demo, subtaak 2) --------------------------

def run_seed(force: bool = False):
    cmd = [sys.executable, str(SEED_SCRIPT)] + (['--force'] if force else [])
    return subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace',
                          cwd=ROOT, timeout=120)


def read_profile(ctx: Ctx) -> dict:
    f = ctx.pod_dir / 'profiel' / 'profiel.jsonld'
    return json.loads(f.read_text(encoding='utf-8')) if f.exists() else {}


def expected_scenario_values(profile: dict) -> dict:
    """De vier scenariowaarden zoals ze nu in profiel.jsonld staan (PROFILE_ATTRIBUTES.path)."""
    vehicles = profile.get('pd:Vehicle') or [{}]
    return {
        ATTR + 'age_category': profile.get('pd:AgeRange'),
        ATTR + 'postal_area': profile.get('pd:PostalCode'),
        ATTR + 'vehicle_type': (vehicles[0] or {}).get('type'),
        ATTR + 'claims_history': profile.get('mysolido:claimsHistory'),
    }


def phase_seed(ctx: Ctx):
    """scripts/seed_demo.py: lege Pod -> twintig mappen + demoprofiel; tweede run weigert."""
    rep = ctx.report
    profile_file = ctx.pod_dir / 'profiel' / 'profiel.jsonld'
    had_profile = profile_file.exists()
    if had_profile:
        rep.info('Seed: profiel/profiel.jsonld bestond al; seed niet met --force gedraaid', str(profile_file))
    else:
        r = run_seed()
        rep.check('Seed: lege Pod gevuld (exit 0)', r.returncode == 0, '', (r.stdout + r.stderr)[-300:])
        ctx.seeded = r.returncode == 0
    folders = [f for f in DEFAULT_FOLDERS_ALL if (ctx.pod_dir / f).is_dir()]
    if had_profile:
        rep.info('Seed: standaardmappen op schijf', f'{len(folders)} van {len(DEFAULT_FOLDERS_ALL)}')
    else:
        rep.check('Seed: twintig standaardmappen aanwezig', len(folders) == len(DEFAULT_FOLDERS_ALL),
                  '', f'{len(folders)} van {len(DEFAULT_FOLDERS_ALL)}: ontbreekt {sorted(set(DEFAULT_FOLDERS_ALL) - set(folders))}')
        present = [p for p in SEED_FILES if (ctx.pod_dir / p).is_file()]
        rep.check('Seed: voorbeeldbestanden in voertuigen/ en financieel/', len(present) == len(SEED_FILES),
                  '', f'aanwezig: {present}')
    rep.check('Seed: profiel/profiel.jsonld aanwezig', profile_file.exists(), '', 'ontbreekt')
    rep.check('Seed: profiel/.policy.jsonld aanwezig', (ctx.pod_dir / 'profiel' / '.policy.jsonld').exists(), '', 'ontbreekt')
    if ctx.seeded:
        values = expected_scenario_values(read_profile(ctx))
        rep.check('Seed: demoprofiel bevat de vier scenariowaarden',
                  values == {ATTR + 'age_category': '35-44', ATTR + 'postal_area': '5611',
                             ATTR + 'vehicle_type': 'auto',
                             ATTR + 'claims_history': {'claimFreeYears': 5, 'claimsLast3Years': False}},
                  '', json.dumps(values))
    r = run_seed()
    rep.check('Seed: tweede run zonder --force weigert (exit 1)',
              r.returncode == 1 and 'bestaat al' in (r.stdout + r.stderr),
              '', f'exit {r.returncode}: {(r.stdout + r.stderr)[-200:]}')
    rep.check('Seed: geweigerde run laat het profiel ongemoeid', profile_file.exists(), '', 'profiel verdwenen')


def phase_profile_fields(ctx: Ctx):
    """Nieuwe profielvelden (leeftijdscategorie, postcodegebied, schadeverleden) opslaan en teruglezen."""
    rep = ctx.report
    profile_file = ctx.pod_dir / 'profiel' / 'profiel.jsonld'
    original = profile_file.read_text(encoding='utf-8') if profile_file.exists() else None
    try:
        r = flask(ctx, 'POST', '/profiel-data', data={
            'age_category': '45-54', 'postal_area': '1234', 'region': 'Testregio',
            'vehicle_type': 'motor', 'vehicle_fuel': 'benzine', 'vehicle_year': '2015',
            'claim_free_years': '7', 'claims_last_3_years': 'ja'})
        rec = read_profile(ctx)
        rep.check('Profiel: opslaan schrijft pd:AgeRange, pd:PostalCode en mysolido:claimsHistory',
                  r.status_code in REDIRECT and rec.get('pd:AgeRange') == '45-54' and rec.get('pd:PostalCode') == '1234'
                  and rec.get('mysolido:claimsHistory') == {'claimFreeYears': 7, 'claimsLast3Years': True},
                  '', f'status {r.status_code}, record: {json.dumps(rec)[:300]}')
        rep.check('Profiel: bestaande velden blijven werken (pd:Vehicle, pd:Location)',
                  (rec.get('pd:Vehicle') or [{}])[0].get('type') == 'motor' and rec.get('pd:Location') == 'Testregio',
                  '', json.dumps(rec.get('pd:Vehicle')))
        r = flask(ctx, 'GET', '/profiel-data')
        rep.check('Profiel: formulier leest de drie velden terug',
                  r.status_code == 200 and 'value="45-54" selected' in r.text and 'value="1234"' in r.text
                  and 'name="claim_free_years"' in r.text and 'value="ja" selected' in r.text,
                  '', f'status {r.status_code}')
        r = flask(ctx, 'POST', '/profiel-data', data={'age_category': '45-54', 'postal_area': '12', 'vehicle_type': 'motor'})
        rec = read_profile(ctx)
        rep.check('Profiel: ongeldig postcodegebied wordt niet opgeslagen, de rest wel',
                  'pd:PostalCode' not in rec and rec.get('pd:AgeRange') == '45-54',
                  '', json.dumps(rec)[:200])
    finally:
        if original is not None:
            profile_file.write_text(original, encoding='utf-8')
            rep.ok('Profiel: oorspronkelijk profiel teruggezet')
        elif profile_file.exists():
            profile_file.unlink()
            rep.ok('Profiel: testprofiel verwijderd (er was geen profiel)')


def phase_intention(ctx: Ctx):
    """Intentie autoverzekering: vier attributen als snapshot, purpose, noOnwardTransfer, offerMode."""
    rep = ctx.report
    idir = ctx.pod_dir / 'intenties'
    profile_file = ctx.pod_dir / 'profiel' / 'profiel.jsonld'
    profile = read_profile(ctx)
    expected = expected_scenario_values(profile)
    if not all(expected.values()):
        rep.skip('Intentie: profiel mist scenariowaarden, fase overgeslagen', json.dumps(expected))
        return
    r = flask(ctx, 'GET', '/intenties/nieuw')
    rep.check('Intentie: formulier toont attributen per veld en de MyTerms-velden',
              r.status_code == 200 and 'name="attributes"' in r.text and 'value="claims_history"' in r.text
              and 'name="purpose"' in r.text and 'name="no_onward_transfer"' in r.text and 'name="offer_mode"' in r.text,
              '', f'status {r.status_code}')

    def new_files(before):
        # <uuid>.policy.jsonld is de Offer naast het record (subtaak 3), geen intentie
        return [p for p in idir.glob('*.jsonld') if p.name not in before and not p.name.startswith('.')
                and not p.name.endswith('.policy.jsonld')] if idir.exists() else []

    def listing():
        return {p.name for p in idir.glob('*.jsonld')} if idir.exists() else set()

    created = []
    try:
        before = listing()
        r = flask(ctx, 'POST', '/intenties/nieuw', data={
            'category': 'autoverzekering', 'description': 'Regressietest: ik zoek een autoverzekering',
            'validity': '2w', 'attributes': list(SCENARIO_ATTRIBUTES), 'purpose': 'quote_calculation',
            'no_onward_transfer': '1', 'offer_mode': 'open'})
        new = new_files(before)
        rep.check('Intentie: record weggeschreven', r.status_code in REDIRECT and len(new) == 1,
                  '', f'status {r.status_code}, nieuwe bestanden: {len(new)}')
        if not new:
            return
        created.append(new[0])
        iid = new[0].stem
        rec = json.loads(new[0].read_text(encoding='utf-8'))
        shared = rec.get('mysolido:sharedAttributes') or []
        got = {a.get('@id'): a.get('value') for a in shared}
        rep.check('Intentie: sharedAttributes bevat precies de vier attributen met de profielwaarden',
                  rec.get('@type') == 'mysolido:Intention' and got == expected,
                  '', f'verwacht {json.dumps(expected)}, gekregen {json.dumps(got)}')
        stamps = {a.get('capturedAt') for a in shared}
        rep.check('Intentie: elk attribuut heeft label, valueLabel en hetzelfde capturedAt',
                  len(stamps) == 1 and all(a.get('label') and a.get('valueLabel') for a in shared),
                  '', json.dumps(shared)[:300])
        purpose = rec.get('mysolido:purpose') or {}
        rep.check('Intentie: purpose quote_calculation (Offerteberekening, dpv:ServiceProvision)',
                  purpose.get('@id') == 'urn:mysolido:purpose:quote_calculation'
                  and purpose.get('label') == 'Offerteberekening' and purpose.get('dpv') == 'dpv:ServiceProvision',
                  '', json.dumps(purpose))
        rep.check('Intentie: noOnwardTransfer true, offerMode open, geen targetedParty',
                  rec.get('mysolido:noOnwardTransfer') is True and rec.get('mysolido:offerMode') == 'open'
                  and 'mysolido:targetedParty' not in rec, '', json.dumps(rec)[:300])
        rep.check('Intentie: geen mysolido:sharedProfileData meer in nieuwe records',
                  'mysolido:sharedProfileData' not in rec, '', 'veld aanwezig')
        try:
            created_at = datetime.fromisoformat(rec.get('schema:dateCreated'))
            valid = datetime.fromisoformat(rec.get('schema:validThrough'))
            rep.check('Intentie: geldigheid 2 weken = 14 dagen', (valid - created_at).days == 14, '', str(valid - created_at))
        except (TypeError, ValueError) as exc:
            rep.fail('Intentie: geldigheid 2 weken = 14 dagen', repr(exc))
        r = flask(ctx, 'GET', f'/intenties/{iid}')
        rep.check('Intentie: detailpagina toont snapshot met "Vastgelegd op" en de vier attribuut-urn\'s',
                  r.status_code == 200 and 'Vastgelegd op' in r.text
                  and all(f'data-attribute="{ATTR}{k}"' in r.text for k in SCENARIO_ATTRIBUTES)
                  and 'Offerteberekening' in r.text,
                  '', f'status {r.status_code}')
        # Snapshot boven verwijzing: profiel wijzigen mag de detailpagina niet veranderen
        original = profile_file.read_text(encoding='utf-8')
        try:
            changed = dict(profile)
            changed['pd:AgeRange'] = '65+' if profile.get('pd:AgeRange') != '65+' else '18-24'
            profile_file.write_text(json.dumps(changed, indent=2, ensure_ascii=False), encoding='utf-8')
            r = flask(ctx, 'GET', f'/intenties/{iid}')
            rep.check('Intentie: detailpagina toont het snapshot, niet het gewijzigde profiel',
                      r.status_code == 200 and profile['pd:AgeRange'] in r.text and changed['pd:AgeRange'] not in r.text,
                      '', f'status {r.status_code}')
        finally:
            profile_file.write_text(original, encoding='utf-8')

        # Gericht aanbod: naam verplicht, wordt opgeslagen als targetedParty
        before = listing()
        r = flask(ctx, 'POST', '/intenties/nieuw', data={
            'category': 'autoverzekering', 'description': 'Regressietest gericht zonder naam',
            'validity': '1w', 'attributes': ['vehicle_type'], 'offer_mode': 'targeted', 'targeted_party': ''})
        rep.check('Intentie: gericht aanbod zonder naam wordt geweigerd', r.status_code in REDIRECT and not new_files(before),
                  '', f'status {r.status_code}, nieuwe bestanden: {len(new_files(before))}')
        r = flask(ctx, 'POST', '/intenties/nieuw', data={
            'category': 'autoverzekering', 'description': 'Regressietest gericht aanbod',
            'validity': '1w', 'attributes': ['vehicle_type'], 'offer_mode': 'targeted',
            'targeted_party': 'Verzekeraar X'})
        new = new_files(before)
        if rep.check('Intentie: gericht aanbod weggeschreven', len(new) == 1, '', f'status {r.status_code}'):
            created.append(new[0])
            rec2 = json.loads(new[0].read_text(encoding='utf-8'))
            party = rec2.get('mysolido:targetedParty') or {}
            rep.check('Intentie: offerMode targeted met targetedParty (@id + name), noOnwardTransfer false zonder vinkje',
                      rec2.get('mysolido:offerMode') == 'targeted'
                      and party.get('name') == 'Verzekeraar X' and str(party.get('@id', '')).startswith('urn:mysolido:party:')
                      and rec2.get('mysolido:noOnwardTransfer') is False
                      and [a['@id'] for a in rec2.get('mysolido:sharedAttributes', [])] == [ATTR + 'vehicle_type'],
                      '', json.dumps(rec2)[:300])

        # Oud record (sharedProfileData per groep) blijft leesbaar
        legacy_id = f'regressietest-legacy-{ctx.run_id}'
        legacy_file = idir / f'{legacy_id}.jsonld'
        legacy_file.write_text(json.dumps({
            '@type': 'mysolido:Intention', '@id': f'urn:mysolido:intention:{legacy_id}',
            'mysolido:category': 'autoverzekering', 'schema:description': 'Regressietest oud record',
            'mysolido:status': 'concept', 'schema:dateCreated': '2026-04-03T10:00:00+00:00',
            'schema:validThrough': '2026-05-03T10:00:00+00:00',
            'mysolido:sharedProfileData': {'vehicle': {'included': True, 'data': {'type': 'auto'}},
                                           'insurance': {'included': False}}}, indent=2), encoding='utf-8')
        created.append(legacy_file)
        r = flask(ctx, 'GET', f'/intenties/{legacy_id}')
        rep.check('Intentie: oud record met sharedProfileData blijft leesbaar (groepsweergave)',
                  r.status_code == 200 and 'Oudere intentie' in r.text and 'Voertuigen' in r.text,
                  '', f'status {r.status_code}')
    finally:
        for f in created:
            if f.exists():
                r = flask(ctx, 'POST', f'/intenties/{f.stem}/delete')
            for p in (f, f.with_name(f.stem + '.policy.jsonld')):
                if p.exists():
                    p.unlink()
        rep.check('Intentie: testrecords (en hun policybestanden) opgeruimd',
                  not any(p.exists() for f in created for p in (f, f.with_name(f.stem + '.policy.jsonld'))),
                  '', 'bestanden bestaan nog')


def phase_intention_policy(ctx: Ctx):
    """ODRL-Offer per intentie (subtaak 3): bestand, vorm, samenvatting, leesroute, herstelroute, listing."""
    rep = ctx.report
    idir = ctx.pod_dir / 'intenties'
    profile = read_profile(ctx)
    expected = expected_scenario_values(profile)
    if not all(expected.values()):
        rep.skip('Intentiepolicy: profiel mist scenariowaarden, fase overgeslagen', json.dumps(expected))
        return

    def listing():
        return {p.name for p in idir.glob('*.jsonld')} if idir.exists() else set()

    def new_files(before):
        return [p for p in idir.glob('*.jsonld') if p.name not in before
                and not p.name.startswith('.') and not p.name.endswith('.policy.jsonld')] if idir.exists() else []

    def policy_file(rec_file: Path) -> Path:
        return rec_file.with_name(rec_file.stem + '.policy.jsonld')

    def create(data):
        before = listing()
        r = flask(ctx, 'POST', '/intenties/nieuw', data=data)
        return r, new_files(before)

    created = []
    route_removed_policy = None
    try:
        # 1. Open aanbod, vier attributen, doorleververbod
        r, new = create({'category': 'autoverzekering', 'description': 'Regressietest policy open',
                         'validity': '2w', 'attributes': list(SCENARIO_ATTRIBUTES),
                         'purpose': 'quote_calculation', 'no_onward_transfer': '1', 'offer_mode': 'open'})
        if not rep.check('Intentiepolicy: intentie aangemaakt', r.status_code in REDIRECT and len(new) == 1,
                         '', f'status {r.status_code}, nieuwe bestanden: {len(new)}'):
            return
        rec_file = new[0]
        created.append(rec_file)
        iid = rec_file.stem
        uid = f'urn:mysolido:policy:intention:{iid}'
        rec = json.loads(rec_file.read_text(encoding='utf-8'))
        pf = policy_file(rec_file)
        if not rep.check('Intentiepolicy: intenties/<uuid>.policy.jsonld geschreven', pf.exists(), pf.name, 'ontbreekt'):
            return
        pol = json.loads(pf.read_text(encoding='utf-8'))
        rep.check('Intentiepolicy: @type Offer, uid, profile en assigner = WEBID',
                  pol.get('@type') == 'Offer' and pol.get('uid') == uid and pol.get('assigner') == ctx.webid
                  and pol.get('profile') == 'http://www.w3.org/ns/odrl/2/core',
                  '', json.dumps({k: pol.get(k) for k in ('@type', 'uid', 'assigner', 'profile')}))
        perms = pol.get('permission') or [{}]
        perm = perms[0]
        rep.check('Intentiepolicy: één permission "use" met de vier targets in recordvolgorde',
                  len(perms) == 1 and perm.get('action') == 'use'
                  and perm.get('target') == [ATTR + k for k in SCENARIO_ATTRIBUTES],
                  '', json.dumps(perm.get('target')))
        cons = {c.get('leftOperand'): c for c in perm.get('constraint', [])}
        purpose_c = cons.get('purpose') or {}
        rep.check('Intentiepolicy: constraint purpose eq urn:mysolido:purpose:quote_calculation',
                  purpose_c.get('operator') == 'eq'
                  and (purpose_c.get('rightOperand') or {}).get('@id') == 'urn:mysolido:purpose:quote_calculation',
                  '', json.dumps(purpose_c))
        date_c = cons.get('dateTime') or {}
        rep.check('Intentiepolicy: constraint dateTime lteq schema:validThrough (xsd:dateTime)',
                  date_c.get('operator') == 'lteq'
                  and (date_c.get('rightOperand') or {}).get('@value') == rec.get('schema:validThrough')
                  and (date_c.get('rightOperand') or {}).get('@type') == 'xsd:dateTime',
                  '', json.dumps(date_c))
        prohib = pol.get('prohibition') or []
        rep.check('Intentiepolicy: prohibition distribute + transfer op dezelfde targets (noOnwardTransfer true)',
                  len(prohib) == 1 and sorted(actions(prohib[0].get('action'))) == ['distribute', 'transfer']
                  and prohib[0].get('target') == perm.get('target'),
                  '', json.dumps(prohib))
        rep.check('Intentiepolicy: open aanbod heeft geen assignee',
                  'assignee' not in perm and not any('assignee' in p for p in prohib), '', json.dumps(perm.get('assignee')))
        rep.check('Intentiepolicy: record bevat mysolido:policy = uid', rec.get('mysolido:policy') == uid,
                  '', str(rec.get('mysolido:policy')))
        r = flask(ctx, 'GET', f'/intenties/{iid}')
        needles = ('Iedereen die deze voorwaarden accepteert', 'leeftijdscategorie', 'postcodegebied',
                   'voertuigtype', 'schadeverleden', 'offerteberekening', 'niet doorleveren', 'Voorwaarden (ODRL-aanbod)')
        rep.check('Intentiepolicy: detailpagina toont de samenvatting met vier labels, doel en doorleverzin',
                  r.status_code == 200 and all(n in r.text for n in needles),
                  '', f'status {r.status_code}, ontbreekt: {[n for n in needles if n not in r.text]}')
        rep.check('Intentiepolicy: detailpagina toont de ruwe JSON-LD (uid zichtbaar)', uid in r.text, '', 'uid niet in pagina')
        rep.check('Intentiepolicy: "Vastgelegd op" in dd-mm-jjjj',
                  f"Vastgelegd op {datetime.fromisoformat(rec['schema:dateCreated']).strftime('%d-%m-%Y')}" in r.text,
                  '', 'datumnotatie niet gevonden')
        r = flask(ctx, 'GET', f'/intenties/{iid}/policy.jsonld')
        rep.check('Intentiepolicy: GET /intenties/<uuid>/policy.jsonld geeft application/ld+json met de Offer',
                  r.status_code == 200 and 'application/ld+json' in r.headers.get('Content-Type', '')
                  and r.json().get('uid') == uid,
                  r.headers.get('Content-Type', ''), f'status {r.status_code}')

        # 2. Gericht aanbod zonder doorleververbod
        r, new = create({'category': 'autoverzekering', 'description': 'Regressietest policy gericht',
                         'validity': '1w', 'attributes': ['vehicle_type', 'postal_area'],
                         'purpose': 'quote_calculation', 'offer_mode': 'targeted', 'targeted_party': 'Verzekeraar X'})
        if rep.check('Intentiepolicy: gericht aanbod aangemaakt', r.status_code in REDIRECT and len(new) == 1,
                     '', f'status {r.status_code}'):
            rec2_file = new[0]
            created.append(rec2_file)
            rec2 = json.loads(rec2_file.read_text(encoding='utf-8'))
            pf2 = policy_file(rec2_file)
            pol2 = json.loads(pf2.read_text(encoding='utf-8')) if pf2.exists() else {}
            perm2 = (pol2.get('permission') or [{}])[0]
            party_id = str((rec2.get('mysolido:targetedParty') or {}).get('@id', ''))
            assignee = perm2.get('assignee') or {}
            rep.check('Intentiepolicy: assignee = targetedParty.@id met rdfs:label, targets in volgorde, geen prohibition',
                      party_id.startswith('urn:mysolido:party:') and assignee.get('@id') == party_id
                      and assignee.get('rdfs:label') == 'Verzekeraar X' and not pol2.get('prohibition')
                      and perm2.get('target') == [ATTR + 'vehicle_type', ATTR + 'postal_area'],
                      '', json.dumps(pol2)[:300])
            r = flask(ctx, 'GET', f'/intenties/{rec2_file.stem}')
            rep.check('Intentiepolicy: samenvatting gericht aanbod begint met de partijnaam, zonder doorleverzin',
                      r.status_code == 200 and 'Verzekeraar X mag voertuigtype en postcodegebied' in r.text
                      and 'niet doorleveren' not in r.text,
                      '', f'status {r.status_code}')

        # 3. Zonder attributen geweigerd
        before = listing()
        r = flask(ctx, 'POST', '/intenties/nieuw', data={'category': 'anders', 'description': 'Regressietest zonder attributen',
                                                          'validity': '1w', 'purpose': 'quote_calculation'})
        refused_new = new_files(before)
        follow = flask(ctx, 'GET', '/intenties/nieuw')
        rep.check('Intentiepolicy: intentie zonder attributen wordt geweigerd met melding',
                  r.status_code in REDIRECT and not refused_new and 'minstens' in follow.text,
                  '', f'status {r.status_code}, nieuwe bestanden: {len(refused_new)}')

        # 4. "Voorwaarden opstellen" voor een record zonder policybestand
        pf.unlink()
        r = flask(ctx, 'GET', f'/intenties/{iid}')
        rep.check('Intentiepolicy: zonder policybestand toont de detailpagina "Voorwaarden opstellen"',
                  r.status_code == 200 and 'Voorwaarden opstellen' in r.text, '', f'status {r.status_code}')
        r = flask(ctx, 'POST', f'/intenties/{iid}/policy/create')
        pol_again = json.loads(pf.read_text(encoding='utf-8')) if pf.exists() else {}
        rep.check('Intentiepolicy: POST policy/create maakt de Offer opnieuw aan',
                  r.status_code in REDIRECT and pol_again.get('uid') == uid, '', f'status {r.status_code}, bestaat: {pf.exists()}')

        # 5. Listing, zoeken en overzicht
        r = flask(ctx, 'GET', '/browse/intenties')
        rep.check('Intentiepolicy: policybestand niet in de kluislisting', r.status_code == 200 and '.policy.jsonld' not in r.text,
                  '', f'status {r.status_code}')
        r = flask(ctx, 'GET', '/search', params={'q': 'policy'})
        rep.check('Intentiepolicy: policybestand niet in zoekresultaten', r.status_code == 200 and '.policy.jsonld' not in r.text,
                  '', f'status {r.status_code}')
        r = flask(ctx, 'GET', '/intenties')
        rep.check('Intentiepolicy: policybestand niet als intentie in het overzicht',
                  r.status_code == 200 and f'{iid}.policy' not in r.text, '', f'status {r.status_code}')

        # 6. Verwijderen van de intentie neemt de Offer mee
        flask(ctx, 'POST', f'/intenties/{iid}/delete')
        route_removed_policy = not rec_file.exists() and not pf.exists()
        rep.check('Intentiepolicy: verwijderen van de intentie verwijdert ook de Offer', bool(route_removed_policy),
                  '', f'record: {rec_file.exists()}, policy: {pf.exists()}')
    finally:
        for f in created:
            if f.exists():
                flask(ctx, 'POST', f'/intenties/{f.stem}/delete')
            for p in (f, policy_file(f)):
                if p.exists():
                    p.unlink()
        rep.check('Intentiepolicy: testrecords en policybestanden opgeruimd',
                  not any(p.exists() for f in created for p in (f, policy_file(f))), '', 'bestanden bestaan nog')


def phase_acceptance(ctx: Ctx):
    """Acceptatie en Agreement (subtaak 4a): open aanbod, concept, gericht aanbod, leesroute, listing."""
    import hashlib
    rep = ctx.report
    idir = ctx.pod_dir / 'intenties'
    vdir = ctx.pod_dir / 'verzoeken'
    profile = read_profile(ctx)
    expected = expected_scenario_values(profile)
    if not all(expected.values()):
        rep.skip('Acceptatie: profiel mist scenariowaarden, fase overgeslagen', json.dumps(expected))
        return
    anon = requests.Session()

    def listing(folder):
        return {p.name for p in folder.glob('*.jsonld')} if folder.exists() else set()

    def new_records(folder, before):
        return [p for p in folder.glob('*.jsonld') if p.name not in before and not p.name.startswith('.')
                and not p.name.endswith(('.policy.jsonld', '.agreement.jsonld'))] if folder.exists() else []

    def create_intention(data):
        before = listing(idir)
        r = flask(ctx, 'POST', '/intenties/nieuw', data=data)
        new = new_records(idir, before)
        return (new[0] if len(new) == 1 and r.status_code in REDIRECT else None)

    def accept(iid, data):
        before = listing(vdir)
        r = anon.post(f'{ctx.flask_base}/verzoek/intentie/{iid}', data=data, timeout=TIMEOUT, allow_redirects=False)
        return r, new_records(vdir, before)

    def files_for(req_file: Path):
        return (req_file, req_file.with_name(req_file.stem + '.agreement.jsonld'),
                req_file.with_name(req_file.stem + '_response.json'))

    intentions, request_files = [], []
    try:
        # 1. Open aanbod aanmaken en activeren
        open_file = create_intention({'category': 'autoverzekering', 'description': 'Regressietest acceptatie open',
                                      'validity': '2w', 'attributes': list(SCENARIO_ATTRIBUTES),
                                      'purpose': 'quote_calculation', 'no_onward_transfer': '1', 'offer_mode': 'open'})
        if not rep.check('Acceptatie: open intentie aangemaakt', open_file is not None, '', 'geen record'):
            return
        intentions.append(open_file)
        iid = open_file.stem
        flask(ctx, 'POST', f'/intenties/{iid}/activate')
        rec = json.loads(open_file.read_text(encoding='utf-8'))
        rep.check('Acceptatie: intentie geactiveerd', rec.get('mysolido:status') == 'actief', '', rec.get('mysolido:status'))
        policy_file = open_file.with_name(f'{iid}.policy.jsonld')
        policy_hash = 'sha256:' + hashlib.sha256(policy_file.read_bytes()).hexdigest()
        uid = f'urn:mysolido:policy:intention:{iid}'

        # 2. Formulier: zin, JSON, vier labels zonder waarden
        r = anon.get(f'{ctx.flask_base}/verzoek/intentie/{iid}', timeout=TIMEOUT)
        labels_ok = all(l in r.text for l in ('Leeftijdscategorie', 'Postcodegebied', 'Voertuigtype', 'Schadeverleden'))
        values_absent = all(v not in r.text for v in ('35-44', '5611', 'Schadevrije jaren: 5'))
        rep.check('Acceptatie: formulier toont samenvattingszin, JSON-LD en vier labels zonder waarden',
                  r.status_code == 200 and 'Iedereen die deze voorwaarden accepteert' in r.text and uid in r.text
                  and labels_ok and values_absent and 'name="accept_terms"' in r.text,
                  '', f'status {r.status_code}, labels {labels_ok}, waarden afwezig {values_absent}')

        # 3. Zonder vinkje geweigerd
        r, new = accept(iid, {'name': 'Verzekeraar X', 'organization': 'Verzekeraar X BV', 'email': 'offerte@verzekeraar-x.test'})
        rep.check('Acceptatie: zonder vinkje geweigerd, geen verzoek', r.status_code in REDIRECT and not new,
                  '', f'status {r.status_code}, nieuwe bestanden: {len(new)}')

        # 4. Met vinkje: verzoek, Agreement, response
        r, new = accept(iid, {'name': 'Verzekeraar X', 'organization': 'Verzekeraar X BV',
                              'email': 'offerte@verzekeraar-x.test', 'accept_terms': 'yes'})
        if not rep.check('Acceptatie: verzoekrecord geschreven bij acceptatie', r.status_code == 200 and len(new) == 1,
                         '', f'status {r.status_code}, nieuwe bestanden: {len(new)}'):
            return
        req_file = new[0]
        request_files.append(req_file)
        rid = req_file.stem
        req = json.loads(req_file.read_text(encoding='utf-8'))
        party = req.get('mysolido:party') or {}
        rep.check('Acceptatie: verzoek bevat intention, acceptedPolicy, acceptedAt (hele seconden), hash en party',
                  req.get('mysolido:intention') == rec.get('@id') and req.get('mysolido:acceptedPolicy') == uid
                  and req.get('mysolido:acceptedPolicyHash') == policy_hash
                  and '.' not in str(req.get('mysolido:acceptedAt', '')).split('+')[0]
                  and str(party.get('@id', '')).startswith('urn:mysolido:party:') and party.get('rdfs:label') == 'Verzekeraar X BV'
                  and party.get('mysolido:contactName') == 'Verzekeraar X'   # label = organisatie, persoon apart (4b)
                  and party.get('mysolido:organisation') == 'Verzekeraar X BV' and party.get('mysolido:contact') == 'offerte@verzekeraar-x.test',
                  '', json.dumps({k: req.get(k) for k in ('mysolido:intention', 'mysolido:acceptedPolicy', 'mysolido:acceptedAt',
                                                          'mysolido:acceptedPolicyHash', 'mysolido:party')}))
        rep.check('Acceptatie: status geaccepteerd, agreement-uid, responseLink en validUntil = validThrough',
                  req.get('mysolido:status') == 'geaccepteerd' and req.get('mysolido:agreement') == f'urn:mysolido:agreement:{rid}'
                  and req.get('mysolido:responseLink') == f"/verzoek/response/{req.get('mysolido:statusToken')}"
                  and req.get('mysolido:validUntil') == rec.get('schema:validThrough'),
                  '', json.dumps({k: req.get(k) for k in ('mysolido:status', 'mysolido:agreement', 'mysolido:validUntil')}))
        _, agr_file, resp_file = files_for(req_file)
        offer = json.loads(policy_file.read_text(encoding='utf-8'))
        agr = json.loads(agr_file.read_text(encoding='utf-8')) if agr_file.exists() else {}

        def strip_assignee(rules):
            return [{k: v for k, v in r.items() if k != 'assignee'} for r in rules]
        assignee_ok = all(r.get('assignee', {}).get('@id') == party.get('@id') and r.get('assignee', {}).get('rdfs:label') == 'Verzekeraar X BV'
                          for r in agr.get('permission', []) + agr.get('prohibition', []))
        rep.check('Acceptatie: Agreement met @type, uid, assigner, assignee op permission én prohibition',
                  agr.get('@type') == 'Agreement' and agr.get('uid') == f'urn:mysolido:agreement:{rid}'
                  and agr.get('assigner') == ctx.webid and assignee_ok and agr.get('prohibition'),
                  '', json.dumps(agr)[:300])
        rep.check('Acceptatie: permission en prohibition gelijk aan de Offer (op assignee na)',
                  strip_assignee(agr.get('permission', [])) == offer.get('permission')
                  and strip_assignee(agr.get('prohibition', [])) == offer.get('prohibition'),
                  '', 'regels wijken af')
        rep.check('Acceptatie: Agreement bevat mysolido:offer, request, acceptedAt en offerHash',
                  agr.get('mysolido:offer') == uid and agr.get('mysolido:request') == req.get('@id')
                  and agr.get('mysolido:acceptedAt') == req.get('mysolido:acceptedAt') and agr.get('mysolido:offerHash') == policy_hash,
                  '', json.dumps({k: agr.get(k) for k in ('mysolido:offer', 'mysolido:request', 'mysolido:offerHash')}))
        resp = json.loads(resp_file.read_text(encoding='utf-8')) if resp_file.exists() else {}
        attrs = resp.get('attributes', [])
        rep.check('Acceptatie: response.json bevat precies de vier attributen met label en valueLabel',
                  [a.get('@id') for a in attrs] == [ATTR + k for k in SCENARIO_ATTRIBUTES]
                  and all(a.get('label') and a.get('valueLabel') for a in attrs) and 'fuel' not in json.dumps(resp),
                  '', json.dumps(resp)[:300])
        r = anon.get(f"{ctx.flask_base}{req.get('mysolido:responseLink')}", timeout=TIMEOUT)
        rep.check('Acceptatie: responspagina toont zin, Agreement-uid en de vier waarden, niet brandstof of bouwjaar',
                  r.status_code == 200 and 'Verzekeraar X BV mag' in r.text and f'urn:mysolido:agreement:{rid}' in r.text
                  and all(v in r.text for v in ('35-44', '5611', 'Auto', 'Schadevrije jaren: 5'))
                  and 'Benzine' not in r.text and '2019' not in r.text,
                  '', f'status {r.status_code}')
        r = anon.get(f"{ctx.flask_base}/verzoek/status/{req.get('mysolido:statusToken')}", timeout=TIMEOUT)
        rep.check('Acceptatie: statuspagina toont geaccepteerd met link naar de gegevens',
                  r.status_code == 200 and 'badge-geaccepteerd' in r.text and req.get('mysolido:responseLink') in r.text,
                  '', f'status {r.status_code}')
        rec = json.loads(open_file.read_text(encoding='utf-8'))
        rep.check('Acceptatie: intentierecord heeft acceptedBy met het verzoek', rec.get('mysolido:acceptedBy') == [req.get('@id')],
                  '', json.dumps(rec.get('mysolido:acceptedBy')))
        r = flask(ctx, 'GET', f'/intenties/{iid}')
        rep.check('Acceptatie: detailpagina toont "Geaccepteerd door Verzekeraar X"',
                  r.status_code == 200 and 'Geaccepteerd door' in r.text and 'Verzekeraar X BV op' in r.text, '', f'status {r.status_code}')
        r = flask(ctx, 'POST', f'/intenties/{iid}/delete')
        rep.check('Acceptatie: verwijderen van een geaccepteerde intentie geblokkeerd',
                  r.status_code in REDIRECT and open_file.exists() and policy_file.exists(), '', f'status {r.status_code}, bestaat {open_file.exists()}')
        r = flask(ctx, 'GET', f'/verzoeken/{rid}')
        rep.check('Acceptatie: eigenaarsdetail toont partij, tijdstip, hash en Agreement-link',
                  r.status_code == 200 and policy_hash in r.text and party.get('@id') in r.text and f'/verzoeken/{rid}/agreement.jsonld' in r.text,
                  '', f'status {r.status_code}')
        r = flask(ctx, 'GET', f'/verzoeken/{rid}/agreement.jsonld')
        rep.check('Acceptatie: GET /verzoeken/<uuid>/agreement.jsonld geeft application/ld+json',
                  r.status_code == 200 and 'application/ld+json' in r.headers.get('Content-Type', '')
                  and r.json().get('uid') == f'urn:mysolido:agreement:{rid}',
                  r.headers.get('Content-Type', ''), f'status {r.status_code}')

        # 5. Concept-intentie: voorwaarden lezen, niet accepteren
        concept_file = create_intention({'category': 'autoverzekering', 'description': 'Regressietest acceptatie concept',
                                         'validity': '1w', 'attributes': ['vehicle_type'], 'purpose': 'quote_calculation', 'offer_mode': 'open'})
        if rep.check('Acceptatie: concept-intentie aangemaakt', concept_file is not None, '', 'geen record'):
            intentions.append(concept_file)
            cid = concept_file.stem
            r = anon.get(f'{ctx.flask_base}/verzoek/intentie/{cid}', timeout=TIMEOUT)
            rep.check('Acceptatie: concept toont voorwaarden maar geen acceptatieformulier',
                      r.status_code == 200 and f'urn:mysolido:policy:intention:{cid}' in r.text and 'name="accept_terms"' not in r.text
                      and 'niet actief' in r.text, '', f'status {r.status_code}')
            r, new = accept(cid, {'name': 'Test', 'email': 'test@example.test', 'accept_terms': 'yes'})
            rep.check('Acceptatie: POST op concept geweigerd', r.status_code in REDIRECT and not new, '', f'status {r.status_code}, nieuw {len(new)}')

        # 6. Gericht aanbod: wacht op bevestiging, daarna Agreement via verzoek_approve
        targeted_file = create_intention({'category': 'autoverzekering', 'description': 'Regressietest acceptatie gericht',
                                          'validity': '1w', 'attributes': ['vehicle_type', 'postal_area'], 'purpose': 'quote_calculation',
                                          'no_onward_transfer': '1', 'offer_mode': 'targeted', 'targeted_party': 'Verzekeraar Y'})
        if rep.check('Acceptatie: gerichte intentie aangemaakt', targeted_file is not None, '', 'geen record'):
            intentions.append(targeted_file)
            tid = targeted_file.stem
            flask(ctx, 'POST', f'/intenties/{tid}/activate')
            trec = json.loads(targeted_file.read_text(encoding='utf-8'))
            r, new = accept(tid, {'name': 'Verzekeraar Y', 'email': 'y@verzekeraar-y.test', 'accept_terms': 'yes'})
            if rep.check('Acceptatie: gericht aanbod: verzoek geregistreerd', r.status_code == 200 and len(new) == 1, '', f'status {r.status_code}'):
                treq_file = new[0]
                request_files.append(treq_file)
                trid = treq_file.stem
                treq = json.loads(treq_file.read_text(encoding='utf-8'))
                _, tagr_file, tresp_file = files_for(treq_file)
                rep.check('Acceptatie: gericht: status wacht-op-bevestiging, partij-id = targetedParty.@id, nog geen Agreement',
                          treq.get('mysolido:status') == 'wacht-op-bevestiging' and not tagr_file.exists() and not tresp_file.exists()
                          and (treq.get('mysolido:party') or {}).get('@id') == (trec.get('mysolido:targetedParty') or {}).get('@id')
                          and 'wacht op bevestiging' in r.text.lower(),
                          '', json.dumps({k: treq.get(k) for k in ('mysolido:status', 'mysolido:party')}))
                r = flask(ctx, 'GET', f'/verzoeken/{trid}')
                rep.check('Acceptatie: gericht: eigenaarsdetail toont bevestigknop', r.status_code == 200 and 'Bevestigen' in r.text, '', f'status {r.status_code}')
                r = flask(ctx, 'POST', f'/verzoeken/{trid}/approve')
                treq = json.loads(treq_file.read_text(encoding='utf-8'))
                tagr = json.loads(tagr_file.read_text(encoding='utf-8')) if tagr_file.exists() else {}
                rep.check('Acceptatie: gericht: na goedkeuren status geaccepteerd en Agreement met assignee = targetedParty.@id',
                          r.status_code in REDIRECT and treq.get('mysolido:status') == 'geaccepteerd' and tresp_file.exists()
                          and (tagr.get('permission') or [{}])[0].get('assignee', {}).get('@id') == (trec.get('mysolido:targetedParty') or {}).get('@id')
                          and (tagr.get('permission') or [{}])[0].get('assignee', {}).get('rdfs:label') == 'Verzekeraar Y',
                          '', json.dumps(tagr)[:300])
                r = flask(ctx, 'POST', f'/verzoeken/{trid}/approve')
                rep.check('Acceptatie: gericht: tweede goedkeuring wordt geweigerd (al afgehandeld)', r.status_code in REDIRECT, '', f'status {r.status_code}')

        # 7. Listing, zoeken, overzichten
        r = flask(ctx, 'GET', '/browse/verzoeken')
        rep.check('Acceptatie: .agreement.jsonld niet in de kluislisting', r.status_code == 200 and '.agreement.jsonld' not in r.text, '', f'status {r.status_code}')
        r = flask(ctx, 'GET', '/search', params={'q': 'agreement'})
        rep.check('Acceptatie: .agreement.jsonld niet in zoekresultaten', r.status_code == 200 and '.agreement.jsonld' not in r.text, '', f'status {r.status_code}')
        r = flask(ctx, 'GET', '/verzoeken')
        rep.check('Acceptatie: Agreement niet als verzoek in het overzicht; verzoeken tonen labels',
                  r.status_code == 200 and '.agreement' not in r.text and 'Leeftijdscategorie' in r.text, '', f'status {r.status_code}')
    finally:
        consent_leftovers = []
        for f in request_files:
            # consentrecord van deze acceptatie (subtaak 4b) mee opruimen
            if f.exists():
                try:
                    cid = str(json.loads(f.read_text(encoding='utf-8')).get('mysolido:consent', '')).rsplit(':', 1)[-1]
                except (ValueError, OSError):
                    cid = ''
                cpath = ctx.pod_dir / 'toestemmingen' / f'{cid}.jsonld'
                if cid and cpath.exists():
                    cpath.unlink()
                if cid and cpath.exists():
                    consent_leftovers.append(cpath)
            for p in files_for(f):
                if p.exists():
                    p.unlink()
        for f in intentions:
            flask(ctx, 'POST', f'/intenties/{f.stem}/delete')   # geblokkeerd bij acceptedBy, dan handmatig
            for p in (f, f.with_name(f.stem + '.policy.jsonld')):
                if p.exists():
                    p.unlink()
        leftovers = [p for f in intentions for p in (f, f.with_name(f.stem + '.policy.jsonld')) if p.exists()]
        leftovers += [p for f in request_files for p in files_for(f) if p.exists()]
        leftovers += consent_leftovers
        rep.check('Acceptatie: testintenties, verzoeken, Agreements, responses en consentrecords opgeruimd', not leftovers, '', str(leftovers))


def phase_consent_record(ctx: Ctx):
    """Consentrecord in ISO/IEC TS 27560-structuur (subtaak 4b): velden, weergave, intrekken, statusnormalisatie."""
    rep = ctx.report
    idir = ctx.pod_dir / 'intenties'
    vdir = ctx.pod_dir / 'verzoeken'
    cdir = ctx.pod_dir / 'toestemmingen'
    profile = read_profile(ctx)
    expected = expected_scenario_values(profile)
    if not all(expected.values()):
        rep.skip('Consentrecord: profiel mist scenariowaarden, fase overgeslagen', json.dumps(expected))
        return
    anon = requests.Session()

    def listing(folder):
        return {p.name for p in folder.glob('*.jsonld')} if folder.exists() else set()

    def new_records(folder, before):
        return [p for p in folder.glob('*.jsonld') if p.name not in before and not p.name.startswith('.')
                and not p.name.endswith(('.policy.jsonld', '.agreement.jsonld'))] if folder.exists() else []

    def create_intention(data):
        before = listing(idir)
        r = flask(ctx, 'POST', '/intenties/nieuw', data=data)
        new = new_records(idir, before)
        return (new[0] if len(new) == 1 and r.status_code in REDIRECT else None)

    def accept(iid, data):
        before = listing(vdir)
        r = anon.post(f'{ctx.flask_base}/verzoek/intentie/{iid}', data=data, timeout=TIMEOUT, allow_redirects=False)
        return r, new_records(vdir, before)

    def consent_file_of(req):
        cid = str(req.get('mysolido:consent', '')).rsplit(':', 1)[-1]
        return cid, (cdir / f'{cid}.jsonld' if cid else None)

    intentions, request_files, consent_files, fixtures = [], [], [], []
    try:
        # 1. Open aanbod accepteren -> consentrecord
        open_file = create_intention({'category': 'autoverzekering', 'description': 'Regressietest consent open',
                                      'validity': '2w', 'attributes': list(SCENARIO_ATTRIBUTES),
                                      'purpose': 'quote_calculation', 'no_onward_transfer': '1', 'offer_mode': 'open'})
        if not rep.check('Consentrecord: open intentie aangemaakt', open_file is not None, '', 'geen record'):
            return
        intentions.append(open_file)
        iid = open_file.stem
        flask(ctx, 'POST', f'/intenties/{iid}/activate')
        rec = json.loads(open_file.read_text(encoding='utf-8'))
        r, new = accept(iid, {'name': 'Verzekeraar X', 'organization': 'Verzekeraar X BV',
                              'email': 'offerte@verzekeraar-x.test', 'accept_terms': 'yes'})
        if not rep.check('Consentrecord: acceptatie geregistreerd', r.status_code == 200 and len(new) == 1, '', f'status {r.status_code}'):
            return
        req_file = new[0]
        request_files.append(req_file)
        rid = req_file.stem
        req = json.loads(req_file.read_text(encoding='utf-8'))
        party = req.get('mysolido:party') or {}
        cid, cfile = consent_file_of(req)
        if not rep.check('Consentrecord: verzoek heeft mysolido:consent en toestemmingen/<id>.jsonld bestaat',
                         bool(cid) and cfile is not None and cfile.exists() and req.get('mysolido:consent') == f'urn:mysolido:consent:{cid}',
                         cid, f'consent {req.get("mysolido:consent")}, bestaat {cfile.exists() if cfile else None}'):
            return
        consent_files.append(cfile)
        con = json.loads(cfile.read_text(encoding='utf-8'))
        # -- kop --
        rep.check('Consentrecord: kop (dpv:ConsentRecord, dct:conformsTo 27560, schemaversie, identifier, hasDataSubject = WEBID)',
                  con.get('@type') == 'dpv:ConsentRecord' and con.get('dct:conformsTo') == 'ISO/IEC TS 27560:2023'
                  and con.get('mysolido:recordSchemaVersion') == '1.0' and con.get('dct:identifier') == cid
                  and con.get('@id') == f'urn:mysolido:consent:{cid}'
                  and (con.get('dpv:hasDataSubject') or {}).get('@id') == ctx.webid,
                  '', json.dumps({k: con.get(k) for k in ('@type', 'dct:conformsTo', 'dct:identifier', 'dpv:hasDataSubject')}))
        # -- verwerking --
        purpose = con.get('dpv:hasPurpose') or {}
        rep.check('Consentrecord: hasPurpose = purpose-urn met dpv:ServiceProvision en label; hasLegalBasis ExplicitlyExpressedConsent',
                  purpose.get('@id') == 'urn:mysolido:purpose:quote_calculation' and purpose.get('@type') == 'dpv:ServiceProvision'
                  and purpose.get('rdfs:label') == 'Offerteberekening' and con.get('dpv:hasLegalBasis') == 'dpv:ExplicitlyExpressedConsent',
                  '', json.dumps(purpose))
        pdata = con.get('dpv:hasPersonalData') or []
        resp = json.loads(req_file.with_name(f'{rid}_response.json').read_text(encoding='utf-8'))
        resp_values = {a['@id']: a['valueLabel'] for a in resp.get('attributes', [])}
        expected_types = {ATTR + 'age_category': 'pd:AgeRange', ATTR + 'postal_area': 'pd:PostalCode',
                          ATTR + 'vehicle_type': 'pd:Vehicle', ATTR + 'claims_history': 'pd:Insurance'}
        rep.check('Consentrecord: hasPersonalData precies vier, urn als @id, pd-term als @type, label en waarde uit het snapshot',
                  [p.get('@id') for p in pdata] == [ATTR + k for k in SCENARIO_ATTRIBUTES]
                  and all(p.get('@type') == expected_types[p['@id']] and p.get('rdfs:label') and p.get('mysolido:value') == resp_values.get(p['@id'])
                          for p in pdata),
                  '', json.dumps(pdata)[:300])
        ctrl = con.get('dpv:hasDataController') or {}
        rep.check('Consentrecord: hasDataController = partij-@id met organisatie als label, contactpersoon en e-mail',
                  ctrl.get('@id') == party.get('@id') and ctrl.get('@type') == 'dpv:DataController'
                  and ctrl.get('rdfs:label') == 'Verzekeraar X BV' and ctrl.get('mysolido:contactName') == 'Verzekeraar X'
                  and ctrl.get('mysolido:contact') == 'offerte@verzekeraar-x.test',
                  '', json.dumps(ctrl))
        storage = con.get('dpv:hasStorageCondition') or {}
        rep.check('Consentrecord: hasStorageCondition met validUntil = validThrough en 14 dagen',
                  storage.get('@type') == 'dpv:StorageDuration' and storage.get('mysolido:validUntil') == rec.get('schema:validThrough')
                  and (storage.get('dpv:hasDuration') or {}).get('mysolido:days') == 14
                  and (storage.get('dpv:hasDuration') or {}).get('mysolido:iso8601') == 'P14D',
                  '', json.dumps(storage))
        rep.check('Consentrecord: hasRecipient leeg, onwardTransfer prohibited met verwijzing naar de Agreement, jurisdictie loc:NL',
                  con.get('dpv:hasRecipient') == [] and con.get('mysolido:onwardTransfer') == 'prohibited'
                  and con.get('mysolido:onwardTransferProhibition') == req.get('mysolido:agreement')
                  and (con.get('dpv:hasJurisdiction') or {}).get('@id') == 'loc:NL',
                  '', json.dumps({k: con.get(k) for k in ('dpv:hasRecipient', 'mysolido:onwardTransfer', 'dpv:hasJurisdiction')}))
        # -- gebeurtenis --
        events = con.get('mysolido:events') or []
        rep.check('Consentrecord: status dpv:ConsentGiven, één event given op acceptedAt door de partij, isImplementedByEntity = WEBID',
                  con.get('dpv:hasConsentStatus') == 'dpv:ConsentGiven' and len(events) == 1
                  and events[0].get('@type') == 'given' and events[0].get('at') == req.get('mysolido:acceptedAt')
                  and events[0].get('by') == party.get('@id')
                  and (con.get('dpv:isImplementedByEntity') or {}).get('@id') == ctx.webid,
                  '', json.dumps({'status': con.get('dpv:hasConsentStatus'), 'events': events}))
        # -- koppelingen --
        rep.check('Consentrecord: vijf koppelingen (agreement, intention, request, acceptedPolicy, offerHash) en recht eu-gdpr:A7-3',
                  con.get('mysolido:agreement') == req.get('mysolido:agreement') and con.get('mysolido:intention') == rec.get('@id')
                  and con.get('mysolido:request') == req.get('@id') and con.get('mysolido:acceptedPolicy') == req.get('mysolido:acceptedPolicy')
                  and con.get('mysolido:offerHash') == req.get('mysolido:acceptedPolicyHash') and con.get('dpv:hasRight') == 'eu-gdpr:A7-3',
                  '', json.dumps({k: con.get(k) for k in ('mysolido:agreement', 'mysolido:intention', 'mysolido:request')}))
        # -- weergave --
        r = flask(ctx, 'GET', '/consent')
        rep.check('Consentrecord: consentlijst toont het record met partijlabel en intentiecategorie',
                  r.status_code == 200 and cid in r.text and 'Verzekeraar X BV' in r.text and 'Autoverzekering' in r.text,
                  '', f'status {r.status_code}')
        r = flask(ctx, 'GET', f'/consent/{cid}')
        rep.check('Consentrecord: detailpagina toont 27560-weergave met vier attributen, waarden, gebeurtenis en koppelingen',
                  r.status_code == 200 and 'ISO/IEC TS 27560' in r.text and 'dpv:ConsentGiven' in r.text
                  and all(f'data-attribute="{ATTR}{k}"' in r.text for k in SCENARIO_ATTRIBUTES) and '5611' in r.text
                  and f'/verzoeken/{rid}/agreement.jsonld' in r.text and f'/intenties/{iid}' in r.text and 'data-event="given"' in r.text,
                  '', f'status {r.status_code}')
        r = flask(ctx, 'GET', f'/verzoeken/{rid}')
        rep.check('Consentrecord: eigenaarsdetail van het verzoek linkt naar het consentrecord en toont de gedeelde waarden',
                  r.status_code == 200 and f'/consent/{cid}' in r.text and '5611' in r.text, '', f'status {r.status_code}')

        # 2. Toestemming intrekken
        created_stamp = con.get('dct:created')
        r = flask(ctx, 'POST', f'/consent/{cid}/withdraw')
        con2 = json.loads(cfile.read_text(encoding='utf-8'))
        events2 = con2.get('mysolido:events') or []
        rep.check('Consentrecord: intrekken zet dpv:ConsentWithdrawn, tweede event withdrawn door WEBID, dct:modified gezet',
                  r.status_code in REDIRECT and con2.get('dpv:hasConsentStatus') == 'dpv:ConsentWithdrawn' and len(events2) == 2
                  and events2[1].get('@type') == 'withdrawn' and events2[1].get('by') == ctx.webid
                  and con2.get('dct:modified') and con2.get('dct:modified') >= created_stamp,
                  '', json.dumps({'status': con2.get('dpv:hasConsentStatus'), 'events': events2, 'modified': con2.get('dct:modified')}))
        req2 = json.loads(req_file.read_text(encoding='utf-8'))
        rep.check('Consentrecord: gekoppeld verzoek op ingetrokken met withdrawnAt',
                  req2.get('mysolido:status') == 'ingetrokken' and bool(req2.get('mysolido:withdrawnAt')),
                  '', json.dumps({k: req2.get(k) for k in ('mysolido:status', 'mysolido:withdrawnAt')}))
        r = anon.get(f"{ctx.flask_base}{req.get('mysolido:responseLink')}", timeout=TIMEOUT)
        rep.check('Consentrecord: responspagina toont "Toestemming ingetrokken op" en geen gegevens meer',
                  r.status_code == 200 and 'Toestemming ingetrokken op' in r.text and '5611' not in r.text and '35-44' not in r.text,
                  '', f'status {r.status_code}')
        r = anon.get(f"{ctx.flask_base}/verzoek/status/{req.get('mysolido:statusToken')}", timeout=TIMEOUT)
        rep.check('Consentrecord: statuspagina toont "Toestemming ingetrokken op" zonder link naar gegevens',
                  r.status_code == 200 and 'Toestemming ingetrokken op' in r.text and req.get('mysolido:responseLink') not in r.text,
                  '', f'status {r.status_code}')
        r = flask(ctx, 'GET', f'/intenties/{iid}')
        rep.check('Consentrecord: intentiepagina toont "(toestemming ingetrokken op"',
                  r.status_code == 200 and '(toestemming ingetrokken op' in r.text, '', f'status {r.status_code}')
        r = flask(ctx, 'GET', f'/consent/{cid}')
        rep.check('Consentrecord: detailpagina toont status ConsentWithdrawn en het withdrawn-event',
                  r.status_code == 200 and 'dpv:ConsentWithdrawn' in r.text and 'data-event="withdrawn"' in r.text, '', f'status {r.status_code}')
        agr_file = req_file.with_name(f'{rid}.agreement.jsonld')
        agr = json.loads(agr_file.read_text(encoding='utf-8')) if agr_file.exists() else {}
        rep.check('Consentrecord: Agreement blijft ongewijzigd bestaan na intrekken',
                  agr.get('@type') == 'Agreement' and 'mysolido:withdrawn' not in json.dumps(agr), '', 'Agreement ontbreekt of gewijzigd')

        # 3. Gericht aanbod: record na bevestiging, label = naam zonder organisatie
        targeted_file = create_intention({'category': 'autoverzekering', 'description': 'Regressietest consent gericht',
                                          'validity': '1w', 'attributes': ['vehicle_type', 'postal_area'], 'purpose': 'quote_calculation',
                                          'offer_mode': 'targeted', 'targeted_party': 'Verzekeraar Y'})
        if rep.check('Consentrecord: gerichte intentie aangemaakt', targeted_file is not None, '', 'geen record'):
            intentions.append(targeted_file)
            tid = targeted_file.stem
            flask(ctx, 'POST', f'/intenties/{tid}/activate')
            r, new = accept(tid, {'name': 'Verzekeraar Y', 'email': 'y@verzekeraar-y.test', 'accept_terms': 'yes'})
            if rep.check('Consentrecord: gericht: acceptatie geregistreerd', r.status_code == 200 and len(new) == 1, '', f'status {r.status_code}'):
                treq_file = new[0]
                request_files.append(treq_file)
                treq = json.loads(treq_file.read_text(encoding='utf-8'))
                rep.check('Consentrecord: gericht: nog geen consentrecord vóór bevestiging', not treq.get('mysolido:consent'), '', str(treq.get('mysolido:consent')))
                flask(ctx, 'POST', f'/verzoeken/{treq_file.stem}/approve')
                treq = json.loads(treq_file.read_text(encoding='utf-8'))
                tcid, tcfile = consent_file_of(treq)
                if rep.check('Consentrecord: gericht: na bevestiging consentrecord aanwezig', bool(tcid) and tcfile is not None and tcfile.exists(), '', str(treq.get('mysolido:consent'))):
                    consent_files.append(tcfile)
                    tcon = json.loads(tcfile.read_text(encoding='utf-8'))
                    tctrl = tcon.get('dpv:hasDataController') or {}
                    rep.check('Consentrecord: gericht: label = naam (geen organisatie), controller = targetedParty.@id, onwardTransfer permitted',
                              tctrl.get('rdfs:label') == 'Verzekeraar Y' and tctrl.get('mysolido:contactName') == 'Verzekeraar Y'
                              and tctrl.get('@id') == (json.loads(targeted_file.read_text(encoding='utf-8')).get('mysolido:targetedParty') or {}).get('@id')
                              and tcon.get('mysolido:onwardTransfer') == 'permitted' and 'mysolido:onwardTransferProhibition' not in tcon
                              and len(tcon.get('dpv:hasPersonalData') or []) == 2,
                              '', json.dumps(tctrl))

        # 4. Fixtures: oude statusterm en verstreken geldigheid
        cdir.mkdir(exist_ok=True)
        legacy = cdir / f'regressietest-legacy-{ctx.run_id}.jsonld'
        legacy.write_text(json.dumps({'@type': 'dpv:ConsentRecord', '@id': f'urn:mysolido:consent:{legacy.stem}',
                                      'dct:title': 'Regressietest oude statusterm', 'dct:created': '2026-04-02T10:00:00Z',
                                      'dct:modified': '2026-04-02T10:00:00Z', 'dpv:hasDataSubject': 'urn:mysolido:owner',
                                      'dpv:hasDataController': {'@id': 'urn:mysolido:party:00000001', 'dct:title': 'Fixture BV'},
                                      'dpv:hasPurpose': {'@type': 'dpv:ServiceProvision', 'dct:description': 'Verzekering'},
                                      'dpv:hasPersonalDataCategory': 'dpv:Financial', 'dpv:hasConsentStatus': 'dpv:ConsentStatusGiven',
                                      'dpv:hasLegalBasis': 'dpv:Consent', 'dpv:hasRight': 'dpv:RightToWithdrawConsent'}, indent=2), encoding='utf-8')
        fixtures.append(legacy)
        expired = cdir / f'regressietest-expired-{ctx.run_id}.jsonld'
        expired.write_text(json.dumps({'@type': 'dpv:ConsentRecord', '@id': f'urn:mysolido:consent:{expired.stem}',
                                       'dct:title': 'Regressietest verlopen', 'dct:created': '2026-01-01T10:00:00Z',
                                       'dct:modified': '2026-01-01T10:00:00Z', 'dpv:hasDataSubject': 'urn:mysolido:owner',
                                       'dpv:hasDataController': {'@id': 'urn:mysolido:party:00000002', 'dct:title': 'Fixture BV'},
                                       'dpv:hasPurpose': {'@type': 'dpv:ServiceProvision', 'dct:description': 'Verzekering'},
                                       'dpv:hasPersonalDataCategory': 'dpv:Financial', 'dpv:hasConsentStatus': 'dpv:ConsentStatusGiven',
                                       'dpv:hasExpiry': {'@type': 'dpv:TemporalDuration', 'dpv:hasExpiryTime': '2026-02-01T00:00:00Z'},
                                       'dpv:hasLegalBasis': 'dpv:Consent'}, indent=2), encoding='utf-8')
        fixtures.append(expired)
        r = flask(ctx, 'GET', f'/consent/{legacy.stem}')
        rep.check('Consentrecord: oude statusterm dpv:ConsentStatusGiven leest terug als ConsentGiven / Actief',
                  r.status_code == 200 and 'ConsentGiven' in r.text and 'ConsentStatusGiven' not in r.text and 'Actief' in r.text,
                  '', f'status {r.status_code}')
        r = flask(ctx, 'GET', f'/consent/{expired.stem}')
        rep.check('Consentrecord: verstreken hasExpiry toont Verlopen (afgeleid, niet geschreven)',
                  r.status_code == 200 and 'Verlopen' in r.text and json.loads(expired.read_text(encoding='utf-8')).get('dpv:hasConsentStatus') == 'dpv:ConsentStatusGiven',
                  '', f'status {r.status_code}')
        r = flask(ctx, 'GET', '/consent')
        rep.check('Consentrecord: lijst toont beide fixtures met genormaliseerde status', r.status_code == 200 and legacy.stem in r.text and expired.stem in r.text,
                  '', f'status {r.status_code}')
    finally:
        for f in fixtures:
            if f.exists():
                f.unlink()
        for f in consent_files:
            if f and f.exists():
                flask(ctx, 'POST', f'/consent/{f.stem}/delete')
                if f.exists():
                    f.unlink()
        for f in request_files:
            for p in (f, f.with_name(f.stem + '.agreement.jsonld'), f.with_name(f.stem + '_response.json')):
                if p.exists():
                    p.unlink()
        for f in intentions:
            flask(ctx, 'POST', f'/intenties/{f.stem}/delete')
            for p in (f, f.with_name(f.stem + '.policy.jsonld')):
                if p.exists():
                    p.unlink()
        leftovers = [p for p in fixtures + [c for c in consent_files if c] if p.exists()]
        leftovers += [p for f in request_files for p in (f, f.with_name(f.stem + '.agreement.jsonld'), f.with_name(f.stem + '_response.json')) if p.exists()]
        leftovers += [p for f in intentions for p in (f, f.with_name(f.stem + '.policy.jsonld')) if p.exists()]
        rep.check('Consentrecord: testintenties, verzoeken, Agreements, responses, consentrecords en fixtures opgeruimd', not leftovers, '', str(leftovers))


def _git_short_hash() -> str:
    try:
        out = subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], cwd=ROOT, capture_output=True, text=True, timeout=5)
        return out.stdout.strip() if out.returncode == 0 else ''
    except OSError:
        return ''


def _nl_date(iso: str) -> str:
    try:
        return datetime.fromisoformat(str(iso)[:10]).strftime('%d-%m-%Y')
    except (TypeError, ValueError):
        return ''


def _make_accepted_case(ctx: Ctx, anon: requests.Session, description: str):
    """Open intentie aanmaken, activeren en laten accepteren; geeft (intentie-file, verzoek-file, consent-id)."""
    idir = ctx.pod_dir / 'intenties'
    vdir = ctx.pod_dir / 'verzoeken'
    before = {p.name for p in idir.glob('*.jsonld')} if idir.exists() else set()
    flask(ctx, 'POST', '/intenties/nieuw', data={'category': 'autoverzekering', 'description': description,
                                                 'validity': '2w', 'attributes': list(SCENARIO_ATTRIBUTES),
                                                 'purpose': 'quote_calculation', 'no_onward_transfer': '1', 'offer_mode': 'open'})
    new = [p for p in idir.glob('*.jsonld') if p.name not in before and not p.name.startswith('.')
           and not p.name.endswith('.policy.jsonld')]
    if len(new) != 1:
        return None, None, ''
    intention_file = new[0]
    flask(ctx, 'POST', f'/intenties/{intention_file.stem}/activate')
    before_v = {p.name for p in vdir.glob('*.jsonld')} if vdir.exists() else set()
    anon.post(f'{ctx.flask_base}/verzoek/intentie/{intention_file.stem}',
              data={'name': 'Jan Tester', 'organization': 'Verzekeraar X BV', 'email': 'jan@verzekeraar-x.test', 'accept_terms': 'yes'},
              timeout=TIMEOUT, allow_redirects=False)
    new_v = [p for p in vdir.glob('*.jsonld') if p.name not in before_v and not p.name.startswith('.')
             and not p.name.endswith('.agreement.jsonld')]
    if len(new_v) != 1:
        return intention_file, None, ''
    req = json.loads(new_v[0].read_text(encoding='utf-8'))
    return intention_file, new_v[0], str(req.get('mysolido:consent', '')).rsplit(':', 1)[-1]


def _cleanup_case(ctx: Ctx, intention_file, request_file, consent_id):
    if consent_id:
        p = ctx.pod_dir / 'toestemmingen' / f'{consent_id}.jsonld'
        if p.exists():
            p.unlink()
    if request_file:
        for p in (request_file, request_file.with_name(request_file.stem + '.agreement.jsonld'),
                  request_file.with_name(request_file.stem + '_response.json')):
            if p.exists():
                p.unlink()
    if intention_file:
        for p in (intention_file, intention_file.with_name(intention_file.stem + '.policy.jsonld')):
            if p.exists():
                p.unlink()


def phase_finishing(ctx: Ctx):
    """Afronding (subtaak 5): versieregel, aanbodlink, datumnotatie dd-mm-jjjj, naamveld, Agreement-uid na intrekken."""
    rep = ctx.report
    anon = requests.Session()
    git_hash = _git_short_hash()
    r = flask(ctx, 'GET', '/')
    rep.check('Afronding: versieregel in de voettekst met commit-hash en "lokaal"',
              r.status_code == 200 and 'id="app-version"' in r.text and 'lokaal' in r.text and (not git_hash or git_hash in r.text),
              git_hash, f'status {r.status_code}')
    profile = read_profile(ctx)
    if not all(expected_scenario_values(profile).values()):
        rep.skip('Afronding: profiel mist scenariowaarden, rest overgeslagen')
        return
    intention_file = request_file = None
    cid = ''
    try:
        intention_file, request_file, cid = _make_accepted_case(ctx, anon, 'Regressietest afronding')
        if not rep.check('Afronding: testketen (intentie, acceptatie, consentrecord) aangemaakt',
                         intention_file is not None and request_file is not None and bool(cid), '', 'keten onvolledig'):
            return
        iid, rid = intention_file.stem, request_file.stem
        rec = json.loads(intention_file.read_text(encoding='utf-8'))
        req = json.loads(request_file.read_text(encoding='utf-8'))
        r = flask(ctx, 'GET', f'/intenties/{iid}')
        rep.check('Afronding: aanbodlink met volledige URL en kopieerknop op de actieve intentie',
                  r.status_code == 200 and 'id="offer-link"' in r.text and f'{ctx.flask_base}/verzoek/intentie/{iid}' in r.text
                  and 'id="offer-link-copy"' in r.text, '', f'status {r.status_code}')
        rep.check('Afronding: intentiedetail toont Aangemaakt en Geldig tot als dd-mm-jjjj',
                  _nl_date(rec.get('schema:dateCreated')) in r.text and _nl_date(rec.get('schema:validThrough')) in r.text
                  and rec.get('schema:dateCreated', '')[:10] not in r.text.replace(_nl_date(rec.get('schema:dateCreated')), ''),
                  '', 'datum niet gevonden')
        r = flask(ctx, 'GET', '/intenties')
        rep.check('Afronding: intentielijst toont datums als dd-mm-jjjj',
                  r.status_code == 200 and _nl_date(rec.get('schema:validThrough')) in r.text and _nl_date(rec.get('schema:dateCreated')) in r.text,
                  '', f'status {r.status_code}')
        r = flask(ctx, 'GET', f'/verzoeken/{rid}')
        rep.check('Afronding: verzoekdetail toont de persoon in het naamveld en de datum als dd-mm-jjjj',
                  r.status_code == 200 and 'Jan Tester' in r.text and _nl_date(req.get('schema:dateCreated')) in r.text
                  and _nl_date(req.get('mysolido:validUntil')) in r.text, '', f'status {r.status_code}')
        rep.check('Afronding: schema:name van het verzoek is de persoon, rdfs:label de organisatie',
                  req.get('mysolido:requester', {}).get('schema:name') == 'Jan Tester'
                  and (req.get('mysolido:party') or {}).get('rdfs:label') == 'Verzekeraar X BV', '', json.dumps(req.get('mysolido:requester')))
        r = flask(ctx, 'GET', '/verzoeken')
        rep.check('Afronding: verzoeklijst toont de datum als dd-mm-jjjj', r.status_code == 200 and _nl_date(req.get('schema:dateCreated')) in r.text,
                  '', f'status {r.status_code}')
        r = anon.get(f"{ctx.flask_base}{req.get('mysolido:responseLink')}", timeout=TIMEOUT)
        rep.check('Afronding: responspagina toont "geldig tot" als dd-mm-jjjj',
                  r.status_code == 200 and _nl_date(req.get('mysolido:validUntil')) in r.text, '', f'status {r.status_code}')
        con = json.loads((ctx.pod_dir / 'toestemmingen' / f'{cid}.jsonld').read_text(encoding='utf-8'))
        r = flask(ctx, 'GET', '/consent')
        rep.check('Afronding: consentlijst toont aanmaakdatum en geldigheid als dd-mm-jjjj',
                  r.status_code == 200 and _nl_date(con.get('dct:created')) in r.text
                  and _nl_date(con['dpv:hasStorageCondition']['mysolido:validUntil']) in r.text, '', f'status {r.status_code}')
        r = flask(ctx, 'GET', f'/consent/{cid}')
        rep.check('Afronding: consentdetail toont datums als dd-mm-jjjj', r.status_code == 200 and _nl_date(con.get('dct:created')) in r.text,
                  '', f'status {r.status_code}')
        rep.check('Afronding: consentrecord gebruikt +00:00-notatie zonder Z en de id-datum van vandaag (UTC)',
                  str(con.get('dct:created', '')).endswith('+00:00') and cid.startswith(datetime.utcnow().strftime('%Y%m%d')),
                  '', f"{con.get('dct:created')} / {cid}")
        flask(ctx, 'POST', f'/consent/{cid}/withdraw')
        r = anon.get(f"{ctx.flask_base}{req.get('mysolido:responseLink')}", timeout=TIMEOUT)
        rep.check('Afronding: responspagina na intrekken toont de Agreement-uid',
                  r.status_code == 200 and 'Toestemming ingetrokken op' in r.text and req.get('mysolido:agreement', '') in r.text,
                  '', f'status {r.status_code}')
        rep.info('Afronding: REQUEST_RATE_LIMIT uit .env', 'alleen bij opstart gelezen; niet in deze run getest')
    finally:
        _cleanup_case(ctx, intention_file, request_file, cid)
        rep.check('Afronding: testketen opgeruimd',
                  not any(p.exists() for p in [x for x in (intention_file, request_file) if x]
                          + ([ctx.pod_dir / 'toestemmingen' / f'{cid}.jsonld'] if cid else [])), '', 'bestanden bestaan nog')


BRIDGE_TEST_PORT = 5001

# Opmaakelementen van de kluis (base.html) die op een pagina voor de wederpartij niet mogen voorkomen
NAV_MARKERS = ('class="header-nav"', 'class="bottom-nav"', 'bridge-banner', '/bridge-logout',
               'bell-link', 'id="sync-btn"', 'header-subtitle')

# Testwaarden voor url_map-parameters die niet uit de testketen komen
ROUTE_SAMPLE_VALUES = {'filename': 'css/style.css', 'folder_path': 'documenten',
                       'file_path': 'documenten/regressietest.txt', 'token': 'regressietest-token'}


def _app_routes():
    """url_map en BRIDGE_PUBLIC_ENDPOINTS uit app.py, gelezen in een apart proces (import, geen server)."""
    code = ("import sys, json; sys.argv = ['app.py']; import app; "
            "print('ROUTES ' + json.dumps({'rules': [{'endpoint': r.endpoint, 'rule': r.rule, "
            "'methods': sorted(m for m in r.methods if m not in ('HEAD', 'OPTIONS'))} "
            "for r in app.app.url_map.iter_rules()], 'public': sorted(app.BRIDGE_PUBLIC_ENDPOINTS)}))")
    env = dict(os.environ, PYTHONIOENCODING='utf-8')
    try:
        out = subprocess.run([sys.executable, '-c', code], cwd=ROOT, env=env, capture_output=True,
                             text=True, encoding='utf-8', errors='replace', timeout=60)
    except (subprocess.SubprocessError, OSError):
        return None
    for line in out.stdout.splitlines():
        if line.startswith('ROUTES '):
            return json.loads(line[7:])
    return None


def _route_path(rule: str, values: dict) -> str:
    """Concreet pad voor een url_map-regel: <naam> en <conv:naam> vervangen door een testwaarde."""
    return re.sub(r'<(?:[^<>:]+:)?([^<>]+)>',
                  lambda m: str(values.get(m.group(1)) or ROUTE_SAMPLE_VALUES.get(m.group(1)) or 'x'), rule)


def _to_login(resp) -> bool:
    return resp.status_code in REDIRECT and '/bridge-login' in resp.headers.get('Location', '')


def _check_route_table(rep, bridge_base: str, routes: dict, values: dict):
    """Elke route zonder sessie tegen de Bridge: redirect naar /bridge-login, tenzij op de openbare lijst.

    Een nieuwe route die niet op BRIDGE_PUBLIC_ENDPOINTS staat, hoort dicht te vallen; staat hij toch
    open, dan meldt de tweede check hem. Een naam op de lijst zonder route (dode regel) meldt de eerste.
    """
    public = set(routes['public'])
    endpoints = {r['endpoint'] for r in routes['rules']}
    dead = sorted(public - endpoints)
    rep.check('Bridge lokaal: routetabel: elke naam op de openbare lijst bestaat als endpoint',
              not dead, '', 'zonder route: ' + ', '.join(dead))
    closed_ok, closed_bad, open_ok, open_bad = [], [], [], []
    for r in routes['rules']:
        path = _route_path(r['rule'], values)
        method = 'GET' if 'GET' in r['methods'] else r['methods'][0]
        try:
            resp = requests.request(method, bridge_base + path, timeout=TIMEOUT, allow_redirects=False)
        except requests.RequestException as exc:
            (open_bad if r['endpoint'] in public else closed_bad).append(f'{method} {path}: {exc}')
            continue
        label = f'{method} {path} -> {resp.status_code}'
        if r['endpoint'] in public:
            (open_bad if _to_login(resp) else open_ok).append(label)
        else:
            (closed_ok if _to_login(resp) else closed_bad).append(label)
    rep.check(f'Bridge lokaal: routetabel: {len(closed_ok) + len(closed_bad)} routes buiten de openbare lijst '
              f'vallen zonder sessie dicht (redirect /bridge-login)',
              not closed_bad, '', 'open zonder sessie: ' + '; '.join(closed_bad))
    rep.check(f'Bridge lokaal: routetabel: {len(open_ok) + len(open_bad)} openbare routes antwoorden zonder sessie',
              not open_bad, '', 'toch naar inlog: ' + '; '.join(open_bad))
    rep.info(f'Bridge lokaal: routetabel: {len(routes["rules"])} routes in app.url_map, '
             f'{len(public)} openbare endpointnamen', ', '.join(sorted(public)))
    resp = requests.get(bridge_base + '/share-password/x', timeout=TIMEOUT, allow_redirects=False)
    rep.check('Bridge lokaal: dode prefix /share-password/ valt dicht', _to_login(resp), '', f'status {resp.status_code}')


def _check_public_pages_bare(rep, base: str, sess: requests.Session, pages, label: str):
    """De vier wederpartij-pagina's: 200, geen kluisnavigatie (NAV_MARKERS), wel de versieregel."""
    bad = []
    for path, name in pages:
        r = sess.get(base + path, timeout=TIMEOUT)
        found = [m for m in NAV_MARKERS if m in r.text]
        if r.status_code != 200 or found or 'id="app-version"' not in r.text:
            bad.append(f'{name} status {r.status_code} navigatie {found}')
    rep.check(f"Bridge lokaal: wederpartij-pagina's zonder navigatie-elementen, met versieregel ({label})",
              not bad, '', '; '.join(bad))


def _make_concept_intention(ctx: Ctx, description: str):
    """Intentie aanmaken zonder te activeren (status concept); geeft het intentiebestand of None."""
    idir = ctx.pod_dir / 'intenties'
    before = {p.name for p in idir.glob('*.jsonld')} if idir.exists() else set()
    flask(ctx, 'POST', '/intenties/nieuw', data={'category': 'autoverzekering', 'description': description,
                                                 'validity': '2w', 'attributes': list(SCENARIO_ATTRIBUTES),
                                                 'purpose': 'quote_calculation', 'no_onward_transfer': '1', 'offer_mode': 'open'})
    new = [p for p in idir.glob('*.jsonld') if p.name not in before and not p.name.startswith('.')
           and not p.name.endswith('.policy.jsonld')]
    return new[0] if len(new) == 1 else None


def phase_bridge_local(ctx: Ctx):
    """Bridge-modus lokaal (subtaak 5): tweede proces met --bridge op poort 5001 tegen dezelfde Pod.

    Sinds 21-09-2026 ook: lus over app.url_map (alles dicht behalve BRIDGE_PUBLIC_ENDPOINTS), Offer-JSON
    openbaar bij status actief en anders achter de inlog, en de wederpartij-pagina's zonder kluisnavigatie
    (lokaal, Bridge zonder login, Bridge met eigenaarssessie).
    """
    import bcrypt
    rep = ctx.report
    bridge_base = f'http://127.0.0.1:{BRIDGE_TEST_PORT}'
    try:
        requests.get(bridge_base + '/', timeout=2)
        rep.skip('Bridge lokaal: poort 5001 is al bezet, fase overgeslagen')
        return
    except requests.RequestException:
        pass
    anon = requests.Session()
    intention_file = request_file = concept_file = None
    cid = ''
    proc = None
    log_path = Path(os.environ.get('TEMP', str(ROOT))) / f'mysolido-bridge-test-{ctx.run_id}.log'
    try:
        intention_file, request_file, cid = _make_accepted_case(ctx, anon, 'Regressietest Bridge lokaal')
        if not rep.check('Bridge lokaal: testketen op de lokale app aangemaakt',
                         intention_file is not None and request_file is not None and bool(cid), '', 'keten onvolledig'):
            return
        iid, rid = intention_file.stem, request_file.stem
        password = 'bridge-' + secrets.token_hex(6)
        env = dict(os.environ)
        env.update({'MYSOLIDO_PORT': str(BRIDGE_TEST_PORT),
                    'BRIDGE_PASSWORD': bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode(),
                    'PYTHONIOENCODING': 'utf-8', 'FLASK_DEBUG': 'false'})
        log = open(log_path, 'w', encoding='utf-8')
        proc = subprocess.Popen([sys.executable, 'app.py', '--bridge'], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
        up = False
        for _ in range(30):
            time.sleep(1)
            try:
                r = requests.get(bridge_base + '/', timeout=2, allow_redirects=False)
                up = True
                break
            except requests.RequestException:
                if proc.poll() is not None:
                    break
        if not rep.check('Bridge lokaal: tweede proces gestart met --bridge op poort 5001', up, '', f'niet bereikbaar; log {log_path}'):
            return
        rep.check('Bridge lokaal: zonder login redirect naar bridge-login',
                  r.status_code in REDIRECT and 'bridge-login' in r.headers.get('Location', ''), '', f'status {r.status_code}')
        s = requests.Session()
        r = s.post(bridge_base + '/bridge-login', data={'password': password}, timeout=TIMEOUT, allow_redirects=False)
        rep.check('Bridge lokaal: inloggen met het Bridge-wachtwoord', r.status_code in REDIRECT, '', f'status {r.status_code}')
        r = s.get(f'{bridge_base}/intenties/{iid}', timeout=TIMEOUT)
        rep.check('Bridge lokaal: intentiedetail met Offer-kaart en "Geaccepteerd door", zonder knoppen',
                  r.status_code == 200 and 'Voorwaarden (ODRL-aanbod)' in r.text and 'Geaccepteerd door' in r.text
                  and f'/intenties/{iid}/withdraw' not in r.text and f'/intenties/{iid}/activate' not in r.text
                  and 'Voorwaarden opstellen' not in r.text and 'id="offer-link"' in r.text,
                  '', f'status {r.status_code}')
        r = s.get(f'{bridge_base}/consent/{cid}', timeout=TIMEOUT)
        rep.check('Bridge lokaal: consentdetail met 27560-tabel, zonder Intrekken',
                  r.status_code == 200 and 'ISO/IEC TS 27560' in r.text and f'/consent/{cid}/withdraw' not in r.text
                  and f'/verzoeken/{rid}"' not in r.text, '', f'status {r.status_code}')
        r = requests.get(f'{bridge_base}/verzoek/intentie/{iid}', timeout=TIMEOUT)
        rep.check('Bridge lokaal: acceptatieformulier toont voorwaarden zonder formulier, met Bridge-melding (zonder login)',
                  r.status_code == 200 and f'urn:mysolido:policy:intention:{iid}' in r.text and 'name="accept_terms"' not in r.text
                  and 'alleen lezen' in r.text, '', f'status {r.status_code}')
        vdir = ctx.pod_dir / 'verzoeken'
        before = {p.name for p in vdir.glob('*.jsonld')}
        r = requests.post(f'{bridge_base}/verzoek/intentie/{iid}', data={'name': 'X', 'email': 'x@y.test', 'accept_terms': 'yes'},
                          timeout=TIMEOUT, allow_redirects=False)
        rep.check('Bridge lokaal: POST accepteren geweigerd, geen nieuw verzoek',
                  r.status_code in REDIRECT and {p.name for p in vdir.glob('*.jsonld')} == before, '', f'status {r.status_code}')
        r = s.get(f'{bridge_base}/verzoeken', timeout=TIMEOUT)
        rep.check('Bridge lokaal: /verzoeken geeft 403', r.status_code == 403, '', f'status {r.status_code}')
        r1 = s.get(f'{bridge_base}/intenties/{iid}/policy.jsonld', timeout=TIMEOUT)
        r2 = s.get(f'{bridge_base}/verzoeken/{rid}/agreement.jsonld', timeout=TIMEOUT)
        rep.check('Bridge lokaal: policy.jsonld en agreement.jsonld als application/ld+json',
                  r1.status_code == 200 and 'ld+json' in r1.headers.get('Content-Type', '')
                  and r2.status_code == 200 and 'ld+json' in r2.headers.get('Content-Type', ''),
                  '', f'status {r1.status_code}/{r2.status_code}')
        r = s.get(bridge_base + '/', timeout=TIMEOUT)
        git_hash = _git_short_hash()
        rep.check('Bridge lokaal: versieregel met "Bridge"', r.status_code == 200 and 'id="app-version"' in r.text
                  and 'Bridge' in r.text.split('id="app-version"')[1][:400] and (not git_hash or git_hash in r.text),
                  git_hash, f'status {r.status_code}')

        # --- Routetabel (21-09-2026): elke route zonder sessie, dicht tenzij op BRIDGE_PUBLIC_ENDPOINTS ---
        token = str(json.loads(request_file.read_text(encoding='utf-8')).get('mysolido:statusToken', ''))
        routes = _app_routes()
        if rep.check('Bridge lokaal: routetabel: app.url_map en BRIDGE_PUBLIC_ENDPOINTS uit app.py gelezen',
                     routes is not None, '', 'import van app.py mislukt'):
            _check_route_table(rep, bridge_base, routes,
                               {'intention_id': iid, 'request_id': rid, 'consent_id': cid, 'status_token': token})

        # --- Wederpartij-pagina's: kale opmaak, lokaal en op de Bridge, ook met eigenaarssessie ---
        pages = [('/verzoek', 'verzoekformulier'), (f'/verzoek/intentie/{iid}', 'acceptatiepagina'),
                 (f'/verzoek/status/{token}', 'statuspagina'), (f'/verzoek/response/{token}', 'responspagina')]
        _check_public_pages_bare(rep, ctx.flask_base, requests.Session(), pages, 'lokaal')
        _check_public_pages_bare(rep, bridge_base, requests.Session(), pages, 'Bridge zonder login')
        _check_public_pages_bare(rep, bridge_base, s, pages, 'Bridge met eigenaarssessie')
        r = s.get(bridge_base + '/', timeout=TIMEOUT)
        rep.check('Bridge lokaal: kluispagina met eigenaarssessie behoudt de navigatie',
                  r.status_code == 200 and all(m in r.text for m in ('class="header-nav"', 'class="bottom-nav"', 'bridge-banner')),
                  '', f'status {r.status_code}')

        # --- Offer-JSON: openbaar bij status actief, anders achter de inlog ---
        r = requests.get(f'{bridge_base}/intenties/{iid}/policy.jsonld', timeout=TIMEOUT, allow_redirects=False)
        rep.check('Bridge lokaal: Offer-JSON van een actieve intentie zonder sessie als application/ld+json',
                  r.status_code == 200 and 'ld+json' in r.headers.get('Content-Type', '')
                  and f'urn:mysolido:policy:intention:{iid}' in r.text, '', f'status {r.status_code}')
        r = requests.get(f'{bridge_base}/intenties/bestaat-niet-{ctx.run_id}/policy.jsonld', timeout=TIMEOUT, allow_redirects=False)
        rep.check('Bridge lokaal: Offer-JSON van een onbekend id zonder sessie naar het inlogscherm', _to_login(r), '', f'status {r.status_code}')
        concept_file = _make_concept_intention(ctx, 'Regressietest Bridge concept')
        if rep.check('Bridge lokaal: concept-intentie op de lokale app aangemaakt', concept_file is not None, '', 'geen bestand'):
            r = requests.get(f'{bridge_base}/intenties/{concept_file.stem}/policy.jsonld', timeout=TIMEOUT, allow_redirects=False)
            rep.check('Bridge lokaal: Offer-JSON van een concept-intentie zonder sessie naar het inlogscherm', _to_login(r), '', f'status {r.status_code}')
            r = s.get(f'{bridge_base}/intenties/{concept_file.stem}/policy.jsonld', timeout=TIMEOUT, allow_redirects=False)
            rep.check('Bridge lokaal: Offer-JSON van een concept-intentie met eigenaarssessie niet naar het inlogscherm',
                      not _to_login(r) and r.status_code in (200, 404), '', f'status {r.status_code}')
        flask(ctx, 'POST', f'/intenties/{iid}/withdraw')
        withdrawn = json.loads(intention_file.read_text(encoding='utf-8')).get('mysolido:status') == 'ingetrokken'
        r = requests.get(f'{bridge_base}/intenties/{iid}/policy.jsonld', timeout=TIMEOUT, allow_redirects=False)
        rep.check('Bridge lokaal: Offer-JSON na intrekken van de intentie zonder sessie naar het inlogscherm',
                  withdrawn and _to_login(r), '', f'ingetrokken {withdrawn}, status {r.status_code}')
        r = s.get(f'{bridge_base}/intenties/{iid}/policy.jsonld', timeout=TIMEOUT, allow_redirects=False)
        rep.check('Bridge lokaal: Offer-JSON na intrekken met eigenaarssessie als application/ld+json',
                  r.status_code == 200 and 'ld+json' in r.headers.get('Content-Type', ''), '', f'status {r.status_code}')
    finally:
        if proc is not None:
            proc.kill()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                pass
            try:
                requests.get(bridge_base + '/', timeout=2)
                rep.fail('Bridge lokaal: tweede proces gestopt', 'poort 5001 antwoordt nog')
            except requests.RequestException:
                rep.ok('Bridge lokaal: tweede proces gestopt')
        _cleanup_case(ctx, intention_file, request_file, cid)
        _cleanup_case(ctx, concept_file, None, '')


# --- main --------------------------------------------------------------------------------

def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    parser = argparse.ArgumentParser(description='MySolido regression test against a running CSS + Flask stack.')
    parser.add_argument('--scenario', choices=['U', 'N'], default='U', help='U = upgrade path (default), N = new installation')
    parser.add_argument('--phase', choices=['all', 'bridge', 'persist', 'demo'], default='all',
                        help='demo = alleen seed, profielvelden en intentie (MyTerms-demo)')
    parser.add_argument('--out', help='write results as JSON to this file')
    parser.add_argument('--keep', action='store_true', help='do not remove test data afterwards')
    parser.add_argument('--keep-persist', action='store_true',
                        help='leave regressietest/acl-map and policy-map behind for a later --phase persist')
    parser.add_argument('--css-base', help='override CSS base URL (default: CSS_BASE_URL from .env)')
    parser.add_argument('--flask-base', default='http://127.0.0.1:5000')
    parser.add_argument('--bridge-password', help='plaintext Bridge password, only for --phase bridge')
    args = parser.parse_args()

    ctx = Ctx(args)
    started = datetime.now()
    print(f'MySolido regressietest {started:%Y-%m-%d %H:%M} -- scenario {ctx.scenario}, fase {args.phase}, '
          f'CSS {ctx.css_base} ({css_version()}), Flask {ctx.flask_base}, Pod {ctx.pod_url}')

    if args.phase == 'bridge':
        if not args.bridge_password:
            parser.error('--bridge-password is required for --phase bridge')
        run_phase(ctx, 'Bridge read-only modus', phase_bridge_mode, args.bridge_password)
    elif args.phase == 'persist':
        run_phase(ctx, 'Persistentie van ACL en policy na herstart', phase_persist_check, args.keep_persist)
    elif args.phase == 'demo':
        run_phase(ctx, 'Demodata (seed_demo.py)', phase_seed)
        run_phase(ctx, 'Profielvelden MyTerms-demo', phase_profile_fields)
        run_phase(ctx, 'Intentie met per-veldselectie', phase_intention)
        run_phase(ctx, 'Intentiepolicy (ODRL-Offer)', phase_intention_policy)
        run_phase(ctx, 'Acceptatie en Agreement', phase_acceptance)
        run_phase(ctx, 'Consentrecord (27560)', phase_consent_record)
        run_phase(ctx, 'Afronding (versieregel, aanbodlink, datums)', phase_finishing)
        run_phase(ctx, 'Bridge-modus lokaal (tweede proces, poort 5001)', phase_bridge_local)
    else:
        run_phase(ctx, 'Preflight', phase_preflight)
        account = run_phase(ctx, 'Accountcreatie en test-Pod (CSS account-API)', phase_account)
        run_phase(ctx, 'WebID en credentials', phase_webid_credentials)
        content = run_phase(ctx, 'Bestanden en roundtrip Flask <-> CSS', phase_files)
        run_phase(ctx, 'Identifier-normalisatie', phase_normalisation)
        run_phase(ctx, 'WAC / ACL', phase_wac, account)
        run_phase(ctx, 'Deellinks', phase_share_link)
        run_phase(ctx, 'ODRL-beleid', phase_policy)
        run_phase(ctx, 'Toestemmingen en consentrequests', phase_consent_request)
        run_phase(ctx, 'Demodata (seed_demo.py)', phase_seed)
        run_phase(ctx, 'Profielvelden MyTerms-demo', phase_profile_fields)
        run_phase(ctx, 'Intentie met per-veldselectie', phase_intention)
        run_phase(ctx, 'Intentiepolicy (ODRL-Offer)', phase_intention_policy)
        run_phase(ctx, 'Acceptatie en Agreement', phase_acceptance)
        run_phase(ctx, 'Consentrecord (27560)', phase_consent_record)
        run_phase(ctx, 'Afronding (versieregel, aanbodlink, datums)', phase_finishing)
        run_phase(ctx, 'Bridge-modus lokaal (tweede proces, poort 5001)', phase_bridge_local)
        run_phase(ctx, 'Backup en restore', phase_backup_restore, content)
        run_phase(ctx, 'Flask /debug (HTTP-laag)', phase_debug)
        run_phase(ctx, 'Probes 7.2.0-changelog', phase_probes)
        run_phase(ctx, 'Bridge-sync module', phase_bridge_sync)
        run_phase(ctx, 'Persistentie: ACL- en policy-map aanmaken', phase_persist_setup)
        if args.keep:
            ctx.report.skip('Opruimen', '--keep opgegeven')
        else:
            run_phase(ctx, 'Opruimen', phase_cleanup, account, args.keep_persist)

    counts = ctx.report.counts()
    print(f'\nResultaat: {counts["PASS"]} geslaagd, {counts["FAIL"]} gefaald, '
          f'{counts["SKIP"]} niet automatiseerbaar, {counts["INFO"]} info '
          f'({time.time() - started.timestamp():.0f}s)')
    if args.out:
        out = {'started': started.isoformat(timespec='seconds'), 'scenario': ctx.scenario, 'phase': args.phase,
               'css_version': css_version(), 'css_base': ctx.css_base, 'pod_url': ctx.pod_url,
               'counts': counts, 'items': ctx.report.items}
        Path(args.out).write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding='utf-8')
        print(f'Resultaten opgeslagen in {args.out}')
    sys.exit(1 if counts['FAIL'] else 0)


if __name__ == '__main__':
    main()
