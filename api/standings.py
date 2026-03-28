"""
GET /api/standings?competition=BSA
Uses direct Supabase REST API.
"""
import json
import os
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError

SUPABASE_URL = os.environ.get('SUPABASE_URL', '')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY', '')


def supabase_get(table, **params):
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


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        params = parse_qs(urlparse(self.path).query)

        if not SUPABASE_URL or not SUPABASE_KEY:
            return self._respond(503, {'standings': [], 'error': 'not_configured'})

        try:
            rows = supabase_get('standings', select='*', order='position.asc')
            standings = []
            for r in rows:
                team = parse_json(r.get('team', '{}'))
                standings.append({
                    'position': r.get('position'),
                    'teamId': team.get('id'),
                    'teamName': team.get('name', ''),
                    'teamShort': team.get('shortName', ''),
                    'teamTla': team.get('tla', ''),
                    'crest': team.get('crest', ''),
                    'playedGames': r.get('played_games'),
                    'won': r.get('won'),
                    'draw': r.get('draw'),
                    'lost': r.get('lost'),
                    'points': r.get('points'),
                    'goalsFor': r.get('goals_for'),
                    'goalsAgainst': r.get('goals_against'),
                    'goalDifference': r.get('goal_difference'),
                })
            self._respond(200, {'standings': standings})
        except HTTPError as e:
            self._respond(e.code, {'standings': [], 'error': f'supabase_{e.code}'})
        except Exception as e:
            self._respond(500, {'standings': [], 'error': str(e)})

    def _respond(self, status, data):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
