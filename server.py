"""
Palmeiras Web - Static/API HTTP server

Direct Supabase access with the same public API contracts used by the web and
mobile apps. This server is intentionally small and read-only. By default it
serves local development on port 5001; production can override HOST and PORT.

Usage:
    /opt/homebrew/bin/python3 apps/web/server.py
    open http://localhost:5001
"""
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# Load .env before importing shared API helpers so helper-level environment
# constants see local development credentials.
DIRECTORY = Path(__file__).resolve().parent
PROJECT_ROOT = DIRECTORY.parents[1]

for env_path in (PROJECT_ROOT / '.env', DIRECTORY / '.env'):
    if env_path.exists():
        with env_path.open() as env_file:
            for line in env_file:
                line = line.strip()
                if '=' in line and not line.startswith('#'):
                    key, value = line.split('=', 1)
                    os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

from api._shared import (  # noqa: E402
    APP_VERSION,
    RequestValidationError,
    BR_TZ,
    TEAM_ID,
    calendar_match,
    competition_param,
    get_first,
    int_param,
    is_public_supabase_key,
    month_window,
    normalize_competition_code,
    optional_competition_param,
    parse_json,
    parse_statuses,
    supabase_get,
    transform_match,
    transform_standing,
    year_month_params,
)
from api._shared import validate_date  # noqa: E402
from api.calendar import render_calendar  # noqa: E402

SUPABASE_URL = os.environ.get('SUPABASE_URL', '')
# Read-only API: use anon key only (preserves RLS).  The service_role key
# (SUPABASE_KEY) is excluded unless a temporary migration flag is explicitly set.
ALLOW_SERVICE_ROLE_PUBLIC_API = os.environ.get('ALLOW_SERVICE_ROLE_PUBLIC_API') == '1'
SUPABASE_KEY = (
    os.environ.get('SUPABASE_ANON_KEY')
    or os.environ.get('SUPABASE_PUBLIC_KEY')
    or (os.environ.get('SUPABASE_KEY', '') if ALLOW_SERVICE_ROLE_PUBLIC_API else '')
    or ''
)
HOST = os.environ.get('HOST', '0.0.0.0')
PORT = int(os.environ.get('PORT', '5001'))
DEFAULT_ALLOWED_ORIGINS = {
    'http://localhost:5001',
    'http://localhost:3000',
    'https://palmeiras.rodrigolanna.com.br',
}
ALLOWED_ORIGINS = {
    origin.strip()
    for origin in os.environ.get('ALLOWED_ORIGINS', '').split(',')
    if origin.strip()
} or DEFAULT_ALLOWED_ORIGINS
BLOCKED_NEWS_SOURCES = {
    'facebook.com',
    'instagram.com',
    'threads.net',
    'tiktok.com',
    'twitter.com',
    'x.com',
    'youtube.com',
}

_client = None


def get_client():
    """Return a cached Supabase client for local development."""
    global _client
    if _client is not None:
        return _client
    if not SUPABASE_URL or not (is_public_supabase_key(SUPABASE_KEY) or (ALLOW_SERVICE_ROLE_PUBLIC_API and SUPABASE_KEY)):
        return None
    try:
        from supabase import create_client
        _client = create_client(SUPABASE_URL, SUPABASE_KEY)
        return _client
    except Exception as error:
        print(f'[supabase] connection failed: {type(error).__name__}', file=sys.stderr)
        return None


def _public_news_items(rows, limit):
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


def _safe_error(collection, code):
    return {collection: [], 'error': code}


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


def _exclusive_end_date(value):
    if not value:
        return None
    return (datetime.strptime(value, '%Y-%m-%d').date() + timedelta(days=1)).isoformat()


def _year_window(year):
    start = datetime(year, 1, 1, 0, 0, 0, tzinfo=BR_TZ)
    end = datetime(year + 1, 1, 1, 0, 0, 0, tzinfo=BR_TZ)
    return (
        start.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S'),
        end.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S'),
    )


def _row_competition_code(row):
    comp = parse_json(row.get('competition', '{}'))
    return normalize_competition_code(comp.get('code'))


def _row_has_team(row, team_id):
    home = parse_json(row.get('home_team', '{}'))
    away = parse_json(row.get('away_team', '{}'))
    return home.get('id') == team_id or away.get('id') == team_id


