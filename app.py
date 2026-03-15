import re
import os
import io
import zipfile
from datetime import datetime
from email.utils import parsedate_to_datetime
from urllib.parse import unquote
from flask import Flask, render_template, request, redirect, url_for, flash, Response
import requests
import base64
from dotenv import load_dotenv
from audit import log_action, get_audit_log
from shares import add_share, remove_share, get_all_shares, get_shares_for_resource, check_expired_shares
from trash import move_to_trash, restore_from_trash, permanent_delete, get_all_trash, cleanup_expired
from notifications import add_notification, get_all_notifications, get_unread_count, mark_as_read, mark_all_read

load_dotenv()

app = Flask(__name__)
app.secret_key = 'mysolido-dev-key-2026'

# === CONFIGURATIE ===
CLIENT_ID = os.getenv('CLIENT_ID')
CLIENT_SECRET = os.getenv('CLIENT_SECRET')
CSS_BASE_URL = os.getenv('CSS_BASE_URL', 'http://localhost:3000')
SOLID_POD_URL = os.getenv('SOLID_POD_URL', 'http://localhost:3000/wim/')
OWNER_WEBID = CSS_BASE_URL.rstrip('/') + '/wim/profile/card#me'

# Viewable file types for inline display
VIEWABLE_TYPES = {
    '.pdf': 'application/pdf',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.png': 'image/png',
    '.gif': 'image/gif',
    '.webp': 'image/webp',
    '.txt': 'text/plain',
    '.html': 'text/html',
    '.json': 'application/json',
    '.csv': 'text/csv',
    '.mp3': 'audio/mpeg',
    '.wav': 'audio/wav',
    '.mp4': 'video/mp4',
    '.webm': 'video/webm',
}

# Default folders to create on init
DEFAULT_FOLDERS = [
    'identiteit', 'medisch', 'financieel', 'wonen', 'zakelijk',
    'werk', 'voertuigen', 'juridisch', 'media', 'wachtwoorden',
    'gezin', 'abonnementen', 'inbox', 'verzekeringen',
    'huisdieren', 'opleiding', 'reizen', 'digitaal-testament',
    'persoonlijk', 'projecten',
]

# Folder styles with icon name and colors for light/dark themes
FOLDER_STYLES = {
    'identiteit':         {'icon': 'shield',       'color': '#6366f1', 'color_dark': '#818cf8'},
    'medisch':            {'icon': 'heart',        'color': '#ef4444', 'color_dark': '#f87171'},
    'financieel':         {'icon': 'banknotes',    'color': '#f59e0b', 'color_dark': '#fbbf24'},
    'wonen':              {'icon': 'house',        'color': '#10b981', 'color_dark': '#34d399'},
    'zakelijk':           {'icon': 'briefcase',    'color': '#3b82f6', 'color_dark': '#60a5fa'},
    'werk':               {'icon': 'tie',          'color': '#8b5cf6', 'color_dark': '#a78bfa'},
    'voertuigen':         {'icon': 'car',          'color': '#f97316', 'color_dark': '#fb923c'},
    'juridisch':          {'icon': 'gavel',        'color': '#64748b', 'color_dark': '#94a3b8'},
    'media':              {'icon': 'camera',       'color': '#ec4899', 'color_dark': '#f472b6'},
    'wachtwoorden':       {'icon': 'key',          'color': '#eab308', 'color_dark': '#facc15'},
    'gezin':              {'icon': 'family',       'color': '#14b8a6', 'color_dark': '#2dd4bf'},
    'abonnementen':       {'icon': 'clipboard',    'color': '#a855f7', 'color_dark': '#c084fc'},
    'inbox':              {'icon': 'inbox',        'color': '#0ea5e9', 'color_dark': '#38bdf8'},
    'verzekeringen':      {'icon': 'shield_check', 'color': '#22c55e', 'color_dark': '#4ade80'},
    'huisdieren':         {'icon': 'paw',          'color': '#c2410c', 'color_dark': '#fdba74'},
    'opleiding':          {'icon': 'graduation',   'color': '#3730a3', 'color_dark': '#a5b4fc'},
    'reizen':             {'icon': 'plane',        'color': '#0f766e', 'color_dark': '#5eead4'},
    'digitaal-testament': {'icon': 'testament',    'color': '#6b21a8', 'color_dark': '#c084fc'},
    'persoonlijk':        {'icon': 'star',         'color': '#57534e', 'color_dark': '#d6d3d1'},
    'projecten':          {'icon': 'wrench',       'color': '#4d7c0f', 'color_dark': '#bef264'},
}


