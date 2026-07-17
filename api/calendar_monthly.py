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
        TEAM_ID,
        calendar_match,
        get_first,
        int_param,
        is_configured,
        json_response,
        month_window,
        parse_json,
        normalize_competition_code,
        supabase_get_filtered,
        upstream_status,
        year_month_params,
        cors_options_response,
    )
except ImportError:
    from _shared import (  # type: ignore
        BR_TZ,
        RequestValidationError,
        TEAM_ID,
        calendar_match,
        get_first,
        int_param,
        is_configured,
        json_response,
        month_window,
        parse_json,
        normalize_competition_code,
        supabase_get_filtered,
        upstream_status,
        year_month_params,
        cors_options_response,
    )


def _safe_error(code='upstream_error'):
    return {'error': code, 'days': {}}


def _row_has_team(row, team_id):
    home = parse_json(row.get('home_team', '{}'))
    away = parse_json(row.get('away_team', '{}'))
    return home.get('id') == team_id or away.get('id') == team_id


def _row_competition_code(row):
    comp = parse_json(row.get('competition', '{}'))
    return normalize_competition_code(comp.get('code'))


def _row_is_world_cup(row):
    return _row_competition_code(row) == 'WC'


def _row_belongs_to_default_calendar(row):
    return _row_has_team(row, TEAM_ID) or _row_is_world_cup(row)


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
            year, month = year_month_params(params)
            team_id = None
            if get_first(params, 'team_id', None):
                team_id = int_param(params, 'team_id', TEAM_ID, min_value=1, max_value=999999)
        except RequestValidationError as error:
            return json_response(self, 400, _safe_error(str(error)), cache_control='no-store')

        if not is_configured():
            return json_response(self, 503, _safe_error('not_configured'), cache_control='no-store')

        try:
            start_utc, end_utc = month_window(year, month)
            rows = supabase_get_filtered(
                'matches',
                filters=[('utc_date', f'gte.{start_utc}'), ('utc_date', f'lt.{end_utc}')],
                row_filter=(lambda row: _row_has_team(row, team_id)) if team_id else _row_belongs_to_default_calendar,
                select='*',
                order='utc_date.asc',
                page_size=250,
                max_rows=2000,
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