def _row_has_team_tla(row, team_tla):
    home = parse_json(row.get('home_team', '{}'))
    away = parse_json(row.get('away_team', '{}'))
    return str(home.get('tla', '')).upper() == team_tla or str(away.get('tla', '')).upper() == team_tla


def _row_is_world_cup(row):
    return _row_competition_code(row) == 'WC'


def _row_belongs_to_default_calendar(row):
    return _row_has_team(row, TEAM_ID) or _row_is_world_cup(row)


def _team_result(match, team_id):
    home_id = match['homeTeam'].get('id')
    away_id = match['awayTeam'].get('id')
    if home_id != team_id and away_id != team_id:
        return None

    home_score = match.get('homeScore')
    away_score = match.get('awayScore')
    if home_score is None or away_score is None:
        return None

    team_home = home_id == team_id
    goals_for = home_score if team_home else away_score
    goals_against = away_score if team_home else home_score

    if goals_for > goals_against:
        result = 'W'
        points = 3
    elif goals_for < goals_against:
        result = 'L'
        points = 0
    else:
        result = 'D'
        points = 1

    return {
        'result': result,
        'points': points,
        'goalsFor': goals_for,
        'goalsAgainst': goals_against,
    }


def _compact_match(match):
    return {
        'id': match.get('id'),
        'utcDate': match.get('utcDate'),
        'status': match.get('status'),
        'matchday': match.get('matchday'),
        'stage': match.get('stage'),
        'venue': match.get('venue'),
        'broadcast': match.get('broadcast'),
        'homeTeam': match.get('homeTeam'),
        'awayTeam': match.get('awayTeam'),
        'competition': match.get('competition'),
        'score': match.get('score'),
        'homeScore': match.get('homeScore'),
        'awayScore': match.get('awayScore'),
    }


def _fetch_query_pages(query_factory, *, row_filter=None, stop_after=None, page_size=500, max_rows=5000):
    """Fetch Supabase query-builder results across pages."""
    rows = []
    offset = 0
    page_size = max(1, min(int(page_size), 1000))
    max_rows = max(page_size, int(max_rows))

    while offset < max_rows:
        limit = min(page_size, max_rows - offset)
        page = query_factory().range(offset, offset + limit - 1).execute().data or []
        if not page:
            break

        for row in page:
            if row_filter is None or row_filter(row):
                rows.append(row)
                if stop_after and len(rows) >= stop_after:
                    return rows

        if len(page) < limit:
            break
        offset += limit

    return rows


def api_matches(params):
    """Return match rows in the public frontend contract."""
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
        return 400, _safe_error('matches', str(error)), 'application/json', 'no-store'

    client = get_client()
    if not client:
        return 503, _safe_error('matches', 'not_connected'), 'application/json', 'no-store'

    try:
        finished_only = bool(statuses) and all(s in ('FINISHED', 'PLAYING_TIME_FINISHED') for s in statuses)
        if statuses and any(s in ('SCHEDULED', 'TIMED', 'IN_PLAY', 'PAUSED') for s in statuses) and not from_date:
            from_date = datetime.now(timezone.utc).strftime('%Y-%m-%d')

        def query_factory():
            query = client.table('matches').select('*')
            if statuses:
                if len(statuses) == 1:
                    query = query.eq('status', statuses[0])
                else:
                    query = query.in_('status', statuses)
            if from_date:
                query = query.gte('utc_date', from_date)
            if to_date:
                query = query.lt('utc_date', _exclusive_end_date(to_date))
            return query.order('utc_date', desc=finished_only)

        def row_matches(row):
            if competition and _row_competition_code(row) != competition:
                return False
            if team_id and not _row_has_team(row, team_id):
                return False
            return True

        if competition or team_id:
            rows = _fetch_query_pages(
                query_factory,
                row_filter=row_matches,
                stop_after=limit,
                page_size=500,
                max_rows=5000,
            )
        else:
            rows = query_factory().limit(max(limit * 3, 50)).execute().data or []
        if finished_only:
            rows.sort(key=lambda row: row.get('utc_date', ''), reverse=True)
        return 200, {'matches': [transform_match(row) for row in rows[:limit]]}
    except Exception as error:
        print(f'[api_matches] unexpected error: {type(error).__name__}', file=sys.stderr)
        return 500, _safe_error('matches', 'internal_error'), 'application/json', 'no-store'


