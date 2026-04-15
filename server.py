"""
Palmeiras Web - Local Development Server (port 5001)

Direct Supabase access — same API contracts as Vercel serverless functions.
No proxy, no dependency on Vercel being deployed.

Usage:
    python server.py
    open http://localhost:5001
"""
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from http.server import HTTPServer, SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

# Load .env
env_path = Path(__file__).parent / '.env'
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if '=' in line and not line.startswith('#'):
                key, val = line.split('=', 1)
                os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))

SUPABASE_URL = os.environ.get('SUPABASE_URL', '')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY', '')
TEAM_ID = 1769
PORT = 5001
DIRECTORY = Path(__file__).parent

# --- Supabase ---
_client = None


def get_client():
    global _client
    if _client is not None:
        return _client
    try:
        from supabase import create_client
        _client = create_client(SUPABASE_URL, SUPABASE_KEY)
        return _client
    except Exception as e:
        print(f"[supabase] connection failed: {e}", file=sys.stderr)
        return None


def parse_json(val):
    if isinstance(val, str):
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return {}
    return val if isinstance(val, (dict, list)) else {}


# --- API Handlers ---

def api_matches(params):
    status = params.get('status', [None])[0]
    limit = min(int(params.get('limit', ['50'])[0]), 100)
    from_date = params.get('from_date', [None])[0]

    client = get_client()
    if not client:
        return 503, {'matches': [], 'error': 'not_connected'}

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

        transformed = []
        for m in matches:
            transformed.append({
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
            })
        return 200, {'matches': transformed}
    except Exception as e:
        print(f"[api_matches] error: {e}", file=sys.stderr)
        return 500, {'matches': [], 'error': 'Erro interno do servidor'}


def api_standings(params):
    competition = params.get('competition', ['BSA'])[0]

    client = get_client()
    if not client:
        return 503, {'standings': [], 'error': 'not_connected'}

    try:
        result = client.table('standings').select('*').eq('competition', competition).order('position').execute()
        transformed = []
        for s in result.data:
            team = parse_json(s.get('team', '{}'))
            transformed.append({
                'position': s.get('position'),
                'teamName': team.get('name', ''),
                'teamShort': team.get('shortName', team.get('name', '')),
                'crest': team.get('crest', ''),
                'playedGames': s.get('played_games'),
                'won': s.get('won'),
                'draw': s.get('drawn'),
                'lost': s.get('lost'),
                'goalsFor': s.get('goals_for'),
                'goalsAgainst': s.get('goals_against'),
                'goalDifference': s.get('goal_difference'),
                'points': s.get('points'),
                'teamId': team.get('id'),
            })
        return 200, {'standings': transformed}
    except Exception as e:
        print(f"[api_standings] error: {e}", file=sys.stderr)
        return 500, {'standings': [], 'error': 'Erro interno do servidor'}


def api_news(params):
    limit = min(int(params.get('limit', ['10'])[0]), 100)

    client = get_client()
    if not client:
        return 503, {'news': [], 'error': 'not_connected'}

    try:
        result = client.table('news').select('*').order('collected_at', desc=True).limit(limit).execute()
        return 200, {'news': result.data}
    except Exception as e:
        print(f"[api_news] error: {e}", file=sys.stderr)
        return 500, {'news': [], 'error': 'Erro interno do servidor'}