@app.context_processor
def inject_globals():
    """Inject global template variables"""
    nav_map = {
        'index': 'kluis',
        'browse': 'kluis',
        'search': 'zoeken',
        'shares_overview': 'gedeeld',
        'trash_overview': 'prullenbak',
        'audit': 'logboek',
        'profile': 'profiel',
        'settings': 'profiel',
        'notifications_page': '',
    }
    active = nav_map.get(request.endpoint, '')
    return {
        'folder_styles': FOLDER_STYLES,
        'unread_count': get_unread_count(),
        'active_nav': active,
    }


def get_access_token():
    """Verkrijg een access token via client credentials"""
    auth = base64.b64encode(f'{CLIENT_ID}:{CLIENT_SECRET}'.encode()).decode()
    response = requests.post(
        f'{CSS_BASE_URL}/.oidc/token',
        data={'grant_type': 'client_credentials', 'scope': 'webid'},
        headers={
            'Authorization': f'Basic {auth}',
            'Content-Type': 'application/x-www-form-urlencoded'
        }
    )

    if response.status_code == 200:
        return response.json().get('access_token')
    else:
        print(f"Token ophalen mislukt: {response.status_code} - {response.text}")
        return None


def pod_request(method, url, **kwargs):
    """Doe een geauthenticeerde request naar de pod"""
    token = get_access_token()
    if token is None:
        return None

    # Voeg headers samen
    headers = kwargs.pop('headers', {})
    headers['Authorization'] = f'Bearer {token}'

    if method == 'GET':
        return requests.get(url, headers=headers, **kwargs)
    elif method == 'HEAD':
        return requests.head(url, headers=headers, **kwargs)
    elif method == 'PUT':
        return requests.put(url, headers=headers, **kwargs)
    elif method == 'DELETE':
        return requests.delete(url, headers=headers, **kwargs)


def container_exists(url):
    """Check if a container (folder) already exists"""
    response = pod_request('GET', url, headers={'Accept': 'text/turtle'})
    return response is not None and response.status_code == 200


def create_container(url):
    """Create a container (folder) in the pod"""
    return pod_request('PUT', url,
        headers={
            'Content-Type': 'text/turtle',
            'Link': '<http://www.w3.org/ns/ldp#BasicContainer>; rel="type"'
        },
        data=''
    )


def get_folder_icon(folder_name):
    """Get the icon name for a folder"""
    name_lower = folder_name.lower()
    style = FOLDER_STYLES.get(name_lower)
    if style:
        return style['icon']
    return 'folder'


def parse_container_contents(turtle_text, base_url):
    """Parse Turtle response to extract container contents"""
    items = []

    contains_pattern = re.compile(r'ldp:contains\s+(.+?)\.\s*$', re.DOTALL | re.MULTILINE)
    contains_matches = contains_pattern.findall(turtle_text)

    resources = []
    for match in contains_matches:
        resources.extend(re.findall(r'<([^>]+)>', match))

    for resource in resources:
        if not resource.startswith('http'):
            full_url = base_url.rstrip('/') + '/' + resource.lstrip('/')
        else:
            full_url = resource
        name = unquote(resource.rstrip('/').split('/')[-1])
        is_folder = resource.endswith('/')
        icon = get_folder_icon(name) if is_folder else 'file'
        items.append({
            'name': name,
            'url': full_url,
            'is_folder': is_folder,
            'icon': icon,
        })
    items.sort(key=lambda x: (not x['is_folder'], x['name'].lower()))

    # Fetch metadata (size, modified) for files via HEAD requests (max 20)
    file_count = 0
    for item in items:
        if item['is_folder']:
            item['size'] = ''
            item['modified'] = ''
            continue
        file_count += 1
        if file_count <= 20:
            try:
                head = pod_request('HEAD', item['url'])
                if head and head.status_code == 200:
                    # Size
                    cl = head.headers.get('Content-Length')
                    item['size'] = format_size(int(cl)) if cl else '—'
                    # Date
                    lm = head.headers.get('Last-Modified')
                    if lm:
                        item['modified'] = format_date_nl(lm)
                    else:
                        item['modified'] = '—'
                else:
                    item['size'] = '—'
                    item['modified'] = '—'
            except Exception:
                item['size'] = '—'
                item['modified'] = '—'
        else:
            item['size'] = '—'
            item['modified'] = '—'

    return items


def build_breadcrumbs(folder_path):
    """Build breadcrumb navigation from a folder path"""
    crumbs = [{'name': 'Pod', 'path': ''}]
    if folder_path:
        parts = [p for p in folder_path.split('/') if p]
        for i, part in enumerate(parts):
            path = '/'.join(parts[:i + 1])
            crumbs.append({'name': part, 'path': path})
    return crumbs


def normalize_folder_name(name):
    """Normalize a folder name: lowercase, hyphens instead of spaces, no special chars"""
    name = name.strip().lower()
    name = name.replace(' ', '-')
    name = re.sub(r'[^a-z0-9\-]', '', name)
    name = re.sub(r'-+', '-', name).strip('-')
    return name


@app.route('/')
def index():
    """Toon de inhoud van de pod root"""
    return browse_folder('')


