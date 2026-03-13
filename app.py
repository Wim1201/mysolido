import re
from flask import Flask, render_template, request, redirect, url_for, flash
import requests
import base64

app = Flask(__name__)
app.secret_key = 'mysolido-dev-key-2026'

# === CONFIGURATIE ===
CSS_BASE_URL = 'http://localhost:3000'
SOLID_POD_URL = 'http://localhost:3000/wim/'
CLIENT_ID = 'mysolido-app_0297c523-c780-4102-b7cb-f5ad8cd6e294'
CLIENT_SECRET = 'd9e70d02c091217415164422add9b819aa4bc5e861242d90e3b2b09526e810514940f32f6c9fb3275982ddab5135bea3881ddad347df571f10a65bf4f308e180'

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
}

# Default folders to create on init
DEFAULT_FOLDERS = [
    'identiteit', 'medisch', 'financieel', 'wonen', 'zakelijk',
    'werk', 'voertuigen', 'juridisch', 'media', 'wachtwoorden',
    'gezin', 'abonnementen', 'inbox',
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
    # First, collect all text after ldp:contains declarations
    contains_pattern = re.compile(r'ldp:contains\s+(.+?)(?:[.;]|$)', re.DOTALL)
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


def browse_folder(folder_path):
    """Shared logic for browsing a folder"""
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
            return render_template('index.html',
                items=items,
                pod_url=SOLID_POD_URL,
                folder_path=folder_path,
                breadcrumbs=breadcrumbs,
                parent_path=parent_path,
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
    )


@app.route('/upload', methods=['POST'])
def upload():
    """Upload een bestand naar de huidige map"""
    folder_path = request.form.get('folder_path', '').strip('/')

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
    elif response:
        flash(f'Map aanmaken mislukt: {response.status_code}', 'error')
    else:
        flash('Map aanmaken mislukt: authenticatie error', 'error')

    return redirect_to_folder(folder_path)


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