def api_standings(params):
    """Return league standings."""
    try:
        competition = competition_param(params)
        limit = min(int(params.get('limit', [100])[0]), 100)
    except RequestValidationError as error:
        return 400, _safe_error('standings', str(error)), 'application/json', 'no-store'

    client = get_client()
    if not client:
        return 503, _safe_error('standings', 'not_connected'), 'application/json', 'no-store'

    try:
        rows = (
            client.table('standings')
            .select('*')
            .eq('competition', competition)
            .order('position')
            .limit(limit)
            .execute()
            .data
            or []
        )
        return 200, {'standings': [transform_standing(row) for row in rows]}
    except Exception as error:
        print(f'[api_standings] unexpected error: {type(error).__name__}', file=sys.stderr)
        return 500, _safe_error('standings', 'internal_error'), 'application/json', 'no-store'


def api_competitions(params):
    """Return Palmeiras competition summaries for a calendar year."""
    try:
        year = int_param(params, 'year', datetime.now(BR_TZ).year, min_value=2020, max_value=2035)
        team_id = int_param(params, 'team_id', TEAM_ID, min_value=1, max_value=999999)
    except RequestValidationError as error:
        return 400, {'competitions': [], 'error': str(error)}, 'application/json', 'no-store'

    client = get_client()
    if not client:
        return 503, {'competitions': [], 'error': 'not_connected'}, 'application/json', 'no-store'

    try:
        start_utc, end_utc = _year_window(year)

        def matches_query_factory():
            return (
                client.table('matches')
                .select('*')
                .gte('utc_date', start_utc)
                .lt('utc_date', end_utc)
                .order('utc_date')
            )

        rows = _fetch_query_pages(
            matches_query_factory,
            row_filter=lambda row: _row_has_team(row, team_id),
            page_size=500,
            max_rows=5000,
        )
        matches = [transform_match(row) for row in rows]

        standings_by_comp = {}
        try:
            standings_rows = (
                client.table('standings')
                .select('*')
                .order('competition')
                .order('position')
                .limit(400)
                .execute()
                .data
                or []
            )
            for row in standings_rows:
                standing = transform_standing(row)
                if standing.get('teamId') == team_id:
                    standings_by_comp[normalize_competition_code(row.get('competition'))] = standing
        except Exception as error:
            print(f'[api_competitions] standings summary warning: {type(error).__name__}', file=sys.stderr)

        summaries = {}
        now = datetime.now(timezone.utc)
        for match in matches:
            competition = match.get('competition') or {}
            code = normalize_competition_code(competition.get('code') or 'OTHER') or 'OTHER'
            name = competition.get('name') or code
            summary = summaries.setdefault(
                code,
                {
                    'code': code,
                    'name': name,
                    'year': year,
                    'totalMatches': 0,
                    'finished': 0,
                    'upcoming': 0,
                    'live': 0,
                    'record': {
                        'played': 0,
                        'wins': 0,
                        'draws': 0,
                        'losses': 0,
                        'goalsFor': 0,
                        'goalsAgainst': 0,
                        'goalDifference': 0,
                        'points': 0,
                    },
                    'nextMatch': None,
                    'lastMatch': None,
                    'currentStage': None,
                    'standing': standings_by_comp.get(code),
                },
            )

            summary['totalMatches'] += 1
            status = match.get('status')
            if status in ('IN_PLAY', 'PAUSED'):
                summary['live'] += 1
            elif status in ('FINISHED', 'PLAYING_TIME_FINISHED'):
                summary['finished'] += 1
            elif status in ('SCHEDULED', 'TIMED'):
                summary['upcoming'] += 1

            result = _team_result(match, team_id)
            if result and status in ('FINISHED', 'PLAYING_TIME_FINISHED', 'IN_PLAY', 'PAUSED'):
                record = summary['record']
                record['played'] += 1
                record['goalsFor'] += result['goalsFor']
                record['goalsAgainst'] += result['goalsAgainst']
                record['goalDifference'] = record['goalsFor'] - record['goalsAgainst']
                record['points'] += result['points']
                if result['result'] == 'W':
                    record['wins'] += 1
                elif result['result'] == 'L':
                    record['losses'] += 1
                else:
                    record['draws'] += 1

            utc_date = match.get('utcDate')
            try:
                match_dt = datetime.fromisoformat(str(utc_date).replace('Z', '+00:00')) if utc_date else None
            except ValueError:
                match_dt = None

            compact = _compact_match(match)
            if status in ('IN_PLAY', 'PAUSED') or (
                status in ('SCHEDULED', 'TIMED') and match_dt and match_dt >= now - timedelta(hours=3)
            ):
                current_next = summary['nextMatch']
                if not current_next or utc_date < current_next.get('utcDate', ''):
                    summary['nextMatch'] = compact

            if status in ('FINISHED', 'PLAYING_TIME_FINISHED'):
                current_last = summary['lastMatch']
                if not current_last or utc_date > current_last.get('utcDate', ''):
                    summary['lastMatch'] = compact

            if not summary['currentStage'] and match.get('stage'):
                summary['currentStage'] = match.get('stage')
            if summary['nextMatch'] and summary['nextMatch'].get('stage'):
                summary['currentStage'] = summary['nextMatch'].get('stage')
            elif summary['lastMatch'] and summary['lastMatch'].get('stage'):
                summary['currentStage'] = summary['lastMatch'].get('stage')

        competition_order = {'BSA': 0, 'CLI': 1, 'COPA': 2, 'CPA': 3}
        competitions = sorted(
            summaries.values(),
            key=lambda item: (
                0 if item['live'] else 1,
                item['nextMatch']['utcDate'] if item['nextMatch'] else '9999-12-31T00:00:00Z',
                competition_order.get(item['code'], 50),
                item['name'],
            ),
        )
        return 200, {'year': year, 'teamId': team_id, 'competitions': competitions}
    except Exception as error:
        print(f'[api_competitions] unexpected error: {type(error).__name__}', file=sys.stderr)
        return 500, {'competitions': [], 'error': 'internal_error'}, 'application/json', 'no-store'


