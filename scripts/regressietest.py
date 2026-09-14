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
            for name in ('_trash', 'toestemmingen', 'verzoeken', '.mysolido', TEST_FOLDER)
        }

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
                  and rec.get('dpv:hasConsentStatus') == 'dpv:ConsentStatusGiven',
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
        rep.check('Toestemming: intrekken zet status Withdrawn',
                  rec.get('dpv:hasConsentStatus') == 'dpv:ConsentStatusWithdrawn', '', rec.get('dpv:hasConsentStatus'))
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
    for name in ('_trash', 'toestemmingen', 'verzoeken', '.mysolido'):
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


# --- main --------------------------------------------------------------------------------

def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    parser = argparse.ArgumentParser(description='MySolido regression test against a running CSS + Flask stack.')
    parser.add_argument('--scenario', choices=['U', 'N'], default='U', help='U = upgrade path (default), N = new installation')
    parser.add_argument('--phase', choices=['all', 'bridge', 'persist'], default='all')
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
