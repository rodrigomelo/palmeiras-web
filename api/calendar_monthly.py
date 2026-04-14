"""
GET /api/calendar_monthly?year=YYYY&month=MM — Monthly calendar data

Returns all Palmeiras matches for a given month, grouped by day.
Used by the Visual Calendar frontend component.
"""
import json
import os
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlencode
from urllib.request import Request, urlopen

SUPABASE_URL = os.environ.get('SUPABASE_URL', '')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY', '')
BR_TZ = timezone(timedelta(hours=-3))
TEAM_ID = 1769

COMP_CODES = {'BSA', 'CLI', 'LIBERTADORES', 'COPA', 'COPA_DO_BRASIL'}


def supabase_get(table, **params):
    headers = {
        'apikey': SUPABASE_KEY,
        'Authorization': f'Bearer {SUPABASE_KEY}',
    }
    qs = urlencode(params, doseq=True)
    url = f'{SUPABASE_URL}/rest/v1/{table}?{qs}'
    req = Request(url, headers=headers)
    with urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def supabase_get_filtered(table, filters, **params):
    """GET with Supabase filter operators (e.g. gte.col=value, lt.col=value).
    filters: list of (key, value) tuples to support duplicate column names.
    """
    headers = {
        'apikey': SUPABASE_KEY,
        'Authorization': f'Bearer {SUPABASE_KEY}',
    }
    qs_parts = []
    for k, v in filters:
        qs_parts.append(urlencode({k: v}))
    if params:
        qs_parts.append(urlencode(params))
    url = f'{SUPABASE_URL}/rest/v1/{table}?{"&".join(qs_parts)}'
    req = Request(url, headers=headers)
    with urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def parse_json(val):
    if isinstance(val, str):
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return {}
    return val if isinstance(val, dict) else {}


def make_match_dict(m):
    """Extract flat match dict for frontend consumption."""
    home = parse_json(m.get('home_team', '{}'))
    away = parse_json(m.get('away_team', '{}'))
    comp = parse_json(m.get('competition', '{}'))

    return {
        'utcDate': m.get('utc_date', ''),
        'status': m.get('status', 'SCHEDULED'),
        'competition': {
            'code': comp.get('code', 'OTHER'),
            'name': comp.get('name', 'Outros'),
        },
        'homeTeam': {
            'id': home.get('id'),
            'name': home.get('name', 'Home'),
            'shortName': home.get('shortName', ''),
            'crest': home.get('crest', ''),
        },
        'awayTeam': {
            'id': away.get('id'),
            'name': away.get('name', 'Away'),
            'shortName': away.get('shortName', ''),
            'crest': away.get('crest', ''),
        },
        'matchday': m.get('matchday'),
        'venue': m.get('venue', ''),
        'broadcast': m.get('broadcast', ''),
        'homeScore': m.get('home_score'),
        'awayScore': m.get('away_score'),
    }


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if not SUPABASE_URL or not SUPABASE_KEY:
            return self._respond(503, {'error': 'No database'})

        # Parse year/month from query string
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        year_str = qs.get('year', [''])[0]
        month_str = qs.get('month', [''])[0]

        if not year_str or not month_str:
            return self._respond(400, {'error': 'year and month required'})

        try:
            year = int(year_str)
            month = int(month_str)
        except ValueError:
            return self._respond(400, {'error': 'Invalid year/month'})

        if not (1 <= month <= 12):
            return self._respond(400, {'error': 'Month must be 1-12'})

        try:
            # Fetch all matches for this month (spanning 2 months for timezone edge cases)
            # BR timezone: match at 23:59 on last day of month still counts
            start_dt = datetime(year, month, 1, 0, 0, 0, tzinfo=BR_TZ)
            if month == 12:
                end_dt = datetime(year + 1, 1, 1, 0, 0, 0, tzinfo=BR_TZ)
            else:
                end_dt = datetime(year, month + 1, 1, 0, 0, 0, tzinfo=BR_TZ)

            start_utc = start_dt.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')
            end_utc = end_dt.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')

            matches = supabase_get_filtered(
                'matches',
                filters=[
                    ('utc_date', f'gte.{start_utc}'),
                    ('utc_date', f'lt.{end_utc}'),
                ],
                select='*',
                order='utc_date.asc',
                limit='50',
            )

            # Filter to current month in BR timezone, key by YYYY-MM-DD
            days = {}
            for m in matches:
                utc_date = m.get('utc_date', '')
                if not utc_date:
                    continue
                try:
                    dt = datetime.fromisoformat(utc_date.replace('Z', '+00:00'))
                    dt_sp = dt.astimezone(BR_TZ)
                    if dt_sp.year != year or dt_sp.month != month:
                        continue
                    day_key = dt_sp.strftime('%Y-%m-%d')  # e.g. '2026-04-16'
                    match_dict = make_match_dict(m)
                    # Attach raw score fields for past-game display
                    match_dict['utcDate'] = utc_date
                    match_dict['status'] = m.get('status', 'SCHEDULED')
                    match_dict['score'] = {
                        'fullTime': {
                            'home': m.get('home_score'),
                            'away': m.get('away_score'),
                        }
                    }
                    if day_key not in days:
                        days[day_key] = []
                    days[day_key].append(match_dict)
                except Exception:
                    continue

            self._respond_json(200, {
                'year': year,
                'month': month,
                'days': days,
            })

        except Exception as e:
            self._respond_json(500, {'error': str(e)})

    def _respond(self, status, data):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Cache-Control', 'public, max-age=3600')
        self.end_headers()
        if isinstance(data, str):
            self.wfile.write(data.encode())
        else:
            self.wfile.write(json.dumps(data).encode())

    def _respond_json(self, status, obj):
        self._respond(status, obj)