def api_news(params):
    """Return recent news."""
    try:
        limit = int_param(params, 'limit', 20, min_value=1, max_value=50)
    except RequestValidationError as error:
        return 400, _safe_error('news', str(error)), 'application/json', 'no-store'

    client = get_client()
    if not client:
        return 503, _safe_error('news', 'not_connected'), 'application/json', 'no-store'

    try:
        rows = (
            client.table('news')
            .select('*')
            .order('published_at', desc=True, nullsfirst=False)
            .order('collected_at', desc=True)
            .limit(min(limit * 3, 100))
            .execute()
            .data
            or []
        )
        rows = _public_news_items(rows, limit)
        return 200, {'news': rows}, 'application/json', 'public, max-age=60'
    except Exception as error:
        print(f'[api_news] unexpected error: {type(error).__name__}', file=sys.stderr)
        return 500, _safe_error('news', 'internal_error'), 'application/json', 'no-store'


def api_calendar_monthly(params):
    """Return matches grouped by local Sao Paulo calendar day."""
    try:
        year, month = year_month_params(params)
        team_id = None
        if get_first(params, 'team_id', None):
            team_id = int_param(params, 'team_id', TEAM_ID, min_value=1, max_value=999999)
    except RequestValidationError as error:
        return 400, {'error': str(error), 'days': {}}, 'application/json', 'no-store'

    client = get_client()
    if not client:
        return 503, {'error': 'not_connected', 'days': {}}, 'application/json', 'no-store'

    try:
        start_utc, end_utc = month_window(year, month)
        def query_factory():
            return (
                client.table('matches')
                .select('*')
                .gte('utc_date', start_utc)
                .lt('utc_date', end_utc)
                .order('utc_date')
            )

        rows = _fetch_query_pages(
            query_factory,
            row_filter=(lambda row: _row_has_team(row, team_id)) if team_id else _row_belongs_to_default_calendar,
            page_size=250,
            max_rows=2000,
        )

        days = {}
        for row in rows:
            utc_date = row.get('utc_date')
            if not utc_date:
                continue
            try:
                local_dt = datetime.fromisoformat(utc_date.replace('Z', '+00:00')).astimezone(BR_TZ)
            except ValueError:
                continue
            if local_dt.year != year or local_dt.month != month:
                continue
            days.setdefault(local_dt.strftime('%Y-%m-%d'), []).append(calendar_match(row))
        return 200, {'year': year, 'month': month, 'days': days}, 'application/json', 'public, max-age=900'
    except Exception as error:
        print(f'[api_calendar_monthly] unexpected error: {type(error).__name__}', file=sys.stderr)
        return 500, {'error': 'internal_error', 'days': {}}, 'application/json', 'no-store'


