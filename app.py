import re
import os
from flask import Flask, render_template, request, redirect, url_for, flash, Response
import requests
import base64
from audit import log_action, get_audit_log
from shares import add_share, remove_share, get_all_shares, get_shares_for_resource, check_expired_shares

app = Flask(__name__)
app.secret_key = '***REMOVED***'

# === CONFIGURATIE ===
CSS_BASE_URL = 'http://localhost:3000'
SOLID_POD_URL = 'http://localhost:3000/wim/'
OWNER_WEBID = 'http://localhost:3000/wim/profile/card#me'
CLIENT_ID = '***REMOVED***'
CLIENT_SECRET = '***REMOVED***'

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

# Folder icons per category
FOLDER_ICONS = {
    'identiteit': '\U0001faaa',
    'medisch': '\U0001f3e5',
    'financieel': '\U0001f4b0',
    'wonen': '\U0001f3e0',
    'zakelijk': '\U0001f4bc',
    'werk': '\U0001f454',
    'voertuigen': '\U0001f697',
    'juridisch': '\u2696\ufe0f',
    'media': '\U0001f4f8',
    'wachtwoorden': '\U0001f511',
    'gezin': '\U0001f468\u200d\U0001f469\u200d\U0001f467\u200d\U0001f466',
    'abonnementen': '\U0001f4cb',
    'inbox': '\U0001f4e5',
    'verzekeringen': '\U0001f6e1\ufe0f',
}

# Default folders to create on init
DEFAULT_FOLDERS = [
    'identiteit', 'medisch', 'financieel', 'wonen', 'zakelijk',
    'werk', 'voertuigen', 'juridisch', 'media', 'wachtwoorden',
    'gezin', 'abonnementen', 'inbox', 'verzekeringen',
]


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
    """Get the icon for a folder name, checking parent folders too"""
    name_lower = folder_name.lower()
    return FOLDER_ICONS.get(name_lower, '\U0001f4c1')


def parse_container_contents(turtle_text, base_url):
    """Parse Turtle response to extract container contents"""
    items = []

    # Find all ldp:contains references using regex
    # Handles: ldp:contains <a/>, <b/>, <c/> across one or multiple lines
    # Match until a '.' that ends the Turtle statement (followed by newline/end),
    # not a '.' inside a filename like <test.txt>
    contains_pattern = re.compile(r'ldp:contains\s+(.+?)\.\s*$', re.DOTALL | re.MULTILINE)
    contains_matches = contains_pattern.findall(turtle_text)

    # Extract all <resource> references from the matched text
    resources = []
    for match in contains_matches:
        resources.extend(re.findall(r'<([^>]+)>', match))

    for resource in resources:
        # Build full URL if relative
        if not resource.startswith('http'):
            full_url = base_url.rstrip('/') + '/' + resource.lstrip('/')
        else:
            full_url = resource
        name = resource.rstrip('/').split('/')[-1]
        is_folder = resource.endswith('/')
        icon = get_folder_icon(name) if is_folder else '\U0001f4c4'
        items.append({
            'name': name,
            'url': full_url,
            'is_folder': is_folder,
            'icon': icon,
        })
    # Sort: folders first, then files, alphabetically
    items.sort(key=lambda x: (not x['is_folder'], x['name'].lower()))
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
        {'name': name, 'icon': FOLDER_ICONS[name], 'label': name.capitalize()}
        for name in DEFAULT_FOLDERS
    ]


