"""
GET /api/calendar.ics

Returns iCal feed for all Palmeiras matches.
"""
import json
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler

from db import get_supabase, parse_json

BR_TZ = timezone(timedelta(hours=-3))


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        client = get_supabase()
        if not client:
            self._respond(503, 'No database')
            return

        try:
            result = client.table('matches').select('*').execute()
            matches = sorted(result.data, key=lambda x: x.get('utc_date', ''), reverse=True)[:100]

            lines = [
                "BEGIN:VCALENDAR",
                "VERSION:2.0",
                "PRODID:-//Palmeiras//Dashboard//EN",
                "X-WR-CALNAME:Palmeiras - Jogos",
                "X-WR-TIMEZONE:America/Sao_Paulo",
                "CALSCALE:GREGORIAN",
                "METHOD:PUBLISH",
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
                    home_name = home.get('name', 'Home')
                    away_name = away.get('name', 'Away')

                    status = m.get('status', '')
                    summary = f"{home_name} x {away_name}"
                    if status == 'FINISHED':
                        hg = m.get('home_score', '-')
                        ag = m.get('away_score', '-')
                        summary = f"{home_name} {hg} x {ag} {away_name}"

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
