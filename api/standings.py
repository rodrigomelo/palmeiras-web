"""
GET /api/standings

Query params:
  competition — code (default: BSA)
"""
import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

from db import get_supabase


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        params = parse_qs(urlparse(self.path).query)
        competition = params.get('competition', ['BSA'])[0]

        client = get_supabase()
        if not client:
            self._respond(503, {'standings': [], 'error': 'not_connected'})
            return

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
