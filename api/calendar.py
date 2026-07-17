"""GET /api/calendar.ics — iCal feed for filtered football matches."""
import sys
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse

try:
    from api._shared import (
        BR_TZ,
        TEAM_ID,
        RequestValidationError,
        get_first,
        int_param,
        is_configured,
        normalize_competition_code,
        optional_competition_param,
        parse_json,
        supabase_get_filtered,
        text_response,
        upstream_status,
        validate_date,
        cors_options_response,
    )
except ImportError:
    from _shared import (  # type: ignore
        BR_TZ,
        TEAM_ID,
        RequestValidationError,
        get_first,
        int_param,
        is_configured,
        normalize_competition_code,
        optional_competition_param,
        parse_json,
        supabase_get_filtered,
        text_response,
        upstream_status,
        validate_date,
        cors_options_response,
    )

AWAY_STADIUMS = {
    1765: 'Maracanã',
    1766: 'Arena MRV',
    1767: 'Arena do Grêmio',
    1768: 'Ligga Arena',
    1770: 'Estádio Nilton Santos',
    1771: 'Mineirão',
    1772: 'Arena Condá',
    1776: 'MorumBIS',
    1777: 'Arena Fonte Nova',
    1779: 'Neo Química Arena',
    1780: 'São Januário',
    1782: 'Barradão',
    1783: 'Maracanã',
    4241: 'Couto Pereira',
    4286: 'Nabi Abi Chedid',
    4287: 'Baenão',
    4364: 'Maião',
    6684: 'Beira-Rio',
    6685: 'Vila Belmiro',
}


def fold_line(line):
    """Fold iCalendar lines to 75 octets-ish for client compatibility."""
    if not line:
        return ''
    result = []
    while len(line) > 75:
        result.append(line[:75])
        line = ' ' + line[75:]
    result.append(line)
    return '\r\n'.join(result)


def escape_ics(text):
    """Escape text for an iCalendar property value."""
    if not text:
        return ''
    return str(text).replace('\\', '\\\\').replace(';', '\\;').replace(',', '\\,').replace('\r', '').replace('\n', '\\n')


def _exclusive_end_date(value):
    if not value:
        return None
    return (datetime.strptime(value, '%Y-%m-%d').date() + timedelta(days=1)).isoformat()


def _row_competition_code(row):
    comp = parse_json(row.get('competition', '{}'))
    return normalize_competition_code(comp.get('code'))


def _row_has_team_id(row, team_id):
    home = parse_json(row.get('home_team', '{}'))
    away = parse_json(row.get('away_team', '{}'))
    return home.get('id') == team_id or away.get('id') == team_id


def _row_has_team_tla(row, team_tla):
    home = parse_json(row.get('home_team', '{}'))
    away = parse_json(row.get('away_team', '{}'))
    return str(home.get('tla', '')).upper() == team_tla or str(away.get('tla', '')).upper() == team_tla


def _row_is_world_cup(row):
    return _row_competition_code(row) == 'WC'


def calendar_filters_from_path(path):
    """Parse and validate optional iCalendar feed filters."""
    params = parse_qs(urlparse(path).query)
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

    return {
        'competition': competition,
        'team_id': team_id,
        'team_tla': team_tla,
        'from_date': from_date,
        'to_date': to_date,
    }


def filter_calendar_rows(rows, filters):
    """Apply JSON-field filters that Supabase REST cannot express portably."""
    return [row for row in rows if calendar_row_matches(row, filters)]


def calendar_row_matches(row, filters):
    """Return True when a row matches optional calendar JSON-field filters."""
    if filters.get('competition') and _row_competition_code(row) != filters['competition']:
        return False
    if filters.get('team_id') and not _row_has_team_id(row, filters['team_id']):
        return False
    if filters.get('team_tla') and not _row_has_team_tla(row, filters['team_tla']):
        return False
    if not filters.get('competition') and not filters.get('team_id') and not filters.get('team_tla'):
        return _row_has_team_id(row, TEAM_ID) or _row_is_world_cup(row)
    return True