@app.route('/browse/<path:folder_path>')
def browse(folder_path):
    """Toon de inhoud van een map in de pod"""
    return browse_folder(folder_path)


def get_all_folders():
    """Geeft lijst van alle hoofdmappen met icoon en label voor de upload-dropdown"""
    return [
        {'name': name, 'icon': FOLDER_STYLES.get(name, {}).get('icon', 'folder'), 'label': name.capitalize()}
        for name in DEFAULT_FOLDERS
    ]


def get_move_folders(folder_path, items):
    """Bouw de mappenlijst voor de verplaats-dropdown"""
    folders = []
    subfolders = [item for item in items if item['is_folder']]

    for name in DEFAULT_FOLDERS:
        style = FOLDER_STYLES.get(name, {})
        folders.append({'value': name, 'label': name.capitalize(), 'indent': 0})
        if folder_path == name or folder_path.startswith(name + '/'):
            for sub in subfolders:
                sub_path = folder_path + '/' + sub['name']
                folders.append({'value': sub_path, 'label': sub['name'], 'indent': 1})
    return folders


def get_recent_files(limit=5):
    """Get recent file uploads from audit log"""
    log = get_audit_log('upload', limit=limit)
    return log


def sort_items(items, sort_by):
    """Sort items: folders always first, then files by chosen criterion"""
    folders = [i for i in items if i['is_folder']]
    files = [i for i in items if not i['is_folder']]
    if sort_by == 'name-desc':
        files.sort(key=lambda x: x['name'].lower(), reverse=True)
    elif sort_by == 'date-desc':
        files.reverse()
    elif sort_by == 'date-asc':
        pass  # server order is already oldest first
    else:  # name-asc (default)
        files.sort(key=lambda x: x['name'].lower())
    return folders + files


def is_pod_empty(items):
    """Check if the pod is essentially empty (only system files like profile/, README)"""
    SYSTEM_NAMES = {'profile', 'README', '.acl', '_trash'}
    user_items = [i for i in items if i['name'] not in SYSTEM_NAMES]
    return len(user_items) == 0


def browse_folder(folder_path):
    """Shared logic for browsing a folder"""
    # Check for expired shares and auto-revoke
    expired = check_expired_shares()
    for s in expired:
        write_acl(s['resource_url'])
        display_webid = 'iedereen (openbaar)' if s['webid'] == 'public' else s['webid']
        resource_name = s['resource_url'].rstrip('/').split('/')[-1]
        flash(f'Toegang van {display_webid} tot "{resource_name}" is verlopen en ingetrokken', 'success')
        log_action('revoke_expired', {'resource': s.get('resource_path', ''), 'webid': s['webid']})
        add_notification('share_expired', f'Toegang van {display_webid} tot "{resource_name}" is verlopen')

    folder_path = folder_path.strip('/')
    sort_by = request.args.get('sort', 'name-asc')
    if folder_path:
        container_url = SOLID_POD_URL + folder_path + '/'
    else:
        container_url = SOLID_POD_URL

    try:
        response = pod_request('GET', container_url, headers={'Accept': 'text/turtle'})
        if response and response.status_code == 200:
            items = parse_container_contents(response.text, container_url)

            # Show welcome page if pod root is empty
            if not folder_path and is_pod_empty(items):
                return render_template('welcome.html', pod_url=SOLID_POD_URL)

            items = sort_items(items, sort_by)
            breadcrumbs = build_breadcrumbs(folder_path)
            parts = [p for p in folder_path.split('/') if p]
            parent_path = '/'.join(parts[:-1]) if parts else None
            move_folders = get_move_folders(folder_path, items)
            # Count stats for dashboard
            file_count = sum(1 for i in items if not i['is_folder'])
            folder_count = sum(1 for i in items if i['is_folder'])
            recent_files = get_recent_files() if not folder_path else []
            return render_template('index.html',
                items=items,
                pod_url=SOLID_POD_URL,
                folder_path=folder_path,
                breadcrumbs=breadcrumbs,
                parent_path=parent_path,
                all_folders=get_all_folders(),
                move_folders=move_folders,
                file_count=file_count,
                folder_count=folder_count,
                recent_files=recent_files,
                default_folders=DEFAULT_FOLDERS,
                current_sort=sort_by,
            )
        elif response:
            flash(f'Kon map niet laden: {response.status_code}', 'error')
        else:
            flash('Authenticatie mislukt. Controleer client credentials.', 'error')
    except requests.ConnectionError:
        flash('CSS server niet bereikbaar. Draait hij op poort 3000?', 'error')

    breadcrumbs = build_breadcrumbs(folder_path)
    parts = [p for p in folder_path.split('/') if p]
    parent_path = '/'.join(parts[:-1]) if parts else None
    return render_template('index.html',
        items=[],
        pod_url=SOLID_POD_URL,
        folder_path=folder_path,
        breadcrumbs=breadcrumbs,
        parent_path=parent_path,
        all_folders=get_all_folders(),
        move_folders=get_move_folders(folder_path, []),
        file_count=0,
        folder_count=0,
        recent_files=[],
        default_folders=DEFAULT_FOLDERS,
        current_sort=sort_by,
    )


