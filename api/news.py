"""GET /api/news?limit=20."""
import sys
from http.server import BaseHTTPRequestHandler
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse

try:
    from api._shared import RequestValidationError, int_param, is_configured, json_response, supabase_get, upstream_status, cors_options_response
except ImportError:
    from _shared import RequestValidationError, int_param, is_configured, json_response, supabase_get, upstream_status, cors_options_response  # type: ignore


def _safe_error(code='upstream_error'):
    return {'news': [], 'error': code}


BLOCKED_NEWS_SOURCES = {
    'facebook.com',
    'instagram.com',
    'threads.net',
    'tiktok.com',
    'twitter.com',
    'x.com',
    'youtube.com',
}


def public_news_items(rows, limit):
    items = []
    for row in rows or []:
        title = str(row.get('title') or '').strip()
        source = str(row.get('source') or '').strip().lower()
        url = str(row.get('url') or '').strip()
        if not url or len(title) < 15 or len(title) > 180:
            continue
        if source in BLOCKED_NEWS_SOURCES:
            continue
        items.append(row)
        if len(items) >= limit:
            break
    return items


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        cors_options_response(self)

    def do_HEAD(self):
        self._suppress_body = True
        try:
            return self.do_GET()
        finally:
            self._suppress_body = False

    def do_GET(self):
        params = parse_qs(urlparse(self.path).query)
        try:
            limit = int_param(params, 'limit', 20, min_value=1, max_value=50)
        except RequestValidationError as error:
            return json_response(self, 400, _safe_error(str(error)), cache_control='no-store')

        if not is_configured():
            return json_response(self, 503, _safe_error('not_configured'), cache_control='no-store')

        try:
            data = supabase_get(
                'news',
                select='*',
                order='published_at.desc.nullslast,collected_at.desc',
                limit=str(min(limit * 3, 100)),
            )
            return json_response(self, 200, {'news': public_news_items(data, limit)}, cache_control='public, max-age=60')
        except HTTPError as error:
            print(f'[api.news] Supabase HTTP {error.code}', file=sys.stderr)
            return json_response(self, upstream_status(error), _safe_error(f'supabase_{error.code}'), cache_control='no-store')
        except Exception as error:
            print(f'[api.news] unexpected error: {type(error).__name__}', file=sys.stderr)
            return json_response(self, 500, _safe_error('internal_error'), cache_control='no-store')