def render_calendar(matches):
    """Render Supabase match rows as a complete VCALENDAR string."""
    lines = [
        'BEGIN:VCALENDAR',
        'VERSION:2.0',
        'PRODID:-//Palmeiras//Agenda//PT-BR',
        'X-WR-CALNAME:Palmeiras Agenda',
        'X-WR-TIMEZONE:America/Sao_Paulo',
        'CALSCALE:GREGORIAN',
        'METHOD:PUBLISH',
        'BEGIN:VTIMEZONE',
        'TZID:America/Sao_Paulo',
        'BEGIN:STANDARD',
        'DTSTART:19700101T000000',
        'TZOFFSETFROM:-0300',
        'TZOFFSETTO:-0300',
        'TZNAME:BRT',
        'END:STANDARD',
        'END:VTIMEZONE',
    ]
    now = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')

    for match in matches:
        utc_date = match.get('utc_date')
        if not utc_date:
            continue
        try:
            dt = datetime.fromisoformat(utc_date.replace('Z', '+00:00')).astimezone(BR_TZ)
        except ValueError:
            continue

        home = parse_json(match.get('home_team', '{}'))
        away = parse_json(match.get('away_team', '{}'))
        comp = parse_json(match.get('competition', '{}'))
        referees = parse_json(match.get('referees', '[]'), [])

        home_name = home.get('name') or home.get('shortName') or 'A definir'
        away_name = away.get('name') or away.get('shortName') or 'A definir'
        is_home = home.get('id') == TEAM_ID
        status = match.get('status', '')
        home_score = match.get('home_score')
        away_score = match.get('away_score')

        venue = match.get('venue') or ('Allianz Parque' if is_home else AWAY_STADIUMS.get(home.get('id'), 'A definir'))
        if status == 'FINISHED' and home_score is not None and away_score is not None:
            summary = f'⚽ {home_name} {home_score} x {away_score} {away_name}'
        else:
            summary = f'⚽ {home_name} x {away_name}'

        desc_parts = []
        if comp.get('name'):
            desc_parts.append(f"Competição: {comp['name']}")
        if match.get('matchday'):
            desc_parts.append(f"Rodada: {match['matchday']}")
        if match.get('stage') and match.get('stage') != 'REGULAR_SEASON':
            desc_parts.append(f"Fase: {match['stage']}")
        if venue:
            desc_parts.append(f'Estádio: {venue}')
        desc_parts.append(f"Transmissão: {match.get('broadcast') or 'A confirmar'}")
        if status == 'FINISHED' and home_score is not None and away_score is not None:
            desc_parts.append(f'Placar: {home_score} x {away_score}')
            if match.get('half_time_home') is not None and match.get('half_time_away') is not None:
                desc_parts.append(f"Placar 1º tempo: {match['half_time_home']} x {match['half_time_away']}")
        ref_names = [r.get('name', '') for r in referees if isinstance(r, dict) and r.get('name')]
        if ref_names:
            desc_parts.append(f"Árbitros: {', '.join(ref_names)}")

        start = dt.strftime('%Y%m%dT%H%M%S')
        end = (dt + timedelta(hours=2)).strftime('%Y%m%dT%H%M%S')
        description = escape_ics('\n'.join(desc_parts))
        lines.extend([
            'BEGIN:VEVENT',
            f"UID:palmeiras-{escape_ics(match.get('external_id') or utc_date)}@agenda",
            f'DTSTAMP:{now}',
            f'DTSTART;TZID=America/Sao_Paulo:{start}',
            f'DTEND;TZID=America/Sao_Paulo:{end}',
            fold_line(f'SUMMARY:{escape_ics(summary)}'),
            fold_line(f'DESCRIPTION:{description}'),
        ])
        if venue and venue != 'A definir':
            lines.append(f'LOCATION:{escape_ics(venue)}')
        if comp.get('name'):
            lines.append(f"CATEGORIES:{escape_ics(comp['name'])}")
        lines.append('END:VEVENT')

    lines.append('END:VCALENDAR')
    return '\r\n'.join(lines)


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
        if not is_configured():
            return text_response(self, 503, 'Calendar unavailable', cache_control='no-store')

        try:
            filters = calendar_filters_from_path(self.path)
            query_filters = []
            if filters.get('from_date'):
                query_filters.append(('utc_date', f"gte.{filters['from_date']}"))
            if filters.get('to_date'):
                query_filters.append(('utc_date', f"lt.{_exclusive_end_date(filters['to_date'])}"))

            matches = supabase_get_filtered(
                'matches',
                filters=query_filters,
                row_filter=lambda row: calendar_row_matches(row, filters),
                select='*',
                order='utc_date.asc',
                page_size=500,
                max_rows=5000,
            )
            body = render_calendar(matches)
            return text_response(self, 200, body, content_type='text/calendar; charset=utf-8', cache_control='public, max-age=900')
        except RequestValidationError as error:
            return text_response(self, 400, str(error), cache_control='no-store')
        except HTTPError as error:
            print(f'[api.calendar] Supabase HTTP {error.code}', file=sys.stderr)
            return text_response(self, upstream_status(error), 'Calendar unavailable', cache_control='no-store')
        except Exception as error:
            print(f'[api.calendar] unexpected error: {type(error).__name__}', file=sys.stderr)
            return text_response(self, 500, 'Calendar unavailable', cache_control='no-store')