@app.route('/upload', methods=['POST'])
def upload():
    """Upload een bestand naar de gekozen map"""
    folder_path = request.form.get('upload_folder', '').strip('/')

    if 'file' not in request.files:
        flash('Geen bestand geselecteerd', 'error')
        return redirect_to_folder(folder_path)

    file = request.files['file']
    if file.filename == '':
        flash('Geen bestand geselecteerd', 'error')
        return redirect_to_folder(folder_path)

    if folder_path:
        upload_url = SOLID_POD_URL + folder_path + '/' + file.filename
    else:
        upload_url = SOLID_POD_URL + file.filename

    content_type = file.content_type or 'application/octet-stream'

    response = pod_request('PUT', upload_url,
        data=file.read(),
        headers={'Content-Type': content_type}
    )

    if response and response.status_code in [200, 201, 205]:
        flash(f'"{file.filename}" succesvol geupload!', 'success')
        log_action('upload', {'file': file.filename, 'folder': folder_path or 'root'})
    elif response:
        flash(f'Upload mislukt: {response.status_code}', 'error')
    else:
        flash('Upload mislukt: authenticatie error', 'error')

    return redirect_to_folder(folder_path)


@app.route('/delete', methods=['POST'])
def delete():
    """Verplaats een resource naar de prullenbak"""
    resource_url = request.form.get('resource_url')
    folder_path = request.form.get('folder_path', '').strip('/')

    if not resource_url:
        flash('Geen resource opgegeven', 'error')
        return redirect_to_folder(folder_path)

    name = resource_url.rstrip('/').split('/')[-1]
    is_folder = resource_url.endswith('/')

    if is_folder:
        # Folders: direct verwijderen (niet naar prullenbak)
        response = pod_request('DELETE', resource_url)
        if response and response.status_code in [200, 204, 205]:
            flash(f'Map "{name}" verwijderd', 'success')
            log_action('delete', {'resource': name, 'folder': folder_path or 'root'})
        elif response:
            flash(f'Verwijderen mislukt: {response.status_code}', 'error')
        else:
            flash('Verwijderen mislukt: authenticatie error', 'error')
        return redirect_to_folder(folder_path)

    # Files: verplaats naar prullenbak
    # Step 1: Ensure _trash/ container exists
    trash_container = SOLID_POD_URL + '_trash/'
    if not container_exists(trash_container):
        create_container(trash_container)

    # Step 2: Download the file
    get_response = pod_request('GET', resource_url)
    if not get_response or get_response.status_code != 200:
        flash(f'Verwijderen mislukt: kon bestand niet ophalen', 'error')
        return redirect_to_folder(folder_path)

    content_type = get_response.headers.get('Content-Type', 'application/octet-stream')

    # Step 3: Generate trash entry
    import uuid
    trash_id = uuid.uuid4().hex[:12]
    trash_filename = f'{trash_id}_{name}'
    trash_url = trash_container + trash_filename

    # Step 4: Upload to _trash/
    put_response = pod_request('PUT', trash_url,
        data=get_response.content,
        headers={'Content-Type': content_type}
    )
    if not put_response or put_response.status_code not in [200, 201, 205]:
        flash(f'Verplaatsen naar prullenbak mislukt', 'error')
        return redirect_to_folder(folder_path)

    # Step 5: Delete original
    del_response = pod_request('DELETE', resource_url)
    if not del_response or del_response.status_code not in [200, 204, 205]:
        flash(f'Let op: "{name}" is naar prullenbak gekopieerd maar het origineel kon niet verwijderd worden', 'error')
        return redirect_to_folder(folder_path)

    # Step 6: Record in trash.json
    resource_path = folder_path + '/' + name if folder_path else name
    move_to_trash(resource_url, resource_path, name, folder_path or 'root', trash_url)

    flash(f'"{name}" naar prullenbak verplaatst', 'success')
    log_action('trash', {'resource': name, 'folder': folder_path or 'root'})
    return redirect_to_folder(folder_path)


