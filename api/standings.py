"""
GET /api/standings?competition=BSA
"""
import json
import os
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


def transform(row):
    team = parse_json(row.get('team', '{}'))
    return {
        'position': row.get('position'),
        'teamName': team.get('name', ''),
        'teamShort': team.get('shortName', team.get('name', '')),
        'crest': team.get('crest', ''),
        'playedGames': row.get('played_games'),
        'won': row.get('won'),
        'draw': row.get('drawn'),
        'lost': row.get('lost'),
        'goalsFor': row.get('goals_for'),
        'goalsAgainst': row.get('goals_against'),
        'goalDifference': row.get('goal_difference'),
        'points': row.get('points'),
        'teamId': team.get('id'),
    }


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        params = parse_qs(urlparse(self.path).query)
        competition = params.get('competition', ['BSA'])[0]

        client = get_supabase()
        if not client:
            return self._respond(503, {'standings': [], 'error': 'not_connected'})

        try:
            result = client.table('standings').select('*').eq('competition', competition).order('position').execute()
            standings = [transform(r) for r in result.data]
            self._respond(200, {'standings': standings})
        except Exception as e:
            self._respond(500, {'standings': [], 'error': str(e)})

    def _respond(self, status, data):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
