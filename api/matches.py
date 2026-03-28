"""
GET /api/matches?status=FINISHED&limit=50
Uses direct Supabase REST API — no supabase Python library needed.
"""
import json
import os
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError

SUPABASE_URL = os.environ.get('SUPABASE_URL', '')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY', '')


def supabase_get(table, **params):
    """Direct Supabase REST API GET — no SQLite dependency."""
    headers = {
        'apikey': SUPABASE_KEY,
        'Authorization': f'Bearer {SUPABASE_KEY}',
    }
    qs = urlencode(params)
    url = f'{SUPABASE_URL}/rest/v1/{table}?{qs}'
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


def transform(m):
    return {
        'id': m.get('external_id'),
        'utcDate': m.get('utc_date'),
        'status': m.get('status'),
        'matchday': m.get('matchday'),
        'stage': m.get('stage'),
        'venue': m.get('venue'),
        'broadcast': m.get('broadcast'),
        'homeTeam': parse_json(m.get('home_team', '{}')),
        'awayTeam': parse_json(m.get('away_team', '{}')),
        'competition': parse_json(m.get('competition', '{}')),
        'season': parse_json(m.get('season', '{}')),
        'referees': parse_json(m.get('referees', '[]')),
        'score': {
            'fullTime': {'home': m.get('home_score'), 'away': m.get('away_score')},
            'halfTime': {'home': m.get('half_time_home'), 'away': m.get('half_time_away')},
        },
        'homeScore': m.get('home_score'),
        'awayScore': m.get('away_score'),
    }


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        params = parse_qs(urlparse(self.path).query)
        status = params.get('status', [None])[0]
        limit = int(params.get('limit', ['50'])[0])
        from_date = params.get('from_date', [None])[0]

        if not SUPABASE_URL or not SUPABASE_KEY:
            return self._respond(503, {'matches': [], 'error': 'not_configured'})

        try:
            query_params = {'select': '*', 'order': 'utc_date.asc', 'limit': str(max(limit * 3, 50))}

            if status:
                statuses = [s.strip().upper() for s in status.split(',')]
                if len(statuses) == 1:
                    query_params['status'] = f'eq.{statuses[0]}'
                else:
                    vals = ','.join(statuses)
                    query_params['status'] = f'in.({vals})'
                if any(s in ('SCHEDULED', 'TIMED', 'IN_PLAY') for s in statuses) and not from_date:
                    from_date = datetime.now(timezone.utc).strftime('%Y-%m-%d')

            if from_date:
                query_params['utc_date'] = f'gte.{from_date}'

            matches = supabase_get('matches', **query_params)

            if any(m.get('status') == 'FINISHED' for m in matches):
                matches.sort(key=lambda x: x.get('utc_date', ''), reverse=True)
            matches = matches[:limit]
            self._respond(200, {'matches': [transform(m) for m in matches]})
        except HTTPError as e:
            self._respond(e.code, {'matches': [], 'error': f'supabase_{e.code}'})
        except Exception as e:
            self._respond(500, {'matches': [], 'error': str(e)})

    def _respond(self, status, data):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