def api_calendar(params):
    """Return an iCalendar feed."""
    try:
        competition = optional_competition_param(params)
        team_id = None
        if get_first(params, 'team_id', None):
            team_id = int_param(params, 'team_id', TEAM_ID, min_value=1, max_value=999999)
        team_tla = str(get_first(params, 'team_tla', '') or '').strip().upper()
        if team_tla and (not team_tla.isalpha() or len(team_tla) > 4):
            raise RequestValidationError('invalid team_tla')
        from_date = get_first(params, 'from_date', None)
        from_date, date_error = validate_date(from_date)
        if date_error:
            raise RequestValidationError(date_error)
        to_date = get_first(params, 'to_date', None)
        to_date, date_error = validate_date(to_date, 'to_date')
        if date_error:
            raise RequestValidationError(date_error)
    except RequestValidationError as error:
        return 400, str(error), 'text/plain; charset=utf-8', 'no-store'

    client = get_client()
    if not client:
        return 503, 'Calendar unavailable', 'text/plain; charset=utf-8', 'no-store'

    try:
        def query_factory():
            query = client.table('matches').select('*')
            if from_date:
                query = query.gte('utc_date', from_date)
            if to_date:
                query = query.lt('utc_date', _exclusive_end_date(to_date))
            return query.order('utc_date')

        def row_matches(row):
            if competition and _row_competition_code(row) != competition:
                return False
            if team_id and not _row_has_team(row, team_id):
                return False
            if team_tla and not _row_has_team_tla(row, team_tla):
                return False
            if not competition and not team_id and not team_tla:
                return _row_belongs_to_default_calendar(row)
            return True

        rows = _fetch_query_pages(
            query_factory,
            row_filter=row_matches,
            page_size=500,
            max_rows=5000,
        )
        return 200, render_calendar(rows), 'text/calendar; charset=utf-8', 'public, max-age=900'
    except Exception as error:
        print(f'[api_calendar] unexpected error: {type(error).__name__}', file=sys.stderr)
        return 500, 'Calendar unavailable', 'text/plain; charset=utf-8', 'no-store'


def api_health(params):
    """Health check endpoint for local development."""
    start = datetime.now(timezone.utc)
    client = get_client()
    status = 'disconnected'
    latency_ms = 0
    http_status = 503
    freshness = {'status': 'unknown', 'tables': {}}

    if client:
        try:
            client.table('matches').select('id').limit(1).execute()
            freshness = _data_freshness()
            latency_ms = round((datetime.now(timezone.utc) - start).total_seconds() * 1000)
            status = 'connected'
            http_status = 200
        except Exception as error:
            print(f'[api_health] unexpected error: {type(error).__name__}', file=sys.stderr)
            status = 'error'

    health_status = 'ok' if status == 'connected' and freshness.get('status') == 'fresh' else 'degraded'
    return http_status, {
        'status': health_status,
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'services': {
            'supabase': {'status': status, 'latency_ms': latency_ms},
            'data_freshness': freshness,
        },
        'version': APP_VERSION,
    }, 'application/json', 'no-store'


API_ROUTES = {
    '/api/matches': api_matches,
    '/api/v1/matches': api_matches,
    '/api/standings': api_standings,
    '/api/v1/standings': api_standings,
    '/api/competitions': api_competitions,
    '/api/v1/competitions': api_competitions,
    '/api/news': api_news,
    '/api/v1/news': api_news,
    '/api/calendar.ics': api_calendar,
    '/api/calendar': api_calendar,
    '/api/v1/calendar.ics': api_calendar,
    '/api/v1/calendar': api_calendar,
    '/api/calendar_monthly': api_calendar_monthly,
    '/api/v1/calendar_monthly': api_calendar_monthly,
    '/api/health': api_health,
    '/api/v1/health': api_health,
}