@app.route('/create-folder', methods=['POST'])
def create_folder_route():
    """Maak een nieuwe submap aan in de huidige locatie"""
    folder_path = request.form.get('folder_path', '').strip('/')
    folder_name = request.form.get('folder_name', '')

    normalized = normalize_folder_name(folder_name)
    if not normalized:
        flash('Ongeldige mapnaam', 'error')
        return redirect_to_folder(folder_path)

    if folder_path:
        new_folder_url = SOLID_POD_URL + folder_path + '/' + normalized + '/'
    else:
        new_folder_url = SOLID_POD_URL + normalized + '/'

    if container_exists(new_folder_url):
        flash(f'Map "{normalized}" bestaat al', 'error')
        return redirect_to_folder(folder_path)

    response = create_container(new_folder_url)

    if response and response.status_code in [200, 201, 205]:
        flash(f'Map "{normalized}" aangemaakt!', 'success')
        log_action('create_folder', {'name': normalized, 'path': folder_path or 'root'})
    elif response:
        flash(f'Map aanmaken mislukt: {response.status_code}', 'error')
    else:
        flash('Map aanmaken mislukt: authenticatie error', 'error')

    return redirect_to_folder(folder_path)


@app.route('/move', methods=['POST'])
def move():
    """Verplaats een bestand naar een andere map"""
    resource_url = request.form.get('resource_url', '')
    target_folder = request.form.get('target_folder', '').strip('/')
    folder_path = request.form.get('folder_path', '').strip('/')
    filename = resource_url.rstrip('/').split('/')[-1]

    if not resource_url or not filename:
        flash('Geen bestand opgegeven', 'error')
        return redirect_to_folder(folder_path)

    if target_folder:
        target_url = SOLID_POD_URL + target_folder + '/' + filename
    else:
        target_url = SOLID_POD_URL + filename

    if target_url == resource_url:
        flash('Bestand staat al in deze map', 'error')
        return redirect_to_folder(folder_path)

    get_response = pod_request('GET', resource_url)
    if not get_response or get_response.status_code != 200:
        status = get_response.status_code if get_response else 'geen response'
        flash(f'Verplaatsen mislukt: kon bestand niet ophalen ({status})', 'error')
        return redirect_to_folder(folder_path)

    content_type = get_response.headers.get('Content-Type', 'application/octet-stream')

    put_response = pod_request('PUT', target_url,
        data=get_response.content,
        headers={'Content-Type': content_type}
    )
    if not put_response or put_response.status_code not in [200, 201, 205]:
        status = put_response.status_code if put_response else 'geen response'
        flash(f'Verplaatsen mislukt: kon bestand niet opslaan ({status})', 'error')
        return redirect_to_folder(folder_path)

    del_response = pod_request('DELETE', resource_url)
    if not del_response or del_response.status_code not in [200, 204, 205]:
        flash(f'Let op: "{filename}" is gekopieerd maar het origineel kon niet verwijderd worden', 'error')
        return redirect_to_folder(folder_path)

    target_label = target_folder if target_folder else 'Pod root'
    flash(f'"{filename}" verplaatst naar {target_label}', 'success')
    log_action('move', {'file': filename, 'from': folder_path or 'root', 'to': target_folder or 'root'})
    return redirect_to_folder(folder_path)


def search_pod(container_url, query, path='', depth=0, max_depth=5):
    """Recursively search the pod for files matching the query"""
    if depth >= max_depth:
        return []

    results = []
    response = pod_request('GET', container_url, headers={'Accept': 'text/turtle'})
    if not response or response.status_code != 200:
        return results

    items = parse_container_contents(response.text, container_url)
    for item in items:
        if item['is_folder']:
            sub_path = path + '/' + item['name'] if path else item['name']
            sub_url = item['url']
            results.extend(search_pod(sub_url, query, sub_path, depth + 1, max_depth))
        else:
            if query.lower() in item['name'].lower():
                file_path = path + '/' + item['name'] if path else item['name']
                results.append({
                    'name': item['name'],
                    'path': file_path,
                    'folder_path': path,
                    'url': item['url'],
                    'icon': item['icon'],
                })
    return results


@app.route('/search')
def search():
    """Search for files across all folders"""
    query = request.args.get('q', '').strip()
    results = []
    if query:
        try:
            results = search_pod(SOLID_POD_URL, query)
            log_action('search', {'query': query, 'results': len(results)})
        except requests.ConnectionError:
            flash('CSS server niet bereikbaar. Draait hij op poort 3000?', 'error')

    return render_template('search.html',
        query=query,
        results=results,
        pod_url=SOLID_POD_URL,
        all_folders=get_all_folders(),
    )


@app.route('/view/<path:file_path>')
def view_file(file_path):
    """View a file inline in the browser"""
    file_url = SOLID_POD_URL + file_path
    response = pod_request('GET', file_url)

    if not response or response.status_code != 200:
        flash('Bestand kon niet worden geopend', 'error')
        return redirect(url_for('index'))

    filename = file_path.split('/')[-1]
    ext = os.path.splitext(filename)[1].lower()

    if ext in ('.mp3', '.wav', '.mp4', '.webm') and not request.args.get('raw'):
        folder_path = '/'.join(file_path.split('/')[:-1])
        return render_template('view.html',
            filename=filename,
            file_path=file_path,
            folder_path=folder_path,
            media_type='audio' if ext in ('.mp3', '.wav') else 'video',
            content_type=VIEWABLE_TYPES.get(ext, 'application/octet-stream'),
        )

    if ext in VIEWABLE_TYPES:
        mime = VIEWABLE_TYPES[ext]
        print(f"[view] {filename} → inline, Content-Type: {mime}")
        resp = Response(response.content)
        resp.headers['Content-Type'] = mime
        resp.headers['Content-Disposition'] = f'inline; filename="{filename}"'
        return resp

    print(f"[view] {filename} → attachment")
    resp = Response(response.content)
    resp.headers['Content-Type'] = response.headers.get('Content-Type', 'application/octet-stream')
    resp.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
    return resp


