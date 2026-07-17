"""GET /api/health — health check endpoint."""
import sys
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler
from urllib.error import HTTPError

try:
    from api._shared import APP_VERSION, is_configured, json_response, supabase_get, cors_options_response
except ImportError:
    from _shared import APP_VERSION, is_configured, json_response, supabase_get, cors_options_response  # type: ignore


def _parse_iso_datetime(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _data_freshness():
    now = datetime.now(timezone.utc)
    max_age = timedelta(hours=2)
    tables = {
        'matches': {'table': 'matches', 'field': 'updated_at'},
        'standings': {'table': 'standings', 'field': 'updated_at'},
        'news': {'table': 'news', 'field': 'collected_at'},
    }
    body = {'status': 'fresh', 'max_age_minutes': round(max_age.total_seconds() / 60), 'tables': {}}

    for name, config in tables.items():
        field = config['field']
        rows = supabase_get(config['table'], select=field, order=f'{field}.desc', limit='1')
        latest_raw = rows[0].get(field) if rows else None
        latest = _parse_iso_datetime(latest_raw)
        age_minutes = round((now - latest).total_seconds() / 60) if latest else None
        table_status = 'fresh' if age_minutes is not None and age_minutes <= body['max_age_minutes'] else 'stale'
        if table_status != 'fresh':
            body['status'] = 'stale'
        body['tables'][name] = {
            'status': table_status,
            'latest_at': latest_raw,
            'age_minutes': age_minutes,
        }

    return body


class handler(BaseHTTPRequestHandler):
    """HTTP function entry for /api/health."""

    def do_OPTIONS(self):
        cors_options_response(self)

    def do_HEAD(self):
        self._suppress_body = True
        try:
            return self.do_GET()
        finally:
            self._suppress_body = False

    def do_GET(self):
        start = datetime.now(timezone.utc)
        supabase_status = 'disconnected'
        latency_ms = 0
        freshness = {'status': 'unknown', 'tables': {}}

        if is_configured():
            try:
                supabase_get('matches', select='id', limit='1')
                freshness = _data_freshness()
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
        health_status = 'ok' if supabase_status == 'connected' and freshness.get('status') == 'fresh' else 'degraded'
        body = {
            'status': health_status,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'services': {
                'supabase': {
                    'status': supabase_status,
                    'latency_ms': latency_ms,
                },
                'data_freshness': freshness,
            },
            'version': APP_VERSION,
        }
        return json_response(self, status_code, body, cache_control='no-store')
