"""
GET /api/matches?status=FINISHED&limit=50
"""
import json
import os
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

SUPABASE_URL = os.environ.get('SUPABASE_URL', '')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY', '')


def get_supabase():
    try:
        from supabase import create_client
        return create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception:
        return None


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

        client = get_supabase()
        if not client:
            return self._respond(503, {'matches': [], 'error': 'not_connected'})

        try:
            query = client.table('matches').select('*')
            if status:
                statuses = [s.strip().upper() for s in status.split(',')]
                if len(statuses) == 1:
                    query = query.eq('status', statuses[0])
                else:
                    query = query.in_('status', statuses)
                if any(s in ('SCHEDULED', 'TIMED', 'IN_PLAY') for s in statuses) and not from_date:
                    from_date = datetime.now(timezone.utc).strftime('%Y-%m-%d')
            if from_date:
                query = query.gte('utc_date', from_date)

            result = query.order('utc_date').limit(max(limit * 3, 50)).execute()
            matches = result.data
            if any(m.get('status') == 'FINISHED' for m in matches):
                matches.sort(key=lambda x: x.get('utc_date', ''), reverse=True)
            matches = matches[:limit]
            self._respond(200, {'matches': [transform(m) for m in matches]})
        except Exception as e:
            self._respond(500, {'matches': [], 'error': str(e)})

    def _respond(self, status, data):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
