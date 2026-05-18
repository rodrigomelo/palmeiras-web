"""Shared helpers for Palmeiras Web serverless API handlers.

The public API is read-only. It prefers the Supabase anon key so RLS remains
active in production, while keeping SUPABASE_KEY as a legacy fallback for older
Vercel environments until SUPABASE_ANON_KEY is configured.
"""
import json
import os
from datetime import datetime, timezone, timedelta
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

SUPABASE_URL = os.environ.get('SUPABASE_URL', '').rstrip('/')
SUPABASE_ANON_KEY = (
    os.environ.get('SUPABASE_ANON_KEY')
    or os.environ.get('SUPABASE_PUBLIC_KEY')
    or os.environ.get('SUPABASE_KEY', '')
)
SUPABASE_SERVICE_ROLE_KEY = os.environ.get('SUPABASE_SERVICE_ROLE_KEY') or os.environ.get('SUPABASE_KEY', '')
BR_TZ = timezone(timedelta(hours=-3))
TEAM_ID = 1769
REQUEST_TIMEOUT = 10

ALLOWED_STATUSES = {
    'SCHEDULED',
    'TIMED',
    'IN_PLAY',
    'PAUSED',
    'FINISHED',
    'PLAYING_TIME_FINISHED',
    'POSTPONED',
    'SUSPENDED',
    'CANCELLED',
}
ALLOWED_COMPETITIONS = {'BSA', 'CLI', 'LIBERTADORES', 'COPA', 'COPA_DO_BRASIL'}


class RequestValidationError(ValueError):
    """Raised when an API query parameter is invalid."""


def is_configured(key=None):
    """Return True when the Supabase REST API can be called."""
    return bool(SUPABASE_URL and (key or SUPABASE_ANON_KEY))


def get_first(params, name, default=None):
    """Read the first value from parse_qs-style params."""
    values = params.get(name, [default])
    return values[0] if values else default


def int_param(params, name, default, *, min_value=None, max_value=None):
    """Parse and clamp an integer query parameter."""
    raw = get_first(params, name, str(default))
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise RequestValidationError(f'{name} must be an integer')

    if min_value is not None and value < min_value:
        raise RequestValidationError(f'{name} must be at least {min_value}')
    if max_value is not None and value > max_value:
        value = max_value
    return value


def parse_statuses(status):
    """Validate a comma-separated status filter."""
    if not status:
        return []
    statuses = [s.strip().upper() for s in status.split(',') if s.strip()]
    invalid = [s for s in statuses if s not in ALLOWED_STATUSES]
    if invalid:
        raise RequestValidationError(f'invalid status: {", ".join(invalid)}')
    return statuses


def competition_param(params, default='BSA'):
    """Validate a competition code query parameter."""
    competition = str(get_first(params, 'competition', default) or default).strip().upper()
    if competition not in ALLOWED_COMPETITIONS:
        raise RequestValidationError('invalid competition')
    return competition


def year_month_params(params):
    """Validate year/month query parameters for monthly calendar data."""
    year = int_param(params, 'year', datetime.now(BR_TZ).year, min_value=2020, max_value=2035)
    month = int_param(params, 'month', datetime.now(BR_TZ).month, min_value=1, max_value=12)
    return year, month


def parse_json(value, default=None):
    """Parse JSON stored as text in Supabase, preserving dict/list values."""
    if default is None:
        default = {}
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return default.copy() if isinstance(default, (dict, list)) else default
    if isinstance(default, dict) and isinstance(value, dict):
        return value
    if isinstance(default, list) and isinstance(value, list):
        return value
    return default.copy() if isinstance(default, (dict, list)) else default


def supabase_headers(key=None):
    """Headers for a read-only Supabase REST request."""
    token = key or SUPABASE_ANON_KEY
    return {
        'apikey': token,
        'Authorization': f'Bearer {token}',
        'Accept': 'application/json',
    }


def supabase_get(table, *, filters=None, timeout=REQUEST_TIMEOUT, key=None, **params):
    """GET rows from Supabase REST with optional repeated filters."""
    if not is_configured(key):
        raise RuntimeError('supabase_not_configured')

    query_parts = []
    for name, value in filters or []:
        query_parts.append(urlencode({name: value}))
    if params:
        query_parts.append(urlencode(params, doseq=True))

    qs = '&'.join(query_parts)
    url = f'{SUPABASE_URL}/rest/v1/{table}' + (f'?{qs}' if qs else '')
    request = Request(url, headers=supabase_headers(key))
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


