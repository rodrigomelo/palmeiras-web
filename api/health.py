"""GET /api/health — health check endpoint."""
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from urllib.error import HTTPError

try:
    from api._shared import is_configured, json_response, supabase_get
except ImportError:
    from _shared import is_configured, json_response, supabase_get  # type: ignore

VERSION = '1.1.0'


class handler(BaseHTTPRequestHandler):
    """Vercel serverless function entry for /api/health."""

    def do_GET(self):
        start = datetime.now(timezone.utc)
        supabase_status = 'disconnected'
        latency_ms = 0

        if is_configured():
            try:
                supabase_get('matches', select='id', limit='1')
                elapsed = (datetime.now(timezone.utc) - start).total_seconds() * 1000
                supabase_status = 'connected'
                latency_ms = round(elapsed)
            except HTTPError as error:
                print(f'[api.health] Supabase HTTP {error.code}', file=sys.stderr)
                supabase_status = 'error'
            except Exception as error:
                print(f'[api.health] unexpected error: {type(error).__name__}', file=sys.stderr)
                supabase_status = 'error'

        status_code = 200 if supabase_status == 'connected' else 503
        body = {
            'status': 'ok' if supabase_status == 'connected' else 'degraded',
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'services': {
                'supabase': {
                    'status': supabase_status,
                    'latency_ms': latency_ms,
                },
            },
            'version': VERSION,
        }
        return json_response(self, status_code, body, cache_control='no-store')
