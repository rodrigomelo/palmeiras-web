"""GET /api/standings?competition=BSA."""
import sys
from http.server import BaseHTTPRequestHandler
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse

try:
    from api._shared import (
        RequestValidationError,
        competition_param,
        is_configured,
        json_response,
        supabase_get,
        transform_standing,
        upstream_status,
    )
except ImportError:
    from _shared import (  # type: ignore
        RequestValidationError,
        competition_param,
        is_configured,
        json_response,
        supabase_get,
        transform_standing,
        upstream_status,
    )


def _safe_error(code='upstream_error'):
    return {'standings': [], 'error': code}


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        params = parse_qs(urlparse(self.path).query)
        try:
            competition = competition_param(params)
        except RequestValidationError as error:
            return json_response(self, 400, _safe_error(str(error)), cache_control='no-store')

        if not is_configured():
            return json_response(self, 503, _safe_error('not_configured'), cache_control='no-store')

        try:
            rows = supabase_get(
                'standings',
                select='*',
                competition=f'eq.{competition}',
                order='position.asc',
            )
            return json_response(self, 200, {'standings': [transform_standing(row) for row in rows]})
        except HTTPError as error:
            print(f'[api.standings] Supabase HTTP {error.code}', file=sys.stderr)
            return json_response(self, upstream_status(error), _safe_error(f'supabase_{error.code}'), cache_control='no-store')
        except Exception as error:
            print(f'[api.standings] unexpected error: {type(error).__name__}', file=sys.stderr)
            return json_response(self, 500, _safe_error('internal_error'), cache_control='no-store')
