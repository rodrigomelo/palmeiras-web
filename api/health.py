"""
GET /api/health — Health check endpoint

Returns system status, Supabase connectivity, and API version info.
"""
import json
import os
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from urllib.request import Request, urlopen
from urllib.error import HTTPError

SUPABASE_URL = os.environ.get('SUPABASE_URL', '')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY', '')


VERSION = '1.0.0'


class handler(BaseHTTPRequestHandler):
    """Vercel serverless function entry for /api/health"""

    def do_GET(self):
        start = datetime.now(timezone.utc)
        supabase_status = 'disconnected'
        latency_ms = 0

        try:
            headers = {
                'apikey': SUPABASE_KEY,
                'Authorization': f'Bearer {SUPABASE_KEY}',
                'Content-Type': 'application/json',
            }
            req = Request(
                f'{SUPABASE_URL}/rest/v1/matches?select=id&limit=1',
                headers=headers
            )
            urlopen(req, timeout=10).read().decode()
            elapsed = (datetime.now(timezone.utc) - start).total_seconds() * 1000
            supabase_status = 'connected'
            latency_ms = round(elapsed)
        except Exception:
            supabase_status = 'disconnected'

            latency_ms = 0

        status_code = 200 if supabase_status == 'connected' else 503
        body = json.dumps({
            'status': 'ok' if supabase_status == 'connected' else 'degraded',
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'services': {
                'supabase': {
                    'status': supabase_status,
                    'latency_ms': latency_ms,
                },
            },
            'version': VERSION,
        })

        self.send_response(status_code, body)
        self.end_headers()

        self.send_header('Content-Type', 'application/json')
        self.send_header('Cache-Control', 'public, max-age=900')
        self.wfile.write(body.encode())
