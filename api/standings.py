"""
GET /api/standings?competition=BSA
"""
import json
import os
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

SUPABASE_URL = os.environ.get('SUPABASE_URL', '')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY', '')


def get_supabase():
    try:
        from supabase import create_client
        return create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception:
        return None


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        params = parse_qs(urlparse(self.path).query)
        competition = params.get('competition', ['BSA'])[0]

        client = get_supabase()
        if not client:
            return self._respond(503, {'standings': [], 'error': 'not_connected'})

        try:
            result = client.table('standings').select('*').eq('competition', competition).order('position').execute()
            self._respond(200, {'standings': result.data})
        except Exception as e:
            self._respond(500, {'standings': [], 'error': str(e)})

    def _respond(self, status, data):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
