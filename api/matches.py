"""GET /api/matches?status=FINISHED&limit=50."""
import sys
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse

try:
    from api._shared import (
        RequestValidationError,
        TEAM_ID,
        get_first,
        int_param,
        is_configured,
        json_response,
        normalize_competition_code,
        optional_competition_param,
        parse_json,
        parse_statuses,
        supabase_get,
        transform_match,
        upstream_status,
        cors_options_response,
        validate_date,
    )
except ImportError:  # Vercel loads handlers from the api directory.
    from _shared import (  # type: ignore
        RequestValidationError,
        TEAM_ID,
        get_first,
        int_param,
        is_configured,
        json_response,
        normalize_competition_code,
        optional_competition_param,
        parse_json,
        parse_statuses,
        supabase_get,
        transform_match,
        upstream_status,
        cors_options_response,
        validate_date,
    )


def _safe_error(collection='matches', code='upstream_error'):
    return {collection: [], 'error': code}


def _exclusive_end_date(value):
    if not value:
        return None
    return (datetime.strptime(value, '%Y-%m-%d').date() + timedelta(days=1)).isoformat()


def _row_competition_code(row):
    comp = parse_json(row.get('competition', '{}'))
    return normalize_competition_code(comp.get('code'))


def _row_has_team(row, team_id):
    home = parse_json(row.get('home_team', '{}'))
    away = parse_json(row.get('away_team', '{}'))
    return home.get('id') == team_id or away.get('id') == team_id


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        cors_options_response(self)

    def do_GET(self):
        params = parse_qs(urlparse(self.path).query)

        try:
            status = params.get('status', [None])[0]
            statuses = parse_statuses(status)
            limit = int_param(params, 'limit', 50, min_value=1, max_value=250)
            competition = optional_competition_param(params)
            team_id = None
            if get_first(params, 'team_id', None):
                team_id = int_param(params, 'team_id', TEAM_ID, min_value=1, max_value=999999)
            from_date = params.get('from_date', [None])[0]
            from_date, date_error = validate_date(from_date)
            if date_error:
                raise RequestValidationError(date_error)
            to_date = params.get('to_date', [None])[0]
            to_date, date_error = validate_date(to_date, 'to_date')
            if date_error:
                raise RequestValidationError(date_error)
        except RequestValidationError as error:
            return json_response(self, 400, _safe_error(code=str(error)), cache_control='no-store')

        if not is_configured():
            return json_response(self, 503, _safe_error(code='not_configured'), cache_control='no-store')

        try:
            finished_only = bool(statuses) and all(s in ('FINISHED', 'PLAYING_TIME_FINISHED') for s in statuses)
            fetch_limit = 600 if (competition or team_id) else max(limit * 3, 50)
            query_params = {
                'select': '*',
                'order': 'utc_date.desc' if finished_only else 'utc_date.asc',
                'limit': str(fetch_limit),
            }
            filters = []

            if statuses:
                if len(statuses) == 1:
                    query_params['status'] = f'eq.{statuses[0]}'
                else:
                    query_params['status'] = f'in.({",".join(statuses)})'
                if any(s in ('SCHEDULED', 'TIMED', 'IN_PLAY', 'PAUSED') for s in statuses) and not from_date:
                    from_date = datetime.now(timezone.utc).strftime('%Y-%m-%d')

            if from_date:
                filters.append(('utc_date', f'gte.{from_date}'))
            if to_date:
                filters.append(('utc_date', f'lt.{_exclusive_end_date(to_date)}'))

            matches = supabase_get('matches', filters=filters, **query_params)
            if competition:
                matches = [m for m in matches if _row_competition_code(m) == competition]
            if team_id:
                matches = [m for m in matches if _row_has_team(m, team_id)]
            if finished_only:
                matches.sort(key=lambda x: x.get('utc_date', ''), reverse=True)
            matches = matches[:limit]
            return json_response(self, 200, {'matches': [transform_match(m) for m in matches]})
        except HTTPError as error:
            print(f'[api.matches] Supabase HTTP {error.code}', file=sys.stderr)
            return json_response(self, upstream_status(error), _safe_error(code=f'supabase_{error.code}'), cache_control='no-store')
        except Exception as error:
            print(f'[api.matches] unexpected error: {type(error).__name__}', file=sys.stderr)
            return json_response(self, 500, _safe_error(code='internal_error'), cache_control='no-store')