@app.route('/download/<path:file_path>')
def download_file(file_path):
    """Force download a file from the pod"""
    file_url = SOLID_POD_URL + file_path
    response = pod_request('GET', file_url)

    if not response or response.status_code != 200:
        flash('Bestand kon niet worden gedownload', 'error')
        return redirect(url_for('index'))

    content_type = response.headers.get('Content-Type', 'application/octet-stream')
    filename = file_path.split('/')[-1]

    return Response(
        response.content,
        content_type=content_type,
        headers={'Content-Disposition': f'attachment; filename="{filename}"'}
    )


def build_acl_content(resource_url):
    """Build ACL Turtle content from all active shares for this resource"""
    is_container = resource_url.endswith('/')
    shares = get_shares_for_resource(resource_url)

    acl = '@prefix acl: <http://www.w3.org/ns/auth/acl#>.\n'
    acl += '@prefix foaf: <http://xmlns.com/foaf/0.1/>.\n\n'
    acl += '<#owner>\n'
    acl += '    a acl:Authorization;\n'
    acl += f'    acl:agent <{OWNER_WEBID}>;\n'
    acl += f'    acl:accessTo <{resource_url}>;\n'
    if is_container:
        acl += f'    acl:default <{resource_url}>;\n'
    acl += '    acl:mode acl:Read, acl:Write, acl:Control.\n'

    for i, share in enumerate(shares, 1):
        acl += f'\n<#shared{i}>\n'
        acl += '    a acl:Authorization;\n'
        if share['webid'] == 'public':
            acl += '    acl:agentClass foaf:Agent;\n'
        else:
            acl += f'    acl:agent <{share["webid"]}>;\n'
        acl += f'    acl:accessTo <{resource_url}>;\n'
        if is_container:
            acl += f'    acl:default <{resource_url}>;\n'
        acl += f'    acl:mode {", ".join(share["modes"])}.\n'

    return acl


def write_acl(resource_url):
    """Write or delete ACL for a resource based on its active shares"""
    acl_url = resource_url + '.acl'
    shares = get_shares_for_resource(resource_url)

    if not shares:
        pod_request('DELETE', acl_url)
        return

    acl_content = build_acl_content(resource_url)
    pod_request('PUT', acl_url,
        data=acl_content,
        headers={'Content-Type': 'text/turtle'}
    )


@app.route('/share', methods=['POST'])
def share():
    """Share a resource with a WebID"""
    resource_url = request.form.get('resource_url', '')
    resource_path = request.form.get('resource_path', '')
    folder_path = request.form.get('folder_path', '').strip('/')
    webid = request.form.get('webid', '').strip()
    access_level = request.form.get('access_level', 'read')
    expires = request.form.get('expires', '').strip() or None

    if not resource_url:
        flash('Geen resource opgegeven', 'error')
        return redirect_to_folder(folder_path)

    if access_level == 'public':
        webid = 'public'
        modes = ['acl:Read']
    elif access_level == 'readwrite':
        modes = ['acl:Read', 'acl:Write']
    elif access_level == 'append':
        modes = ['acl:Append']
    else:
        modes = ['acl:Read']

    if not webid:
        flash('Vul een WebID in of kies openbaar', 'error')
        return redirect_to_folder(folder_path)

    add_share(resource_url, resource_path, webid, modes, expires)
    write_acl(resource_url)

    resource_name = resource_url.rstrip('/').split('/')[-1]
    display_webid = 'iedereen (openbaar)' if webid == 'public' else webid
    flash(f'"{resource_name}" gedeeld met {display_webid}', 'success')
    log_action('share', {'resource': resource_path, 'webid': webid, 'modes': modes})

    return redirect_to_folder(folder_path)


@app.route('/shares')
def shares_overview():
    """Show overview of all shared resources"""
    all_shares = get_all_shares()
    return render_template('shares.html', shares=all_shares)


