"""
GET /api/calendar.ics — iCal feed for Palmeiras matches

Includes: stadium, competition, matchday, stage, broadcast, scores.
"""
import json
import os
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler

SUPABASE_URL = os.environ.get('SUPABASE_URL', '')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY', '')
BR_TZ = timezone(timedelta(hours=-3))
TEAM_ID = 1769


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


def escape_ics(text):
    """Escape text for ICS format."""
    if not text:
        return ''
    return str(text).replace('\\', '\\\\').replace(';', '\\;').replace(',', '\\,').replace('\n', '\\n')


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        client = get_supabase()
        if not client:
            return self._respond(503, 'No database')

        try:
            result = client.table('matches').select('*').execute()
            matches = sorted(result.data, key=lambda x: x.get('utc_date', ''), reverse=True)[:150]

            lines = [
                "BEGIN:VCALENDAR",
                "VERSION:2.0",
                "PRODID:-//Palmeiras//Dashboard//EN",
                "X-WR-CALNAME:Palmeiras - Jogos",
                "X-WR-TIMEZONE:America/Sao_Paulo",
                "CALSCALE:GREGORIAN",
                "METHOD:PUBLISH",
                # Timezone definition
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
                    matchday = m.get('matchday', '')
                    stage = m.get('stage', '')
                    venue = m.get('venue', '') or ('Allianz Parque' if is_home else 'A definir')
                    broadcast = m.get('broadcast', '')
                    comp_name = comp.get('name', '')
                    comp_code = comp.get('code', '')

                    # Summary
                    if status == 'FINISHED':
                        hg = m.get('home_score', '-')
                        ag = m.get('away_score', '-')
                        ht_h = m.get('half_time_home')
                        ht_a = m.get('half_time_away')
                        summary = f"🏆 {hn} {hg} x {ag} {an}"
                    elif status == 'IN_PLAY':
                        hg = m.get('home_score', '?')
                        ag = m.get('away_score', '?')
                        summary = f"🔴 AO VIVO: {hn} {hg} x {ag} {an}"
                    else:
                        summary = f"⚽ {hn} x {an}"

                    # Description with all details
                    desc_parts = []
                    if comp_name:
                        desc_parts.append(f"Competicao: {comp_name}")
                    if matchday:
                        desc_parts.append(f"Rodada: {matchday}")
                    if stage and stage != 'REGULAR_SEASON':
                        desc_parts.append(f"Fase: {stage}")
                    if venue:
                        desc_parts.append(f"Estadio: {venue}")
                    if broadcast:
                        desc_parts.append(f"Transmissao: {broadcast}")
                    else:
                        desc_parts.append("Transmissao: A confirmar")
                    if status == 'FINISHED' and ht_h is not None:
                        desc_parts.append(f"Placar 1o tempo: {ht_h} x {ht_a}")

                    # Referees
                    referees = parse_json(m.get('referees', '[]'))
                    if referees and isinstance(referees, list):
                        ref_names = [r.get('name', '') for r in referees if r.get('name')]
                        if ref_names:
                            desc_parts.append(f"Arbitros: {', '.join(ref_names)}")

                    description = escape_ics('\\n'.join(desc_parts))

                    # Location
                    location = escape_ics(venue) if venue and venue != 'A definir' else ''

                    lines.extend([
                        "BEGIN:VEVENT",
                        f"UID:palmeiras-{m.get('external_id', '')}@dashboard",
                        f"DTSTAMP:{now}",
                        f"DTSTART;TZID=America/Sao_Paulo:{start}",
                        f"DTEND;TZID=America/Sao_Paulo:{end}",
                        f"SUMMARY:{escape_ics(summary)}",
                        f"DESCRIPTION:{description}",
                    ])
                    if location:
                        lines.append(f"LOCATION:{location}")
                    if comp_name:
                        lines.append(f"CATEGORIES:{escape_ics(comp_name)}")
                    lines.append("END:VEVENT")

                except Exception:
                    continue

            lines.append("END:VCALENDAR")

            self.send_response(200)
            self.send_header('Content-Type', 'text/calendar; charset=utf-8')
            self.send_header('Cache-Control', 'public, max-age=3600')
            self.end_headers()
            self.wfile.write('\r\n'.join(lines).encode('utf-8'))

        except Exception as e:
            self._respond(500, f'Error: {e}')

    def _respond(self, status, text):
        self.send_response(status)
        self.send_header('Content-Type', 'text/plain')
        self.end_headers()
        self.wfile.write(str(text).encode())
