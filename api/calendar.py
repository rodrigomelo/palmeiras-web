"""
GET /api/calendar.ics — iCal feed for Palmeiras matches

Includes: stadium, competition, matchday, stage, broadcast, scores.
Uses direct Supabase REST API — no supabase Python library needed.
"""
import json
import os
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError

SUPABASE_URL = os.environ.get('SUPABASE_URL', '')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY', '')
BR_TZ = timezone(timedelta(hours=-3))
TEAM_ID = 1769

AWAY_STADIUMS = {
    1776: 'Morumbi', 1777: 'Fonte Nova', 1770: 'Nilton Santos',
    1779: 'Maracanã', 1783: 'Beira-Rio', 1766: 'Mineirão',
    1780: 'Castelão', 1765: 'Arena MRV',
}


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


def fold_line(line):
    if not line:
        return ''
    result = []
    while len(line) > 75:
        result.append(line[:75])
        line = ' ' + line[75:]
    result.append(line)
    return '\r\n'.join(result)


def escape_ics(text):
    if not text:
        return ''
    return str(text).replace('\\', '\\\\').replace(';', '\\;').replace(',', '\\,').replace('\r', '')


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if not SUPABASE_URL or not SUPABASE_KEY:
            return self._respond(503, 'No database')

        try:
            matches = supabase_get('matches', select='*', order='utc_date.desc', limit='150')

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

                    home = parse_json(m.get('home_team', '{}'))
                    away = parse_json(m.get('away_team', '{}'))
                    comp = parse_json(m.get('competition', '{}'))
                    hn = home.get('name', 'Home')
                    an = away.get('name', 'Away')
                    is_home = home.get('id') == TEAM_ID

                    status = m.get('status', '')
                    matchday = m.get('matchday', '')
                    stage = m.get('stage', '')
                    venue = m.get('venue', '')
                    if not venue:
                        if is_home:
                            venue = 'Allianz Parque'
                        else:
                            venue = AWAY_STADIUMS.get(home.get('id'), 'A definir')
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
                    if status == 'FINISHED' and hg is not None and ag is not None:
                        desc_parts.append(f"Placar: {hg} x {ag}")
                        ht_h = m.get('half_time_home')
                        ht_a = m.get('half_time_away')
                        if ht_h is not None and ht_a is not None:
                            desc_parts.append(f"Placar 1o tempo: {ht_h} x {ht_a}")

                    referees = parse_json(m.get('referees', '[]'))
                    if referees and isinstance(referees, list):
                        ref_names = [r.get('name', '') for r in referees if r.get('name')]
                        if ref_names:
                            desc_parts.append(f"Arbitros: {', '.join(ref_names)}")

                    description = fold_line(escape_ics('\n'.join(desc_parts)))
                    location = escape_ics(venue) if venue and venue != 'A definir' else ''

                    lines.extend([
                        "BEGIN:VEVENT",
                        f"UID:palmeiras-{m.get('external_id', '')}@agenda",
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
            self.send_header('Cache-Control', 'public, max-age=900')
            self.end_headers()
            self.wfile.write('\r\n'.join(lines).encode('utf-8'))

        except Exception as e:
            self._respond(500, f'Error: {e}')

    def _respond(self, status, text):
        self.send_response(status)
        self.send_header('Content-Type', 'text/plain')
        self.end_headers()
        self.wfile.write(str(text).encode())
