"""
GET /api/matches

Query params:
  status    — FINISHED, SCHEDULED, TIMED, IN_PLAY (comma-separated)
  limit     — max results (default 50)
  from_date — YYYY-MM-DD filter
"""
import json
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

from db import get_supabase, parse_json


def _transform(m):
    return {
        'id': m.get('external_id'),
        'utcDate': m.get('utc_date'),
        'status': m.get('status'),
        'matchday': m.get('matchday'),
        'venue': m.get('venue'),
        'homeTeam': parse_json(m.get('home_team', '{}')),
        'awayTeam': parse_json(m.get('away_team', '{}')),
        'competition': parse_json(m.get('competition', '{}')),
        'score': {
            'fullTime': {
                'home': m.get('home_score'),
                'away': m.get('away_score'),
            }
        },
    }


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        params = parse_qs(urlparse(self.path).query)
        status = params.get('status', [None])[0]
        limit = int(params.get('limit', ['50'])[0])
        from_date = params.get('from_date', [None])[0]

        client = get_supabase()
        if not client:
            self._respond(503, {'matches': [], 'error': 'not_connected'})
            return

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

            fetch_limit = max(limit * 3, 50)
            result = query.order('utc_date').limit(fetch_limit).execute()
            matches = result.data

            has_finished = any(m.get('status') == 'FINISHED' for m in matches)
            if has_finished:
                matches.sort(key=lambda x: x.get('utc_date', ''), reverse=True)

            matches = matches[:limit]
            self._respond(200, {'matches': [_transform(m) for m in matches]})

        except Exception as e:
            self._respond(500, {'matches': [], 'error': str(e)})

    def _respond(self, status, data):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
