"""
GET /api/news

Query params:
  limit — max results (default 10)
"""
import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

from db import get_supabase


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        params = parse_qs(urlparse(self.path).query)
        limit = int(params.get('limit', ['10'])[0])

        client = get_supabase()
        if not client:
            self._respond(503, [])
            return

        try:
            result = client.table('news').select('*').order('collected_at', desc=True).limit(limit).execute()
            self._respond(200, result.data)
        except Exception as e:
            self._respond(500, [])

    def _respond(self, status, data):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
