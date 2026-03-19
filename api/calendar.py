"""
GET /api/calendar.ics — iCal feed for Palmeiras matches
"""
import json
import os
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler

SUPABASE_URL = os.environ.get('SUPABASE_URL', '')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY', '')
BR_TZ = timezone(timedelta(hours=-3))


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


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        client = get_supabase()
        if not client:
            return self._respond(503, 'No database')

        try:
            result = client.table('matches').select('*').execute()
            matches = sorted(result.data, key=lambda x: x.get('utc_date', ''), reverse=True)[:100]

            lines = [
                "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Palmeiras//Dashboard//EN",
                "X-WR-CALNAME:Palmeiras - Jogos", "X-WR-TIMEZONE:America/Sao_Paulo",
                "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
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
                    hn = home.get('name', 'Home')
                    an = away.get('name', 'Away')
                    status = m.get('status', '')
                    summary = f"{hn} x {an}"
                    if status == 'FINISHED':
                        summary = f"{hn} {m.get('home_score', '-')} x {m.get('away_score', '-')} {an}"
                    lines.extend([
                        "BEGIN:VEVENT",
                        f"UID:palmeiras-{m.get('external_id', '')}@dashboard",
                        f"DTSTAMP:{now}",
                        f"DTSTART;TZID=America/Sao_Paulo:{start}",
                        f"DTEND;TZID=America/Sao_Paulo:{end}",
                        f"SUMMARY:{summary}",
                        "END:VEVENT",
                    ])
                except Exception:
                    continue

            lines.append("END:VCALENDAR")
            self.send_response(200)
            self.send_header('Content-Type', 'text/calendar')
            self.send_header('Cache-Control', 'public, max-age=3600')
            self.end_headers()
            self.wfile.write('\r\n'.join(lines).encode())
        except Exception as e:
            self._respond(500, f'Error: {e}')

    def _respond(self, status, text):
        self.send_response(status)
        self.send_header('Content-Type', 'text/plain')
        self.end_headers()
        self.wfile.write(str(text).encode())
