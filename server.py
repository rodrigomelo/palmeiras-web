"""
Palmeiras Web - Static/API HTTP server

Direct Supabase access with the same API contracts as the Vercel serverless
functions. This server is intentionally small and read-only. By default it
serves local development on port 5001; production can override HOST and PORT.

Usage:
    /opt/homebrew/bin/python3 server.py
    open http://localhost:5001
"""
import json
import os
import sys
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# Load .env before importing shared API helpers so helper-level environment
# constants see local development credentials.
DIRECTORY = Path(__file__).parent
ENV_PATH = DIRECTORY / '.env'
if ENV_PATH.exists():
    with ENV_PATH.open() as env_file:
        for line in env_file:
            line = line.strip()
            if '=' in line and not line.startswith('#'):
                key, value = line.split('=', 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

from api._shared import (  # noqa: E402
    RequestValidationError,
    BR_TZ,
    calendar_match,
    competition_param,
    int_param,
    month_window,
    parse_statuses,
    transform_match,
    transform_standing,
    year_month_params,
)
from api._shared import validate_date  # noqa: E402
from api.calendar import render_calendar  # noqa: E402

SUPABASE_URL = os.environ.get('SUPABASE_URL', '')
# Read-only API: use anon key only (preserves RLS).  The service_role key
# (SUPABASE_KEY) is intentionally excluded so the dev server never bypasses
# Row Level Security on public read endpoints.
SUPABASE_KEY = (
    os.environ.get('SUPABASE_ANON_KEY')
    or os.environ.get('SUPABASE_PUBLIC_KEY')
    or ''
)
HOST = os.environ.get('HOST', '0.0.0.0')
PORT = int(os.environ.get('PORT', '5001'))
DEFAULT_ALLOWED_ORIGINS = {
    'http://localhost:5001',
    'http://localhost:3000',
    'https://palmeiras-web.vercel.app',
    'https://palmeiras.rodrigolanna.com.br',
}
ALLOWED_ORIGINS = {
    origin.strip()
    for origin in os.environ.get('ALLOWED_ORIGINS', '').split(',')
    if origin.strip()
} or DEFAULT_ALLOWED_ORIGINS

_client = None


def get_client():
    """Return a cached Supabase client for local development."""
    global _client
    if _client is not None:
        return _client
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None
    try:
        from supabase import create_client
        _client = create_client(SUPABASE_URL, SUPABASE_KEY)
        return _client
    except Exception as error:
        print(f'[supabase] connection failed: {type(error).__name__}', file=sys.stderr)
        return None


def _safe_error(collection, code):
    return {collection: [], 'error': code}


def api_matches(params):
    """Return match rows in the public frontend contract."""
    try:
        status = params.get('status', [None])[0]
        statuses = parse_statuses(status)
        limit = int_param(params, 'limit', 50, min_value=1, max_value=100)
        from_date = params.get('from_date', [None])[0]
        from_date, date_error = validate_date(from_date)
        if date_error:
            raise RequestValidationError(date_error)
    except RequestValidationError as error:
        return 400, _safe_error('matches', str(error)), 'application/json', 'no-store'

    client = get_client()
    if not client:
        return 503, _safe_error('matches', 'not_connected'), 'application/json', 'no-store'

    try:
        query = client.table('matches').select('*')
        if statuses:
            if len(statuses) == 1:
                query = query.eq('status', statuses[0])
            else:
                query = query.in_('status', statuses)
            if any(s in ('SCHEDULED', 'TIMED', 'IN_PLAY', 'PAUSED') for s in statuses) and not from_date:
                from_date = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        if from_date:
            query = query.gte('utc_date', from_date)

        rows = query.order('utc_date').limit(max(limit * 3, 50)).execute().data or []
        if any(row.get('status') == 'FINISHED' for row in rows):
            rows.sort(key=lambda row: row.get('utc_date', ''), reverse=True)
        return 200, {'matches': [transform_match(row) for row in rows[:limit]]}
    except Exception as error:
        print(f'[api_matches] unexpected error: {type(error).__name__}', file=sys.stderr)
        return 500, _safe_error('matches', 'internal_error'), 'application/json', 'no-store'


def api_standings(params):
    """Return league standings."""
    try:
        competition = competition_param(params)
        limit = min(int(params.get('limit', [100])[0]), 100)
    except RequestValidationError as error:
        return 400, _safe_error('standings', str(error)), 'application/json', 'no-store'

    client = get_client()
    if not client:
        return 503, _safe_error('standings', 'not_connected'), 'application/json', 'no-store'

    try:
        rows = (
            client.table('standings')
            .select('*')
            .eq('competition', competition)
            .order('position')
            .limit(limit)
            .execute()
            .data
            or []
        )
        return 200, {'standings': [transform_standing(row) for row in rows]}
    except Exception as error:
        print(f'[api_standings] unexpected error: {type(error).__name__}', file=sys.stderr)
        return 500, _safe_error('standings', 'internal_error'), 'application/json', 'no-store'


def api_news(params):
    """Return recent news."""
    try:
        limit = int_param(params, 'limit', 20, min_value=1, max_value=50)
    except RequestValidationError as error:
        return 400, _safe_error('news', str(error)), 'application/json', 'no-store'

    client = get_client()
    if not client:
        return 503, _safe_error('news', 'not_connected'), 'application/json', 'no-store'

    try:
        rows = client.table('news').select('*').order('collected_at', desc=True).limit(limit).execute().data or []
        return 200, {'news': rows}
    except Exception as error:
        print(f'[api_news] unexpected error: {type(error).__name__}', file=sys.stderr)
        return 500, _safe_error('news', 'internal_error'), 'application/json', 'no-store'


def api_calendar_monthly(params):
    """Return matches grouped by local Sao Paulo calendar day."""
    try:
        year, month = year_month_params(params)
    except RequestValidationError as error:
        return 400, {'error': str(error), 'days': {}}, 'application/json', 'no-store'

    client = get_client()
    if not client:
        return 503, {'error': 'not_connected', 'days': {}}, 'application/json', 'no-store'

    try:
        start_utc, end_utc = month_window(year, month)
        rows = (
            client.table('matches')
            .select('*')
            .gte('utc_date', start_utc)
            .lt('utc_date', end_utc)
            .order('utc_date')
            .limit(80)
            .execute()
            .data
            or []
        )

        days = {}
        for row in rows:
            utc_date = row.get('utc_date')
            if not utc_date:
                continue
            try:
                local_dt = datetime.fromisoformat(utc_date.replace('Z', '+00:00')).astimezone(BR_TZ)
            except ValueError:
                continue
            if local_dt.year != year or local_dt.month != month:
                continue
            days.setdefault(local_dt.strftime('%Y-%m-%d'), []).append(calendar_match(row))
        return 200, {'year': year, 'month': month, 'days': days}, 'application/json', 'public, max-age=900'
    except Exception as error:
        print(f'[api_calendar_monthly] unexpected error: {type(error).__name__}', file=sys.stderr)
        return 500, {'error': 'internal_error', 'days': {}}, 'application/json', 'no-store'


def api_calendar(params):
    """Return an iCalendar feed."""
    client = get_client()
    if not client:
        return 503, 'Calendar unavailable', 'text/plain; charset=utf-8', 'no-store'

    try:
        rows = client.table('matches').select('*').order('utc_date', desc=True).limit(150).execute().data or []
        return 200, render_calendar(rows), 'text/calendar; charset=utf-8', 'public, max-age=900'
    except Exception as error:
        print(f'[api_calendar] unexpected error: {type(error).__name__}', file=sys.stderr)
        return 500, 'Calendar unavailable', 'text/plain; charset=utf-8', 'no-store'


def api_health(params):
    """Health check endpoint for local development."""
    start = datetime.now(timezone.utc)
    client = get_client()
    status = 'disconnected'
    latency_ms = 0
    http_status = 503

    if client:
        try:
            client.table('matches').select('id').limit(1).execute()
            latency_ms = round((datetime.now(timezone.utc) - start).total_seconds() * 1000)
            status = 'connected'
            http_status = 200
        except Exception as error:
            print(f'[api_health] unexpected error: {type(error).__name__}', file=sys.stderr)
            status = 'error'

    return http_status, {
        'status': 'ok' if status == 'connected' else 'degraded',
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'services': {'supabase': {'status': status, 'latency_ms': latency_ms}},
        'version': '1.1.0-local',
    }, 'application/json', 'no-store'


API_ROUTES = {
    '/api/matches': api_matches,
    '/api/standings': api_standings,
    '/api/news': api_news,
    '/api/calendar.ics': api_calendar,
    '/api/calendar': api_calendar,
    '/api/calendar_monthly': api_calendar_monthly,
    '/api/health': api_health,
}


class Handler(SimpleHTTPRequestHandler):
    """Static + API request handler for local development."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DIRECTORY), **kwargs)

    def _send_security_headers(self):
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header(
            'Content-Security-Policy',
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com data:; "
            "img-src 'self' https: data:; "
            "connect-src 'self' https://*.supabase.co; "
            "base-uri 'self'; frame-ancestors 'none'; form-action 'self'",
        )
        self.send_header('Referrer-Policy', 'strict-origin-when-cross-origin')
        self.send_header('Permissions-Policy', 'camera=(), microphone=(), geolocation=(), interest-cohort=()')

    def end_headers(self):
        self._send_security_headers()
        super().end_headers()

    def do_OPTIONS(self):
        """Handle CORS preflight requests."""
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.send_header('Content-Length', '0')
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if any(part.startswith('.') for part in Path(path).parts):
            self.send_error(404)
            return

        for route, handler in API_ROUTES.items():
            if path == route:
                params = parse_qs(parsed.query)
                result = handler(params)
                status, data, content_type, cache_control = (*result, 'application/json', 'public, max-age=300')[:4]
                self.send_response(status)
                self.send_header('Content-Type', content_type)
                self.send_header('Cache-Control', cache_control)
                origin = self.headers.get('Origin', '')
                if origin in ALLOWED_ORIGINS:
                    self.send_header('Access-Control-Allow-Origin', origin)
                self.end_headers()
                if isinstance(data, (dict, list)):
                    body = json.dumps(data, ensure_ascii=False).encode('utf-8')
                elif isinstance(data, bytes):
                    body = data
                else:
                    body = str(data).encode('utf-8')
                self.wfile.write(body)
                return

        if path == '/':
            self.path = '/index.html'
        return super().do_GET()

    def log_message(self, fmt, *args):
        sys.stderr.write(f'[{self.log_date_time_string()}] {fmt % args}\n')


class PalmeirasHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True


if __name__ == '__main__':
    try:
        from supabase import create_client  # noqa: F401
    except ImportError:
        print("ERROR: 'supabase' package not installed.", file=sys.stderr)
        print(f'  Python: {sys.executable} ({sys.version.split()[0]})', file=sys.stderr)
        print('  Fix: /opt/homebrew/bin/python3 server.py', file=sys.stderr)
        sys.exit(1)

    if not SUPABASE_URL or not SUPABASE_KEY:
        print('ERROR: SUPABASE_URL and SUPABASE_ANON_KEY must be set in .env', file=sys.stderr)
        sys.exit(1)

    print(f'Palmeiras Agenda running at http://{HOST}:{PORT}')
    server = PalmeirasHTTPServer((HOST, PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nShutting down...')
        server.server_close()