def api_calendar_monthly(params):
    """Monthly calendar — returns matches grouped by day."""
    year_str = params.get('year', [None])[0]
    month_str = params.get('month', [None])[0]

    if not year_str or not month_str:
        return 400, {'error': 'year and month required'}

    try:
        year = int(year_str)
        month = int(month_str)
    except ValueError:
        return 400, {'error': 'Invalid year/month'}

    if not (1 <= month <= 12):
        return 400, {'error': 'Month must be 1-12'}

    client = get_client()
    if not client:
        return 503, {'error': 'not_connected'}

    try:
        BR_TZ = timezone(timedelta(hours=-3))
        start_dt = datetime(year, month, 1, 0, 0, 0, tzinfo=BR_TZ)
        if month == 12:
            end_dt = datetime(year + 1, 1, 1, 0, 0, 0, tzinfo=BR_TZ)
        else:
            end_dt = datetime(year, month + 1, 1, 0, 0, 0, tzinfo=BR_TZ)

        start_utc = start_dt.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')
        end_utc = end_dt.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')

        # Use raw URL with gte/lt filters via Supabase REST directly
        import urllib.request
        import urllib.parse
        # WARNING: Using service role key as Bearer — this bypasses RLS.
        # TODO: Implement proper RLS policies and use anon key + user JWT instead.
        headers = {
            'apikey': SUPABASE_KEY,
            'Authorization': f'Bearer {SUPABASE_KEY}',
        }
        qs = f"utc_date=gte.{urllib.parse.quote(start_utc)}&utc_date=lt.{urllib.parse.quote(end_utc)}&order=utc_date.asc&limit=50"
        url = f"{SUPABASE_URL}/rest/v1/matches?{qs}"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw_matches = json.loads(resp.read())

        days = {}
        for m in raw_matches:
            utc_date = m.get('utc_date', '')
            if not utc_date:
                continue
            try:
                dt = datetime.fromisoformat(utc_date.replace('Z', '+00:00'))
                dt_sp = dt.astimezone(BR_TZ)
                if dt_sp.year != year or dt_sp.month != month:
                    continue
                day = dt_sp.day

                home = parse_json(m.get('home_team', '{}'))
                away = parse_json(m.get('away_team', '{}'))
                comp = parse_json(m.get('competition', '{}'))

                match_dict = {
                    'utcDate': utc_date,
                    'status': m.get('status', 'SCHEDULED'),
                    'competition': {'code': comp.get('code', 'OTHER'), 'name': comp.get('name', 'Outros')},
                    'homeTeam': {'id': home.get('id'), 'name': home.get('name', 'Home'),
                                 'shortName': home.get('shortName', ''), 'crest': home.get('crest', '')},
                    'awayTeam': {'id': away.get('id'), 'name': away.get('name', 'Away'),
                                 'shortName': away.get('shortName', ''), 'crest': away.get('crest', '')},
                    'matchday': m.get('matchday'),
                    'venue': m.get('venue', ''),
                    'broadcast': m.get('broadcast', ''),
                    'homeScore': m.get('home_score'),
                    'awayScore': m.get('away_score'),
                }

                if day not in days:
                    days[day] = []
                days[day].append(match_dict)
            except Exception:
                continue

        return 200, {'year': year, 'month': month, 'days': days}
    except Exception as e:
        print(f"[api_calendar_monthly] error: {e}", file=sys.stderr)
        return 500, {'error': 'Erro interno do servidor'}


def api_calendar(params):
    client = get_client()
    if not client:
        return 503, 'No database', 'text/plain'

    try:
        BR_TZ = timezone(timedelta(hours=-3))
        # NOTE: No request timeout on Supabase calls — sync client doesn't support it.
        # Consider switching to async client with httpx for timeout control.
        result = client.table('matches').select('*').limit(200).execute()
        matches = sorted(result.data, key=lambda x: x.get('utc_date', ''), reverse=True)[:150]

        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//Palmeiras//Agenda//EN",
            "X-WR-CALNAME:Palmeiras Agenda",
            "X-WR-TIMEZONE:America/Sao_Paulo",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH",
            "BEGIN:VTIMEZONE",
            "TZID:America/Sao_Paulo",
            "BEGIN:STANDARD",
            "DTSTART:19700101T000000",
            "TZOFFSETFROM:-0300",
            "TZOFFSETTO:-0300",
            "TZNAME:BRT",
            "END:STANDARD",
            "END:VTIMEZONE",
        ]
        now = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')

        for m in matches:
            utc_date = m.get('utc_date', '')
            if not utc_date:
                continue
            try:
                dt = datetime.fromisoformat(utc_date.replace('Z', '+00:00'))
                dt_sp = dt.astimezone(BR_TZ)
                start = dt_sp.strftime('%Y%m%dT%H%M%S')
                end = (dt_sp + timedelta(hours=2)).strftime('%Y%m%dT%H%M%S')

                home = parse_json(m.get('home_team', {}))
                away = parse_json(m.get('away_team', {}))
                comp = parse_json(m.get('competition', {}))
                hn = home.get('name', 'Home')
                an = away.get('name', 'Away')
                is_home = home.get('id') == TEAM_ID

                status = m.get('status', '')
                venue = m.get('venue', '')
                if not venue:
                    venue = 'Allianz Parque' if is_home else 'A definir'
                broadcast = m.get('broadcast', '')
                comp_name = comp.get('name', '')

                hg = m.get('home_score')
                ag = m.get('away_score')
                if status == 'FINISHED' and hg is not None and ag is not None:
                    summary = f"⚽ {hn} {hg} x {ag} {an}"
                else:
                    summary = f"⚽ {hn} x {an}"

                desc_parts = []
                if comp_name:
                    desc_parts.append(f"Competicao: {comp_name}")
                if venue:
                    desc_parts.append(f"Estadio: {venue}")
                if broadcast:
                    desc_parts.append(f"Transmissao: {broadcast}")

                description = '; '.join(desc_parts).replace('\n', ' ')
                location = venue if venue != 'A definir' else ''

                lines.extend([
                    "BEGIN:VEVENT",
                    f"UID:palmeiras-{m.get('external_id', '')}@agenda",
                    f"DTSTAMP:{now}",
                    f"DTSTART;TZID=America/Sao_Paulo:{start}",
                    f"DTEND;TZID=America/Sao_Paulo:{end}",
                    f"SUMMARY:{summary}",
                    f"DESCRIPTION:{description}",
                ])
                if location:
                    lines.append(f"LOCATION:{location}")
                lines.append("END:VEVENT")
            except Exception:
                continue

        lines.append("END:VCALENDAR")
        return 200, '\r\n'.join(lines), 'text/calendar; charset=utf-8'
    except Exception as e:
        print(f"[api_calendar] error: {e}", file=sys.stderr)
        return 500, 'Erro interno do servidor', 'text/plain'


