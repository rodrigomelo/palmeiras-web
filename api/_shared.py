"""Shared helpers for Palmeiras Web serverless API handlers.

The public API is read-only and must run with a Supabase anon/publishable key.
Collector-only service keys are intentionally rejected here so public handlers
never bypass Row Level Security by accident.
"""
import base64
import binascii
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
    or (
        os.environ.get('SUPABASE_KEY', '')
        if os.environ.get('ALLOW_SERVICE_ROLE_PUBLIC_API') == '1'
        else ''
    )
    or ''
)
ALLOW_SERVICE_ROLE_PUBLIC_API = os.environ.get('ALLOW_SERVICE_ROLE_PUBLIC_API') == '1'
BR_TZ = timezone(timedelta(hours=-3))
TEAM_ID = 1769
REQUEST_TIMEOUT = 10
APP_VERSION = os.environ.get('APP_VERSION', '1.1.37')

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
COMPETITION_ALIASES = {
    'BSA': 'BSA',
    'CLI': 'CLI',
    'CL': 'CLI',
    'LIBERTADORES': 'CLI',
    'COPA_LIBERTADORES': 'CLI',
    'COPA': 'COPA',
    'CBC': 'COPA',
    'COPA_DO_BRASIL': 'COPA',
    'CPA': 'CPA',
    'CAMPEONATO_PAULISTA': 'CPA',
    'PAULISTA': 'CPA',
    'WC': 'WC',
    'WORLD_CUP': 'WC',
    'FIFA_WORLD_CUP': 'WC',
}
ALLOWED_COMPETITIONS = set(COMPETITION_ALIASES)


class RequestValidationError(ValueError):
    """Raised when an API query parameter is invalid."""


def _jwt_payload(token):
    """Decode a JWT payload without verifying it; used only for role guardrails."""
    try:
        payload = token.split('.')[1]
        payload += '=' * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload.encode('ascii')).decode('utf-8'))
    except (IndexError, ValueError, UnicodeDecodeError, binascii.Error, json.JSONDecodeError):
        return {}


def supabase_key_role(token):
    """Best-effort Supabase JWT role extraction."""
    if not token or token.count('.') < 2:
        return ''
    return str(_jwt_payload(token).get('role', '')).lower()


def is_public_supabase_key(token=None):
    """Return False for keys that are known to be privileged server-side secrets."""
    token = token or SUPABASE_ANON_KEY
    if not token:
        return False

    lowered = token.lower()
    if lowered.startswith('sb_secret_'):
        return False
    return supabase_key_role(token) != 'service_role'


def is_configured(key=None):
    """Return True when the Supabase REST API can be called safely."""
    token = key or SUPABASE_ANON_KEY
    return bool(SUPABASE_URL and (is_public_supabase_key(token) or (ALLOW_SERVICE_ROLE_PUBLIC_API and token)))


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


def normalize_competition_code(code):
    """Normalize known competition aliases to their stored canonical code."""
    return COMPETITION_ALIASES.get(str(code or '').strip().upper(), str(code or '').strip().upper())


def competition_param(params, default='BSA'):
    """Validate a competition code query parameter."""
    competition = str(get_first(params, 'competition', default) or default).strip().upper()
    if competition not in ALLOWED_COMPETITIONS:
        raise RequestValidationError('invalid competition')
    return normalize_competition_code(competition)


def optional_competition_param(params):
    """Validate an optional competition code query parameter."""
    raw = get_first(params, 'competition', None)
    if not raw:
        return None
    competition = str(raw).strip().upper()
    if competition not in ALLOWED_COMPETITIONS:
        raise RequestValidationError('invalid competition')
    return normalize_competition_code(competition)


def year_month_params(params):
    """Validate year/month query parameters for monthly calendar data."""
    year = int_param(params, 'year', datetime.now(BR_TZ).year, min_value=2020, max_value=2035)
    month = int_param(params, 'month', datetime.now(BR_TZ).month, min_value=1, max_value=12)
    return year, month


def validate_date(value, param_name='from_date'):
    """Validate a date query parameter matches a real YYYY-MM-DD date."""
    if not value:
        return None, None
    import re
    if not re.match(r'^\d{4}-\d{2}-\d{2}$', value):
        return None, f'Invalid {param_name} format, expected YYYY-MM-DD'
    try:
        datetime.strptime(value, '%Y-%m-%d')
    except ValueError:
        return None, f'Invalid {param_name} value, expected a real YYYY-MM-DD date'
    return value, None


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
        raise RuntimeError('supabase_public_key_required')

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