def transform_match(row):
    """Convert a Supabase match row to the public frontend contract."""
    return {
        'id': row.get('external_id'),
        'utcDate': row.get('utc_date'),
        'status': row.get('status'),
        'matchday': row.get('matchday'),
        'stage': row.get('stage'),
        'venue': row.get('venue'),
        'broadcast': row.get('broadcast'),
        'homeTeam': parse_json(row.get('home_team', '{}')),
        'awayTeam': parse_json(row.get('away_team', '{}')),
        'competition': parse_json(row.get('competition', '{}')),
        'season': parse_json(row.get('season', '{}')),
        'referees': parse_json(row.get('referees', '[]'), []),
        'score': {
            'fullTime': {'home': row.get('home_score'), 'away': row.get('away_score')},
            'halfTime': {'home': row.get('half_time_home'), 'away': row.get('half_time_away')},
        },
        'homeScore': row.get('home_score'),
        'awayScore': row.get('away_score'),
    }


def transform_standing(row):
    """Convert a Supabase standing row to the public frontend contract."""
    team = parse_json(row.get('team', '{}'))
    return {
        'position': row.get('position'),
        'teamId': team.get('id'),
        'teamName': team.get('name', ''),
        'teamShort': team.get('shortName', team.get('name', '')),
        'teamTla': team.get('tla', ''),
        'crest': team.get('crest', ''),
        'playedGames': row.get('played_games'),
        'won': row.get('won'),
        'draw': row.get('drawn'),
        'lost': row.get('lost'),
        'points': row.get('points'),
        'goalsFor': row.get('goals_for'),
        'goalsAgainst': row.get('goals_against'),
        'goalDifference': row.get('goal_difference'),
    }


def calendar_match(row):
    """Convert a match row to the compact calendar-month contract."""
    match = transform_match(row)
    return {
        'utcDate': match['utcDate'],
        'status': match['status'] or 'SCHEDULED',
        'competition': {
            'code': match['competition'].get('code', 'OTHER'),
            'name': match['competition'].get('name', 'Outros'),
        },
        'homeTeam': {
            'id': match['homeTeam'].get('id'),
            'name': match['homeTeam'].get('name', 'Home'),
            'shortName': match['homeTeam'].get('shortName', ''),
            'crest': match['homeTeam'].get('crest', ''),
        },
        'awayTeam': {
            'id': match['awayTeam'].get('id'),
            'name': match['awayTeam'].get('name', 'Away'),
            'shortName': match['awayTeam'].get('shortName', ''),
            'crest': match['awayTeam'].get('crest', ''),
        },
        'matchday': match['matchday'],
        'venue': match['venue'] or '',
        'broadcast': match['broadcast'] or '',
        'homeScore': match['homeScore'],
        'awayScore': match['awayScore'],
        'score': {'fullTime': match['score']['fullTime']},
    }


def month_window(year, month):
    """Return UTC start/end filters for a month in Sao Paulo time."""
    start_dt = datetime(year, month, 1, 0, 0, 0, tzinfo=BR_TZ)
    if month == 12:
        end_dt = datetime(year + 1, 1, 1, 0, 0, 0, tzinfo=BR_TZ)
    else:
        end_dt = datetime(year, month + 1, 1, 0, 0, 0, tzinfo=BR_TZ)
    return (
        start_dt.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S'),
        end_dt.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S'),
    )


def json_response(handler, status, data, *, cache_control='public, max-age=300'):
    """Send a JSON response with safe defaults."""
    body = json.dumps(data, ensure_ascii=False).encode('utf-8')
    handler.send_response(status)
    handler.send_header('Content-Type', 'application/json; charset=utf-8')
    handler.send_header('Cache-Control', cache_control)
    handler.send_header('X-Content-Type-Options', 'nosniff')
    handler.end_headers()
    handler.wfile.write(body)


def text_response(handler, status, text, *, content_type='text/plain; charset=utf-8', cache_control='public, max-age=300'):
    """Send a text response with safe defaults."""
    handler.send_response(status)
    handler.send_header('Content-Type', content_type)
    handler.send_header('Cache-Control', cache_control)
    handler.send_header('X-Content-Type-Options', 'nosniff')
    handler.end_headers()
    handler.wfile.write(str(text).encode('utf-8'))


def upstream_status(error):
    """Map Supabase/urllib errors to a public status code."""
    if isinstance(error, HTTPError) and 400 <= error.code < 500:
        return error.code
    return 502