@app.route('/revoke', methods=['POST'])
def revoke():
    """Revoke access for a specific WebID to a resource"""
    resource_url = request.form.get('resource_url', '')
    webid = request.form.get('webid', '')
    resource_path = request.form.get('resource_path', '')

    if not resource_url or not webid:
        flash('Ongeldige verzoek', 'error')
        return redirect(url_for('shares_overview'))

    remove_share(resource_url, webid)
    write_acl(resource_url)

    resource_name = resource_url.rstrip('/').split('/')[-1]
    display_webid = 'iedereen (openbaar)' if webid == 'public' else webid
    flash(f'Toegang van {display_webid} tot "{resource_name}" ingetrokken', 'success')
    log_action('revoke', {'resource': resource_path, 'webid': webid})

    return redirect(url_for('shares_overview'))


@app.route('/audit')
def audit():
    """Show the audit log"""
    action_filter = request.args.get('filter', '')
    log = get_audit_log(action_filter if action_filter else None, limit=100)
    return render_template('audit.html', log=log, current_filter=action_filter)


# === TRASH ROUTES ===

@app.route('/trash')
def trash_overview():
    """Show trash contents"""
    # Auto-cleanup expired items
    expired = cleanup_expired()
    for item in expired:
        pod_request('DELETE', item['trash_url'])
        add_notification('trash_auto_deleted', f'"{item["filename"]}" is definitief verwijderd uit prullenbak')
        log_action('trash_auto_deleted', {'file': item['filename']})

    trash_items = get_all_trash()
    return render_template('trash.html', trash_items=trash_items)


@app.route('/trash/restore', methods=['POST'])
def trash_restore():
    """Restore a file from trash to its original location"""
    trash_id = request.form.get('trash_id', '')

    entry = restore_from_trash(trash_id)
    if not entry:
        flash('Item niet gevonden in prullenbak', 'error')
        return redirect(url_for('trash_overview'))

    # Download from _trash/
    get_response = pod_request('GET', entry['trash_url'])
    if not get_response or get_response.status_code != 200:
        flash('Herstellen mislukt: kon bestand niet ophalen uit prullenbak', 'error')
        return redirect(url_for('trash_overview'))

    content_type = get_response.headers.get('Content-Type', 'application/octet-stream')

    # Upload to original location
    put_response = pod_request('PUT', entry['resource_url'],
        data=get_response.content,
        headers={'Content-Type': content_type}
    )
    if not put_response or put_response.status_code not in [200, 201, 205]:
        flash('Herstellen mislukt: kon bestand niet terugplaatsen', 'error')
        return redirect(url_for('trash_overview'))

    # Delete from _trash/
    pod_request('DELETE', entry['trash_url'])

    flash(f'"{entry["filename"]}" hersteld naar {entry.get("original_folder", "originele locatie")}', 'success')
    log_action('restore', {'file': entry['filename'], 'to': entry.get('original_folder', '')})
    return redirect(url_for('trash_overview'))


@app.route('/trash/delete', methods=['POST'])
def trash_permanent_delete():
    """Permanently delete a file from trash"""
    trash_id = request.form.get('trash_id', '')

    entry = permanent_delete(trash_id)
    if not entry:
        flash('Item niet gevonden in prullenbak', 'error')
        return redirect(url_for('trash_overview'))

    # Delete from pod _trash/
    pod_request('DELETE', entry['trash_url'])

    flash(f'"{entry["filename"]}" definitief verwijderd', 'success')
    log_action('permanent_delete', {'file': entry['filename']})
    return redirect(url_for('trash_overview'))


# === NOTIFICATION ROUTES ===

@app.route('/notifications')
def notifications_page():
    """Show all notifications"""
    notifs = get_all_notifications()
    return render_template('notifications.html', notifications=notifs)


@app.route('/notifications/read', methods=['POST'])
def notification_mark_read():
    """Mark notification(s) as read"""
    notification_id = request.form.get('notification_id', '')
    if notification_id:
        mark_as_read(notification_id)
    else:
        mark_all_read()
    return redirect(url_for('notifications_page'))


# === PROFILE & SETTINGS ROUTES ===

def get_storage_stats():
    """Calculate storage statistics by scanning the pod"""
    stats = {'file_count': 0, 'folder_count': 0, 'total_size': 0}

    def scan(container_url, depth=0, max_depth=5):
        if depth >= max_depth:
            return
        response = pod_request('GET', container_url, headers={'Accept': 'text/turtle'})
        if not response or response.status_code != 200:
            return
        items = parse_container_contents(response.text, container_url)
        for item in items:
            if item['is_folder']:
                stats['folder_count'] += 1
                scan(item['url'], depth + 1, max_depth)
            else:
                stats['file_count'] += 1
                # Try to get file size
                head_resp = pod_request('GET', item['url'])
                if head_resp and head_resp.status_code == 200:
                    stats['total_size'] += len(head_resp.content)

    try:
        scan(SOLID_POD_URL)
    except Exception:
        pass
    return stats


