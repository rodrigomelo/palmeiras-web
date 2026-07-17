"""GET /api/competitions?year=YYYY — Palmeiras competition summaries."""
import sys
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse

try:
    from api._shared import (
        BR_TZ,
        RequestValidationError,
        TEAM_ID,
        int_param,
        is_configured,
        json_response,
        normalize_competition_code,
        parse_json,
        supabase_get,
        supabase_get_filtered,
        transform_match,
        transform_standing,
        upstream_status,
        cors_options_response,
    )
except ImportError:
    from _shared import (  # type: ignore
        BR_TZ,
        RequestValidationError,
        TEAM_ID,
        int_param,
        is_configured,
        json_response,
        normalize_competition_code,
        parse_json,
        supabase_get,
        supabase_get_filtered,
        transform_match,
        transform_standing,
        upstream_status,
        cors_options_response,
    )


def _safe_error(code='upstream_error'):
    return {'competitions': [], 'error': code}


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
            year = int_param(params, 'year', datetime.now(BR_TZ).year, min_value=2020, max_value=2035)
            team_id = int_param(params, 'team_id', TEAM_ID, min_value=1, max_value=999999)
        except RequestValidationError as error:
            return json_response(self, 400, _safe_error(str(error)), cache_control='no-store')

        if not is_configured():
            return json_response(self, 503, _safe_error('not_configured'), cache_control='no-store')

        try:
            start_utc, end_utc = _year_window(year)
            rows = supabase_get_filtered(
                'matches',
                filters=[('utc_date', f'gte.{start_utc}'), ('utc_date', f'lt.{end_utc}')],
                row_filter=lambda row: _row_has_team(row, team_id),
                select='*',
                order='utc_date.asc',
                page_size=500,
                max_rows=5000,
            )
            matches = [transform_match(row) for row in rows]

            standings_by_comp = {}
            try:
                standings_rows = supabase_get('standings', select='*', order='competition.asc,position.asc', limit='400')
                for row in standings_rows:
                    standing = transform_standing(row)
                    if standing.get('teamId') == team_id:
                        standings_by_comp[normalize_competition_code(row.get('competition'))] = standing
            except Exception as error:
                print(f'[api.competitions] standings summary warning: {type(error).__name__}', file=sys.stderr)

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
            return json_response(self, 200, {'year': year, 'teamId': team_id, 'competitions': competitions})
        except HTTPError as error:
            print(f'[api.competitions] Supabase HTTP {error.code}', file=sys.stderr)
            return json_response(self, upstream_status(error), _safe_error(f'supabase_{error.code}'), cache_control='no-store')
        except Exception as error:
            print(f'[api.competitions] unexpected error: {type(error).__name__}', file=sys.stderr)
            return json_response(self, 500, _safe_error('internal_error'), cache_control='no-store')