def get_move_folders(folder_path, items):
    """Bouw de mappenlijst voor de verplaats-dropdown: hoofdmappen + submappen van huidige locatie"""
    folders = []
    # Submappen uit de huidige listing
    subfolders = [item for item in items if item['is_folder']]

    for name in DEFAULT_FOLDERS:
        icon = FOLDER_ICONS[name]
        folders.append({'value': name, 'label': f'{icon} {name.capitalize()}', 'indent': 0})
        # Als we in deze hoofdmap zitten (of een submap ervan), voeg submappen toe
        if folder_path == name or folder_path.startswith(name + '/'):
            for sub in subfolders:
                sub_path = folder_path + '/' + sub['name']
                folders.append({'value': sub_path, 'label': sub['name'], 'indent': 1})
    return folders


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

    # Ensure folder_path ends clean
    folder_path = folder_path.strip('/')
    if folder_path:
        container_url = SOLID_POD_URL + folder_path + '/'
    else:
        container_url = SOLID_POD_URL

    try:
        response = pod_request('GET', container_url, headers={'Accept': 'text/turtle'})
        if response and response.status_code == 200:
            items = parse_container_contents(response.text, container_url)
            breadcrumbs = build_breadcrumbs(folder_path)
            # Parent path for "back" button
            parts = [p for p in folder_path.split('/') if p]
            parent_path = '/'.join(parts[:-1]) if parts else None
            move_folders = get_move_folders(folder_path, items)
            return render_template('index.html',
                items=items,
                pod_url=SOLID_POD_URL,
                folder_path=folder_path,
                breadcrumbs=breadcrumbs,
                parent_path=parent_path,
                all_folders=get_all_folders(),
                move_folders=move_folders,
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
    """Verwijder een resource uit de pod"""
    resource_url = request.form.get('resource_url')
    folder_path = request.form.get('folder_path', '').strip('/')

    if not resource_url:
        flash('Geen resource opgegeven', 'error')
        return redirect_to_folder(folder_path)

    response = pod_request('DELETE', resource_url)

    if response and response.status_code in [200, 204, 205]:
        name = resource_url.rstrip('/').split('/')[-1]
        flash(f'"{name}" verwijderd', 'success')
        log_action('delete', {'resource': name, 'folder': folder_path or 'root'})
    elif response:
        flash(f'Verwijderen mislukt: {response.status_code}', 'error')
    else:
        flash('Verwijderen mislukt: authenticatie error', 'error')

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

    # Build target URL
    if target_folder:
        target_url = SOLID_POD_URL + target_folder + '/' + filename
    else:
        target_url = SOLID_POD_URL + filename

    if target_url == resource_url:
        flash('Bestand staat al in deze map', 'error')
        return redirect_to_folder(folder_path)

    # Step 1: Download the file
    get_response = pod_request('GET', resource_url)
    if not get_response or get_response.status_code != 200:
        status = get_response.status_code if get_response else 'geen response'
        flash(f'Verplaatsen mislukt: kon bestand niet ophalen ({status})', 'error')
        return redirect_to_folder(folder_path)

    content_type = get_response.headers.get('Content-Type', 'application/octet-stream')

    # Step 2: Upload to new location
    put_response = pod_request('PUT', target_url,
        data=get_response.content,
        headers={'Content-Type': content_type}
    )
    if not put_response or put_response.status_code not in [200, 201, 205]:
        status = put_response.status_code if put_response else 'geen response'
        flash(f'Verplaatsen mislukt: kon bestand niet opslaan ({status})', 'error')
        return redirect_to_folder(folder_path)

    # Step 3: Delete original
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
            # Build the subfolder path
            sub_path = path + '/' + item['name'] if path else item['name']
            sub_url = item['url']
            # Recurse into subfolder
            results.extend(search_pod(sub_url, query, sub_path, depth + 1, max_depth))
        else:
            # Check if filename matches query (case-insensitive)
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

    content_type = response.headers.get('Content-Type', 'application/octet-stream')
    filename = file_path.split('/')[-1]
    ext = os.path.splitext(filename)[1].lower()

    # For media types that need an HTML wrapper (audio/video), render a template
    # Unless ?raw=1 is passed (used by <source> tags to get the actual media data)
    if ext in ('.mp3', '.wav', '.mp4', '.webm') and not request.args.get('raw'):
        folder_path = '/'.join(file_path.split('/')[:-1])
        return render_template('view.html',
            filename=filename,
            file_path=file_path,
            folder_path=folder_path,
            media_type='audio' if ext in ('.mp3', '.wav') else 'video',
            content_type=VIEWABLE_TYPES.get(ext, content_type),
        )

    # For viewable types, serve inline
    if ext in VIEWABLE_TYPES:
        return Response(
            response.content,
            content_type=content_type,
            headers={'Content-Disposition': f'inline; filename="{filename}"'}
        )

    # For everything else, trigger download
    return Response(
        response.content,
        content_type=content_type,
        headers={'Content-Disposition': f'attachment; filename="{filename}"'}
    )


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

    # Owner entry (always present)
    acl = '@prefix acl: <http://www.w3.org/ns/auth/acl#>.\n'
    acl += '@prefix foaf: <http://xmlns.com/foaf/0.1/>.\n\n'
    acl += '<#owner>\n'
    acl += '    a acl:Authorization;\n'
    acl += f'    acl:agent <{OWNER_WEBID}>;\n'
    acl += f'    acl:accessTo <{resource_url}>;\n'
    if is_container:
        acl += f'    acl:default <{resource_url}>;\n'
    acl += '    acl:mode acl:Read, acl:Write, acl:Control.\n'

    # Add one entry per active share
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
        # No shares left, remove the ACL so it falls back to parent
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

    # Determine modes based on access level
    if access_level == 'public':
        webid = 'public'
        modes = ['acl:Read']
    elif access_level == 'readwrite':
        modes = ['acl:Read', 'acl:Write']
    else:
        modes = ['acl:Read']

    if not webid:
        flash('Vul een WebID in of kies openbaar', 'error')
        return redirect_to_folder(folder_path)

    # Add to shares.json
    add_share(resource_url, resource_path, webid, modes, expires)

    # Write ACL with ALL active shares for this resource
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

    # Remove from shares.json
    remove_share(resource_url, webid)

    # Rewrite ACL with remaining shares (or delete if none left)
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
    """Maak de standaard 13 hoofdmappen aan in de pod"""
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
