"""
Palmeiras Web Dashboard - Flask Server

Local development server that:
- Serves static files (HTML, CSS, JS)
- Proxies /api/* to local data API (localhost:5002)
- Generates calendar ICS

On Vercel, static files are served directly and API calls
are proxied via vercel.json to palmeiras-data.vercel.app.
"""
import os
import subprocess

from flask import Flask, send_from_directory, send_file, request, Response
import requests


def get_git_version():
    try:
        return subprocess.check_output(
            ['git', 'describe', '--tags', '--abbrev=0'],
            stderr=subprocess.DEVNULL,
        ).decode().strip()
    except Exception:
        return "unknown"


DATA_API = os.environ.get('DATA_API', 'http://localhost:5002')

app = Flask(__name__, static_folder='.')


@app.route('/')
def index():
    return send_from_directory('.', 'index.html')


@app.route('/favicon.png')
def favicon():
    return send_from_directory('static', 'favicon.png')


@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory('static', filename)


@app.route('/version')
@app.route('/api/version')
def version():
    path = os.path.join('.', 'version.txt')
    if not os.path.exists(path):
        with open(path, 'w') as f:
            f.write(get_git_version())
    return send_file(path, mimetype='text/plain')


@app.route('/api/<path:endpoint>')
def proxy_api(endpoint):
    """Proxy /api/* to the data API."""
    target = f"{DATA_API}/api/{endpoint}"
    resp = requests.get(target, params=request.args, timeout=30)
    return Response(resp.content, status=resp.status_code, mimetype='application/json')


def handler(event, context):
    return app(event, context)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)
