"""
Palmeiras Web Dashboard - Flask Server for Vercel
"""
from flask import Flask, send_from_directory, Response
import requests

app = Flask(__name__, static_folder='.')

DATA_API = 'https://palmeiras-data.vercel.app'


@app.route('/')
def index():
    return send_from_directory('.', 'index.html')


@app.route('/favicon.png')
def favicon():
    return send_from_directory('.', 'favicon.png')


@app.route('/api/calendar.ics')
def calendar_ics():
    """Generate iCal feed for Palmeiras matches."""
    try:
        # Fetch all matches (past and future)
        resp = requests.get(f"{DATA_API}/api/matches?status=FINISHED,TIMED,SCHEDULED,IN_PLAY&limit=100", timeout=30)
        if resp.status_code != 200:
            return Response(f"Error fetching matches: {resp.status_code}", status=resp.status_code)
        
        data = resp.json()
        matches = data.get('matches', [])
        
        # Sort by date (newest first for past, then upcoming)
        matches.sort(key=lambda x: x.get('utcDate', ''), reverse=True)
        
        ics_lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//Palmeiras//Dashboard//EN",
            "X-WR-CALNAME:Palmeiras - Jogos",
            "X-WR-TIMEZONE:America/Sao_Paulo",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH",
        ]
        
        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')
        
        for m in matches:
            utc_date = m.get('utcDate', '')
            if not utc_date:
                continue
            
            try:
                dt = datetime.fromisoformat(utc_date.replace('Z', '+00:00'))
                # Convert to Sao Paulo time (GMT-3)
                sp_tz = timezone(timedelta(hours=-3))
                dt_sp = dt.astimezone(sp_tz)
                start = dt_sp.strftime('%Y%m%dT%H%M%S')
                # End time - games are 2 hours
                end_hour = (dt_sp.hour + 2) % 24
                end = dt_sp.replace(hour=end_hour).strftime('%Y%m%dT%H%M%S')
                
                home_team = m.get('homeTeam', {})
                away_team = m.get('awayTeam', {})
                
                home_name = home_team.get('name', 'Home') if isinstance(home_team, dict) else 'Home'
                away_name = away_team.get('name', 'Away') if isinstance(away_team, dict) else 'Away'
                
                match_id = m.get('id', '')
                status = m.get('status', '')
                
                # Include score for finished matches
                summary = f"🏆 {home_name} x {away_name}"
                if status == 'FINISHED':
                    score = m.get('score', {}).get('fullTime', {})
                    hg = score.get('home')
                    ag = score.get('away')
                    hg = hg if hg is not None else '-'
                    ag = ag if ag is not None else '-'
                    summary = f"🏆 {home_name} {hg} x {ag} {away_name}"
                
                ics_lines.extend([
                    "BEGIN:VEVENT",
                    f"UID:palmeiras-{match_id}@palmeiras-web",
                    f"DTSTAMP:{now}",
                    f"DTSTART;TZID=America/Sao_Paulo:{start}",
                    f"DTEND;TZID=America/Sao_Paulo:{end}",
                    f"SUMMARY:{summary}",
                    f"DESCRIPTION:Status: {status}",
                    "END:VEVENT",
                ])
            except Exception:
                continue
        
        ics_lines.append("END:VCALENDAR")
        
        return Response(
            '\n'.join(ics_lines),
            mimetype='text/calendar',
            headers={
                'Cache-Control': 'no-cache, no-store, must-revalidate',
            }
        )
        
    except Exception as e:
        return Response(f"Error: {str(e)}", status=500)


def handler(event, context):
    return app(event, context)
