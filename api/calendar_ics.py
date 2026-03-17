import requests
import json
from datetime import datetime, timezone, timedelta


def handler(request):
    DATA_API = 'https://palmeiras-data.vercel.app'
    
    try:
        # Fetch all matches (past and future)
        resp = requests.get(f"{DATA_API}/api/matches?status=FINISHED,TIMED,SCHEDULED,IN_PLAY&limit=100", timeout=30)
        if resp.status_code != 200:
            return resp.text, resp.status_code, {'Content-Type': 'text/plain'}
        
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
        
        now = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')
        
        for m in matches:
            utc_date = m.get('utcDate', '')
            if not utc_date:
                continue
            
            try:
                dt = datetime.fromisoformat(utc_date.replace('Z', '+00:00'))
                sp_tz = timezone(timedelta(hours=-3))
                dt_sp = dt.astimezone(sp_tz)
                start = dt_sp.strftime('%Y%m%dT%H%M%S')
                end_hour = (dt_sp.hour + 2) % 24
                end = dt_sp.replace(hour=end_hour).strftime('%Y%m%dT%H%M%S')
                
                home_team = m.get('homeTeam', {})
                away_team = m.get('awayTeam', {})
                
                home_name = home_team.get('name', 'Home') if isinstance(home_team, dict) else 'Home'
                away_name = away_team.get('name', 'Away') if isinstance(away_team, dict) else 'Away'
                
                match_id = m.get('id', '')
                status = m.get('status', '')
                
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
        
        return '\n'.join(ics_lines), 200, {
            'Content-Type': 'text/calendar',
            'Cache-Control': 'no-cache, no-store, must-revalidate',
        }
        
    except Exception as e:
        return f"Error: {str(e)}", 500, {'Content-Type': 'text/plain'}
