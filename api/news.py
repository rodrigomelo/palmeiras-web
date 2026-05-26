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


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        cors_options_response(self)

    def do_GET(self):
        params = parse_qs(urlparse(self.path).query)
        try:
            limit = int_param(params, 'limit', 20, min_value=1, max_value=50)
        except RequestValidationError as error:
            return json_response(self, 400, _safe_error(str(error)), cache_control='no-store')

        if not is_configured():
            return json_response(self, 503, _safe_error('not_configured'), cache_control='no-store')

        try:
            data = supabase_get('news', select='*', order='collected_at.desc', limit=str(limit))
            return json_response(self, 200, {'news': data})
        except HTTPError as error:
            print(f'[api.news] Supabase HTTP {error.code}', file=sys.stderr)
            return json_response(self, upstream_status(error), _safe_error(f'supabase_{error.code}'), cache_control='no-store')
        except Exception as error:
            print(f'[api.news] unexpected error: {type(error).__name__}', file=sys.stderr)
            return json_response(self, 500, _safe_error('internal_error'), cache_control='no-store')