def supabase_get_filtered(
    table,
    *,
    filters=None,
    row_filter=None,
    stop_after=None,
    page_size=500,
    max_rows=5000,
    timeout=REQUEST_TIMEOUT,
    key=None,
    **params,
):
    """GET rows across pages, applying optional local JSON-field filtering."""
    collected = []
    offset = 0
    page_size = max(1, min(int(page_size), 1000))
    max_rows = max(page_size, int(max_rows))

    while offset < max_rows:
        limit = min(page_size, max_rows - offset)
        page = supabase_get(
            table,
            filters=filters,
            timeout=timeout,
            key=key,
            limit=str(limit),
            offset=str(offset),
            **params,
        )
        if not page:
            break

        for row in page:
            if row_filter is None or row_filter(row):
                collected.append(row)
                if stop_after and len(collected) >= stop_after:
                    return collected

        if len(page) < limit:
            break
        offset += limit

    return collected


def transform_match(row):
    """Convert a Supabase match row to the public frontend contract."""
    home_team = parse_json(row.get('home_team', '{}'))
    away_team = parse_json(row.get('away_team', '{}'))

    def clean_team(team):
        name = team.get('name') or team.get('shortName') or 'A definir'
        cleaned = dict(team)
        cleaned['name'] = name
        cleaned['shortName'] = team.get('shortName') or name
        return cleaned

    return {
        'id': row.get('external_id'),
        'utcDate': row.get('utc_date'),
        'status': row.get('status'),
        'matchday': row.get('matchday'),
        'stage': row.get('stage'),
        'venue': row.get('venue'),
        'broadcast': row.get('broadcast'),
        'homeTeam': clean_team(home_team),
        'awayTeam': clean_team(away_team),
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
    home_name = match['homeTeam'].get('name') or match['homeTeam'].get('shortName') or 'A definir'
    away_name = match['awayTeam'].get('name') or match['awayTeam'].get('shortName') or 'A definir'
    return {
        'utcDate': match['utcDate'],
        'status': match['status'] or 'SCHEDULED',
        'competition': {
            'code': match['competition'].get('code', 'OTHER'),
            'name': match['competition'].get('name', 'Outros'),
        },
        'homeTeam': {
            'id': match['homeTeam'].get('id'),
            'name': home_name,
            'shortName': match['homeTeam'].get('shortName') or home_name,
            'crest': match['homeTeam'].get('crest', ''),
        },
        'awayTeam': {
            'id': match['awayTeam'].get('id'),
            'name': away_name,
            'shortName': match['awayTeam'].get('shortName') or away_name,
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


def _should_write_body(handler):
    return not getattr(handler, '_suppress_body', False)


def json_response(handler, status, data, *, cache_control='public, max-age=300'):
    """Send a JSON response with safe defaults and CORS headers."""
    body = json.dumps(data, ensure_ascii=False).encode('utf-8')
    handler.send_response(status)
    handler.send_header('Content-Type', 'application/json; charset=utf-8')
    handler.send_header('Cache-Control', cache_control)
    handler.send_header('X-Content-Type-Options', 'nosniff')
    handler.send_header('Access-Control-Allow-Origin', '*')
    handler.send_header('Access-Control-Allow-Methods', 'GET, HEAD, OPTIONS')
    handler.send_header('Access-Control-Allow-Headers', 'Content-Type')
    handler.end_headers()
    if _should_write_body(handler):
        handler.wfile.write(body)


def text_response(handler, status, text, *, content_type='text/plain; charset=utf-8', cache_control='public, max-age=300'):
    """Send a text response with safe defaults and CORS headers."""
    handler.send_response(status)
    handler.send_header('Content-Type', content_type)
    handler.send_header('Cache-Control', cache_control)
    handler.send_header('X-Content-Type-Options', 'nosniff')
    handler.send_header('Access-Control-Allow-Origin', '*')
    handler.send_header('Access-Control-Allow-Methods', 'GET, HEAD, OPTIONS')
    handler.send_header('Access-Control-Allow-Headers', 'Content-Type')
    handler.end_headers()
    if _should_write_body(handler):
        handler.wfile.write(str(text).encode('utf-8'))


def upstream_status(error):
    """Map Supabase/urllib errors to a public status code."""
    if isinstance(error, HTTPError) and 400 <= error.code < 500:
        return error.code
    return 502


def cors_options_response(handler):
    """Respond to a CORS preflight OPTIONS request."""
    handler.send_response(204)
    handler.send_header('Access-Control-Allow-Origin', '*')
    handler.send_header('Access-Control-Allow-Methods', 'GET, HEAD, OPTIONS')
    handler.send_header('Access-Control-Allow-Headers', 'Content-Type')
    handler.send_header('Content-Length', '0')
    handler.end_headers()
