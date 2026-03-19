"""
Palmeiras Data API - FastAPI Server

Production server for Vercel deployment. Reads from Supabase.
Local development uses the same server via uvicorn.
"""
import os
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

# Load .env
env_path = Path(__file__).parent.parent / '.env'
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if '=' in line and not line.startswith('#'):
                key, val = line.split('=', 1)
                os.environ.setdefault(key.strip(), val.strip())

# Config
SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY')
TEAM_ID = 1769
BR_TZ = timezone(timedelta(hours=-3))

# Supabase client (lazy)
try:
    from supabase import create_client
    HAS_SUPABASE = True
except ImportError:
    HAS_SUPABASE = False


def get_supabase():
    """Create Supabase client on demand."""
    if not (SUPABASE_URL and SUPABASE_KEY and HAS_SUPABASE):
        return None
    return create_client(SUPABASE_URL, SUPABASE_KEY)


# FastAPI app
app = FastAPI(
    title="Palmeiras Data API",
    version="2.0.0",
    description="Data API for Palmeiras Dashboard",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def health():
    """Health check."""
    return {
        "name": "Palmeiras Data API",
        "version": "2.0.0",
        "status": "ok",
        "supabase": bool(SUPABASE_URL),
    }


@app.get("/api/matches")
def get_matches(
    status: Optional[str] = Query(None, description="Filter: FINISHED, SCHEDULED, TIMED, IN_PLAY"),
    limit: int = Query(50, ge=1, le=100),
    from_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
):
    """
    Fetch matches from Supabase.
    - FINISHED: most recent first
    - SCHEDULED/TIMED/IN_PLAY: nearest first from today
    """
    client = get_supabase()
    if not client:
        return {"matches": [], "status": "not_connected"}

    try:
        query = client.table('matches').select('*')

        if status:
            statuses = [s.strip().upper() for s in status.split(',')]
            if len(statuses) == 1:
                query = query.eq('status', statuses[0])
            else:
                query = query.in_('status', statuses)

            # For upcoming, filter from today
            if any(s in ('SCHEDULED', 'TIMED', 'IN_PLAY') for s in statuses) and not from_date:
                from_date = datetime.now(timezone.utc).strftime('%Y-%m-%d')

        if from_date:
            query = query.gte('utc_date', from_date)

        fetch_limit = max(limit * 3, 50)
        result = query.order('utc_date').limit(fetch_limit).execute()
        matches = result.data

        # Sort: FINISHED descending, others ascending
        has_finished = any(m.get('status') == 'FINISHED' for m in matches)
        if has_finished:
            matches.sort(key=lambda x: x.get('utc_date', ''), reverse=True)

        matches = matches[:limit]

        # Transform
        return {"matches": [_transform_match(m) for m in matches]}

    except Exception as e:
        return {"matches": [], "error": str(e)}


@app.get("/api/standings")
def get_standings(competition: str = Query("BSA")):
    """Fetch standings from Supabase."""
    client = get_supabase()
    if not client:
        return {"standings": [], "status": "not_connected"}

    try:
        result = client.table('standings').select('*').eq('competition', competition).order('position').execute()
        return {"standings": result.data}
    except Exception as e:
        return {"standings": [], "error": str(e)}


@app.get("/api/news")
def get_news(limit: int = Query(10, ge=1, le=50)):
    """Fetch news from Supabase."""
    client = get_supabase()
    if not client:
        return []

    try:
        result = client.table('news').select('*').order('collected_at', desc=True).limit(limit).execute()
        return result.data
    except Exception as e:
        return []


@app.get("/api/calendar.ics")
@app.get("/calendar.ics")
def calendar_ics(limit: int = Query(100, ge=1, le=200)):
    """Generate iCal feed for all Palmeiras matches."""
    client = get_supabase()
    if not client:
        return Response("No database", status_code=500)

    try:
        result = client.table('matches').select('*').execute()
        matches = sorted(result.data, key=lambda x: x.get('utc_date', ''), reverse=True)[:limit]

        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//Palmeiras//Data API//EN",
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

                home = _parse_json(m.get('home_team', {}))
                away = _parse_json(m.get('away_team', {}))
                home_name = home.get('name', 'Home') if isinstance(home, dict) else 'Home'
                away_name = away.get('name', 'Away') if isinstance(away, dict) else 'Away'

                status = m.get('status', '')
                summary = f"🏆 {home_name} x {away_name}"
                if status == 'FINISHED':
                    hg = m.get('home_score', '-')
                    ag = m.get('away_score', '-')
                    summary = f"🏆 {home_name} {hg} x {ag} {away_name}"

                lines.extend([
                    "BEGIN:VEVENT",
                    f"UID:palmeiras-{m.get('external_id', '')}@palmeiras",
                    f"DTSTAMP:{now}",
                    f"DTSTART;TZID=America/Sao_Paulo:{start}",
                    f"DTEND;TZID=America/Sao_Paulo:{end}",
                    f"SUMMARY:{summary}",
                    "END:VEVENT",
                ])
            except Exception:
                continue

        lines.append("END:VCALENDAR")

        return Response(
            '\r\n'.join(lines),
            media_type='text/calendar',
            headers={'Cache-Control': 'public, max-age=3600'},
        )
    except Exception as e:
        return Response(f"Error: {e}", status_code=500)


# --- Helpers ---

def _parse_json(val):
    """Parse JSON string or return dict as-is."""
    if isinstance(val, str):
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return {}
    return val if isinstance(val, dict) else {}


def _transform_match(m):
    """Transform Supabase row to frontend format."""
    return {
        'id': m.get('external_id'),
        'utcDate': m.get('utc_date'),
        'status': m.get('status'),
        'matchday': m.get('matchday'),
        'venue': m.get('venue'),
        'homeTeam': _parse_json(m.get('home_team', '{}')),
        'awayTeam': _parse_json(m.get('away_team', '{}')),
        'competition': _parse_json(m.get('competition', '{}')),
        'score': {
            'fullTime': {
                'home': m.get('home_score'),
                'away': m.get('away_score'),
            }
        },
    }


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=5002)
