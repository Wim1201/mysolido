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

@app.route('/')
def index():
    """Toon de inhoud van de pod"""
    try:
        response = pod_request('GET', SOLID_POD_URL, headers={'Accept': 'text/turtle'})
        if response and response.status_code == 200:
            items = []
            for line in response.text.split('\n'):
                if 'ldp:contains' in line:
                    resource = line.split('<')[1].split('>')[0] if '<' in line else ''
                    if resource:
                        name = resource.rstrip('/').split('/')[-1]
                        is_folder = resource.endswith('/')
                        items.append({'name': name, 'url': resource, 'is_folder': is_folder})
            return render_template('index.html', items=items, pod_url=SOLID_POD_URL)
        elif response:
            flash(f'Kon pod niet laden: {response.status_code}', 'error')
            return render_template('index.html', items=[], pod_url=SOLID_POD_URL)
        else:
            flash('Authenticatie mislukt. Controleer client credentials.', 'error')
            return render_template('index.html', items=[], pod_url=SOLID_POD_URL)
    except requests.ConnectionError:
        flash('CSS server niet bereikbaar. Draait hij op poort 3000?', 'error')
        return render_template('index.html', items=[], pod_url=SOLID_POD_URL)

@app.route('/upload', methods=['POST'])
def upload():
    """Upload een bestand naar de pod"""
    if 'file' not in request.files:
        flash('Geen bestand geselecteerd', 'error')
        return redirect(url_for('index'))

    file = request.files['file']
    if file.filename == '':
        flash('Geen bestand geselecteerd', 'error')
        return redirect(url_for('index'))

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

    return redirect(url_for('index'))

@app.route('/delete', methods=['POST'])
def delete():
    """Verwijder een resource uit de pod"""
    resource_url = request.form.get('resource_url')
    if not resource_url:
        flash('Geen resource opgegeven', 'error')
        return redirect(url_for('index'))

    response = pod_request('DELETE', resource_url)

    if response and response.status_code in [200, 204, 205]:
        name = resource_url.rstrip('/').split('/')[-1]
        flash(f'"{name}" verwijderd', 'success')
    elif response:
        flash(f'Verwijderen mislukt: {response.status_code}', 'error')
    else:
        flash('Verwijderen mislukt: authenticatie error', 'error')

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