def format_size(size_bytes):
    """Format bytes to human-readable size"""
    if size_bytes < 1024:
        return f'{size_bytes} B'
    elif size_bytes < 1024 * 1024:
        return f'{size_bytes / 1024:.1f} KB'
    elif size_bytes < 1024 * 1024 * 1024:
        return f'{size_bytes / (1024 * 1024):.1f} MB'
    else:
        return f'{size_bytes / (1024 * 1024 * 1024):.1f} GB'


NL_MONTHS = ['jan', 'feb', 'mrt', 'apr', 'mei', 'jun', 'jul', 'aug', 'sep', 'okt', 'nov', 'dec']


def format_date_nl(http_date):
    """Format HTTP Last-Modified header to Dutch date like '15 mrt 2026'"""
    try:
        dt = parsedate_to_datetime(http_date)
        return f'{dt.day} {NL_MONTHS[dt.month - 1]} {dt.year}'
    except Exception:
        return '—'


@app.route('/profile')
def profile():
    """Show user profile with storage stats"""
    stats = get_storage_stats()
    stats['total_size_formatted'] = format_size(stats['total_size'])
    return render_template('profile.html',
        webid=OWNER_WEBID,
        pod_url=SOLID_POD_URL,
        stats=stats,
    )


@app.route('/settings')
def settings():
    """Show settings page"""
    return render_template('settings.html')


@app.route('/settings/export', methods=['POST'])
def export_backup():
    """Export entire pod as ZIP"""
    buffer = io.BytesIO()

    def add_to_zip(zf, container_url, path='', depth=0, max_depth=5):
        if depth >= max_depth:
            return
        response = pod_request('GET', container_url, headers={'Accept': 'text/turtle'})
        if not response or response.status_code != 200:
            return
        items = parse_container_contents(response.text, container_url)
        for item in items:
            if item['is_folder']:
                sub_path = path + item['name'] + '/'
                add_to_zip(zf, item['url'], sub_path, depth + 1, max_depth)
            else:
                file_path = path + item['name']
                file_response = pod_request('GET', item['url'])
                if file_response and file_response.status_code == 200:
                    zf.writestr(file_path, file_response.content)

    try:
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            add_to_zip(zf, SOLID_POD_URL)
    except Exception as e:
        flash(f'Backup mislukt: {e}', 'error')
        return redirect(url_for('settings'))

    buffer.seek(0)
    log_action('export', {'type': 'zip_backup'})
    return Response(
        buffer.getvalue(),
        content_type='application/zip',
        headers={'Content-Disposition': 'attachment; filename="mysolido-backup.zip"'}
    )


@app.route('/debug')
def debug():
    """Toon de raw Turtle response van de pod root"""
    try:
        response = pod_request('GET', SOLID_POD_URL, headers={'Accept': 'text/turtle'})
        if response and response.status_code == 200:
            return f'<pre>{response.text}</pre>'
        elif response:
            return f'<pre>Error {response.status_code}: {response.text}</pre>'
        else:
            return '<pre>Authenticatie mislukt</pre>'
    except requests.ConnectionError:
        return '<pre>CSS server niet bereikbaar</pre>'


@app.route('/init-folders')
def init_folders():
    """Maak de standaardmappen aan in de pod"""
    return _do_init_folders()


@app.route('/init-folders-welcome')
def init_folders_welcome():
    """Maak de standaardmappen aan vanuit het welkomstscherm"""
    return _do_init_folders(welcome=True)


def _do_init_folders(welcome=False):
    """Shared logic for creating default folders"""
    created = []
    skipped = []

    for folder in DEFAULT_FOLDERS:
        folder_url = SOLID_POD_URL + folder + '/'
        if container_exists(folder_url):
            skipped.append(folder)
            continue

        response = create_container(folder_url)
        if response and response.status_code in [200, 201, 205]:
            created.append(folder)
        else:
            status = response.status_code if response else 'geen response'
            flash(f'Map "{folder}" aanmaken mislukt: {status}', 'error')

    if welcome and created:
        flash('Je kluis is ingericht! Upload je eerste document.', 'success')
    else:
        if created:
            flash(f'{len(created)} mappen aangemaakt: {", ".join(created)}', 'success')
        if skipped:
            flash(f'{len(skipped)} mappen bestonden al: {", ".join(skipped)}', 'success')
        if not created and not skipped:
            flash('Geen mappen aangemaakt', 'error')

    return redirect(url_for('index'))


def redirect_to_folder(folder_path):
    """Redirect to the correct folder view"""
    if folder_path:
        return redirect(url_for('browse', folder_path=folder_path))
    return redirect(url_for('index'))


if __name__ == '__main__':
    print("=== MySolido ===")
    print(f"Pod: {SOLID_POD_URL}")
    token = get_access_token()
    if token:
        print(f"Authenticatie OK!")
    else:
        print("WAARSCHUWING: Authenticatie mislukt!")
    print("Start op http://localhost:5000")
    print("================")
    app.run(port=5000, debug=True)