class Handler(SimpleHTTPRequestHandler):
    """Static + API request handler for local development."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DIRECTORY), **kwargs)

    def _send_security_headers(self):
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header(
            'Content-Security-Policy',
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com data:; "
            "img-src 'self' https: data:; "
            "connect-src 'self' https://*.supabase.co; "
            "base-uri 'self'; frame-ancestors 'none'; form-action 'self'",
        )
        self.send_header('Referrer-Policy', 'strict-origin-when-cross-origin')
        self.send_header('Permissions-Policy', 'camera=(), microphone=(), geolocation=(), interest-cohort=()')

    def end_headers(self):
        self._send_security_headers()
        super().end_headers()

    def do_OPTIONS(self):
        """Handle CORS preflight requests."""
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.send_header('Content-Length', '0')
        self.end_headers()

    def _apply_static_alias(self, path):
        if path == '/':
            self.path = '/index.html'
        elif path == '/support':
            self.path = '/support.html'
        elif path == '/privacy':
            self.path = '/privacy.html'

    def _send_api_result(self, result, include_body=True):
        status, data, content_type, cache_control = (*result, 'application/json', 'public, max-age=300')[:4]
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Cache-Control', cache_control)
        origin = self.headers.get('Origin', '')
        if origin in ALLOWED_ORIGINS:
            self.send_header('Access-Control-Allow-Origin', origin)
        self.end_headers()
        if not include_body:
            return
        if isinstance(data, (dict, list)):
            body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        elif isinstance(data, bytes):
            body = data
        else:
            body = str(data).encode('utf-8')
        self._write_body(body)

    def do_HEAD(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if any(part.startswith('.') for part in Path(path).parts):
            self.send_error(404)
            return

        for route, handler in API_ROUTES.items():
            if path == route:
                self._send_api_result(handler(parse_qs(parsed.query)), include_body=False)
                return

        self._apply_static_alias(path)
        if path == '/sw.js':
            self.send_response(200)
            self.send_header('Content-Type', 'application/javascript')
            self.send_header('Service-Worker-Allowed', '/')
            self.send_header('Cache-Control', 'no-cache')
            self.end_headers()
            return
        return super().do_HEAD()

    def _write_body(self, body):
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            return

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if any(part.startswith('.') for part in Path(path).parts):
            self.send_error(404)
            return

        for route, handler in API_ROUTES.items():
            if path == route:
                params = parse_qs(parsed.query)
                self._send_api_result(handler(params))
                return

        self._apply_static_alias(path)

        # Service worker must be served with correct MIME type
        if path == '/sw.js':
            self.send_response(200)
            self.send_header('Content-Type', 'application/javascript')
            self.send_header('Service-Worker-Allowed', '/')
            self.send_header('Cache-Control', 'no-cache')
            self.end_headers()
            sw_path = DIRECTORY / 'sw.js'
            self._write_body(sw_path.read_bytes())
            return

        return super().do_GET()

    def log_message(self, fmt, *args):
        sys.stderr.write(f'[{self.log_date_time_string()}] {fmt % args}\n')


class PalmeirasHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True


if __name__ == '__main__':
    try:
        from supabase import create_client  # noqa: F401
    except ImportError:
        print("ERROR: 'supabase' package not installed.", file=sys.stderr)
        print(f'  Python: {sys.executable} ({sys.version.split()[0]})', file=sys.stderr)
        print('  Fix: /opt/homebrew/bin/python3 apps/web/server.py', file=sys.stderr)
        sys.exit(1)

    if not SUPABASE_URL or not (is_public_supabase_key(SUPABASE_KEY) or (ALLOW_SERVICE_ROLE_PUBLIC_API and SUPABASE_KEY)):
        print('ERROR: SUPABASE_URL and a Supabase anon/publishable key must be set in .env', file=sys.stderr)
        print('       Do not use SUPABASE_KEY/service_role for the public API server.', file=sys.stderr)
        print('       Temporary migration fallback: ALLOW_SERVICE_ROLE_PUBLIC_API=1.', file=sys.stderr)
        sys.exit(1)

    print(f'Palmeiras Agenda running at http://{HOST}:{PORT}')
    server = PalmeirasHTTPServer((HOST, PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nShutting down...')
        server.server_close()
