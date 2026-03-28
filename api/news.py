"""
GET /api/news?limit=20
Uses direct Supabase REST API.
"""
import json
import os
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError

SUPABASE_URL = os.environ.get('SUPABASE_URL', '')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY', '')


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        params = parse_qs(urlparse(self.path).query)
        limit = min(int(params.get('limit', ['20'])[0]), 50)

        if not SUPABASE_URL or not SUPABASE_KEY:
            return self._respond(503, {'news': [], 'error': 'not_configured'})

        try:
            headers = {
                'apikey': SUPABASE_KEY,
                'Authorization': f'Bearer {SUPABASE_KEY}',
            }
            qs = urlencode({'select': '*', 'order': 'collected_at.desc', 'limit': str(limit)})
            url = f'{SUPABASE_URL}/rest/v1/news?{qs}'
            req = Request(url, headers=headers)
            with urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
            self._respond(200, {'news': data})
        except HTTPError as e:
            self._respond(e.code, {'news': [], 'error': f'supabase_{e.code}'})
        except Exception as e:
            self._respond(500, {'news': [], 'error': str(e)})

    def _respond(self, status, data):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