def api_health(params):
    """Health check: verifies Supabase connectivity and returns system status."""
    import time
    start = time.time()
    client = get_client()
    latency_ms = round((time.time() - start) * 1000)

    health = {
        'status': 'ok',
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'services': {
            'supabase': {
                'status': 'unknown',
                'latency_ms': latency_ms,
            }
        },
        'version': '1.0.0',
    }

    if not client:
        health['status'] = 'degraded'
        health['services']['supabase']['status'] = 'disconnected'
        return 503, health

    try:
        # Simple query to verify connection
        client.table('matches').select('id').limit(1).execute()
        health['services']['supabase']['status'] = 'connected'
    except Exception as e:
        health['status'] = 'degraded'
        health['services']['supabase']['status'] = 'error'
        health['services']['supabase']['error'] = str(e)[:100]
        return 503, health

    return 200, health


# Route table: path prefix → handler function
API_ROUTES = {
    '/api/matches': api_matches,
    '/api/standings': api_standings,
    '/api/news': api_news,
    '/api/calendar.ics': api_calendar,
    '/api/calendar_monthly': api_calendar_monthly,
    '/api/health': api_health,
}


# --- HTTP Handler ---

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DIRECTORY), **kwargs)

    def _send_security_headers(self):
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Content-Security-Policy',
                         "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                         "img-src 'self' https: data:; style-src 'self' 'unsafe-inline'; "
                         "connect-src 'self' https://*.supabase.co")
        self.send_header('Referrer-Policy', 'strict-origin-when-cross-origin')

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        # API routes
        for route, handler in API_ROUTES.items():
            if path == route or path.startswith(route + '?'):
                params = parse_qs(parsed.query)
                result = handler(params)

                if len(result) == 3:
                    status, data, content_type = result
                else:
                    status, data = result
                    content_type = 'application/json'
                    data = json.dumps(data)

                self.send_response(status)
                self.send_header('Content-Type', content_type)
                # Restrict CORS to known origins
                origin = self.headers.get('Origin', '')
                allowed = ['http://localhost:5001', 'http://localhost:3000', 'https://palmeiras-web.vercel.app']
                if origin in allowed:
                    self.send_header('Access-Control-Allow-Origin', origin)
                self._send_security_headers()
                self.end_headers()
                if isinstance(data, str):
                    self.wfile.write(data.encode())
                else:
                    self.wfile.write(json.dumps(data).encode())
                return

        # Static files
        if self.path == '/':
            self.path = '/index.html'
        return super().do_GET()

    def log_message(self, format, *args):
        sys.stderr.write(f"[{self.log_date_time_string()}] {format % args}\n")


class PalmeirasHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True


if __name__ == '__main__':
    # Verify supabase is importable
    try:
        from supabase import create_client
    except ImportError:
        print("ERROR: 'supabase' package not installed.", file=sys.stderr)
        print(f"  Python: {sys.executable} ({sys.version.split()[0]})", file=sys.stderr)
        print(f"  Fix: /opt/homebrew/bin/python3 server.py", file=sys.stderr)
        sys.exit(1)

    if not SUPABASE_URL or not SUPABASE_KEY:
        print("ERROR: SUPABASE_URL and SUPABASE_KEY must be set in .env", file=sys.stderr)
        sys.exit(1)

    print(f"Palmeiras Agenda running at http://localhost:{PORT}")
    print(f"  Python: {sys.executable} ({sys.version.split()[0]})")
    print(f"  Supabase: {SUPABASE_URL[:40]}...")
    print(f"  API routes: {', '.join(API_ROUTES.keys())}")
    print(f"  Press Ctrl+C to stop")

    server = PalmeirasHTTPServer(('0.0.0.0', PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nStopped.')
