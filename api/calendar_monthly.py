"""GET /api/calendar_monthly?year=YYYY&month=MM — monthly calendar data."""
import sys
from datetime import datetime
from http.server import BaseHTTPRequestHandler
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse

try:
    from api._shared import (
        BR_TZ,
        RequestValidationError,
        calendar_match,
        is_configured,
        json_response,
        month_window,
        supabase_get,
        upstream_status,
        year_month_params,
        cors_options_response,
    )
except ImportError:
    from _shared import (  # type: ignore
        BR_TZ,
        RequestValidationError,
        calendar_match,
        is_configured,
        json_response,
        month_window,
        supabase_get,
        upstream_status,
        year_month_params,
        cors_options_response,
    )


def _safe_error(code='upstream_error'):
    return {'error': code, 'days': {}}


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        cors_options_response(self)

    def do_GET(self):
        params = parse_qs(urlparse(self.path).query)
        try:
            year, month = year_month_params(params)
        except RequestValidationError as error:
            return json_response(self, 400, _safe_error(str(error)), cache_control='no-store')

        if not is_configured():
            return json_response(self, 503, _safe_error('not_configured'), cache_control='no-store')

        try:
            start_utc, end_utc = month_window(year, month)
            rows = supabase_get(
                'matches',
                filters=[('utc_date', f'gte.{start_utc}'), ('utc_date', f'lt.{end_utc}')],
                select='*',
                order='utc_date.asc',
                limit='250',
            )

            days = {}
            for row in rows:
                utc_date = row.get('utc_date')
                if not utc_date:
                    continue
                try:
                    dt = datetime.fromisoformat(utc_date.replace('Z', '+00:00')).astimezone(BR_TZ)
                except ValueError:
                    continue
                if dt.year != year or dt.month != month:
                    continue
                days.setdefault(dt.strftime('%Y-%m-%d'), []).append(calendar_match(row))

            return json_response(self, 200, {'year': year, 'month': month, 'days': days}, cache_control='public, max-age=900')
        except HTTPError as error:
            print(f'[api.calendar_monthly] Supabase HTTP {error.code}', file=sys.stderr)
            return json_response(self, upstream_status(error), _safe_error(f'supabase_{error.code}'), cache_control='no-store')
        except Exception as error:
            print(f'[api.calendar_monthly] unexpected error: {type(error).__name__}', file=sys.stderr)
            return json_response(self, 500, _safe_error('internal_error'), cache_control='no-store')
