"""GET /api/matches?status=FINISHED&limit=50."""
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse

try:
    from api._shared import (
        RequestValidationError,
        int_param,
        is_configured,
        json_response,
        parse_statuses,
        supabase_get,
        transform_match,
        upstream_status,
    )
except ImportError:  # Vercel loads handlers from the api directory.
    from _shared import (  # type: ignore
        RequestValidationError,
        int_param,
        is_configured,
        json_response,
        parse_statuses,
        supabase_get,
        transform_match,
        upstream_status,
    )


def _safe_error(collection='matches', code='upstream_error'):
    return {collection: [], 'error': code}


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        params = parse_qs(urlparse(self.path).query)

        try:
            status = params.get('status', [None])[0]
            statuses = parse_statuses(status)
            limit = int_param(params, 'limit', 50, min_value=1, max_value=100)
            from_date = params.get('from_date', [None])[0]
        except RequestValidationError as error:
            return json_response(self, 400, _safe_error(code=str(error)), cache_control='no-store')

        if not is_configured():
            return json_response(self, 503, _safe_error(code='not_configured'), cache_control='no-store')

        try:
            query_params = {'select': '*', 'order': 'utc_date.asc', 'limit': str(max(limit * 3, 50))}

            if statuses:
                if len(statuses) == 1:
                    query_params['status'] = f'eq.{statuses[0]}'
                else:
                    query_params['status'] = f'in.({",".join(statuses)})'
                if any(s in ('SCHEDULED', 'TIMED', 'IN_PLAY', 'PAUSED') for s in statuses) and not from_date:
                    from_date = datetime.now(timezone.utc).strftime('%Y-%m-%d')

            if from_date:
                query_params['utc_date'] = f'gte.{from_date}'

            matches = supabase_get('matches', **query_params)
            if any(m.get('status') == 'FINISHED' for m in matches):
                matches.sort(key=lambda x: x.get('utc_date', ''), reverse=True)
            matches = matches[:limit]
            return json_response(self, 200, {'matches': [transform_match(m) for m in matches]})
        except HTTPError as error:
            print(f'[api.matches] Supabase HTTP {error.code}', file=sys.stderr)
            return json_response(self, upstream_status(error), _safe_error(code=f'supabase_{error.code}'), cache_control='no-store')
        except Exception as error:
            print(f'[api.matches] unexpected error: {type(error).__name__}', file=sys.stderr)
            return json_response(self, 500, _safe_error(code='internal_error'), cache_control='no-store')
