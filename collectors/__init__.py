"""
Palmeiras Data Collector

Fetches matches, standings, and news from external APIs,
then saves to Supabase. Run via cron or manually.

Usage:
    cd collectors
    python -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt
    python __init__.py
"""
import os
import json
import requests
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / '.env')

SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY')
FOOTBALL_API_KEY = os.environ.get('FOOTBALL_API_KEY')
TEAM_ID = 1769
API_BASE = 'https://api.football-data.org/v4'
HEADERS = {'X-Auth-Token': FOOTBALL_API_KEY} if FOOTBALL_API_KEY else {}


def get_supabase():
    if not (SUPABASE_URL and SUPABASE_KEY):
        print("  ❌ Missing SUPABASE_URL or SUPABASE_KEY")
        return None
    from supabase import create_client
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def collect_matches():
    """Fetch all Palmeiras matches and upsert to Supabase."""
    print("  Fetching matches...")
    client = get_supabase()
    if not client or not FOOTBALL_API_KEY:
        return

    try:
        resp = requests.get(f"{API_BASE}/teams/{TEAM_ID}/matches?limit=100", headers=HEADERS, timeout=30)
        resp.raise_for_status()
        matches = resp.json().get('matches', [])

        # Future scheduled
        resp2 = requests.get(f"{API_BASE}/teams/{TEAM_ID}/matches?status=SCHEDULED,TIMED", headers=HEADERS, timeout=30)
        if resp2.status_code == 200:
            existing = {m['id'] for m in matches}
            for m in resp2.json().get('matches', []):
                if m['id'] not in existing:
                    matches.append(m)

        print(f"    Found {len(matches)} matches")
        now = datetime.now(timezone.utc).isoformat()
        records = [{
            'external_id': m['id'],
            'home_team': json.dumps(m.get('homeTeam', {})),
            'away_team': json.dumps(m.get('awayTeam', {})),
            'home_score': m.get('score', {}).get('fullTime', {}).get('home'),
            'away_score': m.get('score', {}).get('fullTime', {}).get('away'),
            'utc_date': m.get('utcDate'),
            'status': m.get('status'),
            'competition': json.dumps(m.get('competition', {})),
            'matchday': m.get('matchday'),
            'venue': m.get('venue'),
            'updated_at': now,
        } for m in matches]

        client.table('matches').upsert(records, on_conflict='external_id').execute()
        print(f"    ✅ Saved {len(records)} matches")
    except Exception as e:
        print(f"    ❌ {e}")


def collect_standings():
    """Fetch league standings and save to Supabase."""
    print("  Fetching standings...")
    client = get_supabase()
    if not client or not FOOTBALL_API_KEY:
        return

    try:
        resp = requests.get(f"{API_BASE}/competitions/BSA/standings", headers=HEADERS, timeout=30)
        resp.raise_for_status()
        table = []
        for s in resp.json().get('standings', []):
            if s.get('type') == 'TOTAL':
                table = s.get('table', [])
                break

        print(f"    Found {len(table)} teams")
        client.table('standings').delete().neq('id', '00000000-0000-0000-0000-000000000000').execute()

        now = datetime.now(timezone.utc).isoformat()
        for entry in table:
            client.table('standings').insert({
                'competition': 'BSA',
                'position': entry.get('position'),
                'team': json.dumps(entry.get('team', {})),
                'played_games': entry.get('playedGames'),
                'won': entry.get('won'),
                'drawn': entry.get('draw'),
                'lost': entry.get('lost'),
                'goals_for': entry.get('goalsFor'),
                'goals_against': entry.get('goalsAgainst'),
                'goal_difference': entry.get('goalDifference'),
                'points': entry.get('points'),
                'updated_at': now,
            }).execute()

        print(f"    ✅ Saved {len(table)} standings")
    except Exception as e:
        print(f"    ❌ {e}")


def collect_news():
    """Fetch Palmeiras news from ge.globo."""
    print("  Fetching news...")
    client = get_supabase()
    if not client:
        return

    try:
        from bs4 import BeautifulSoup
    except ImportError:
        print("    ⚠️  beautifulsoup4 not installed, skipping")
        return

    try:
        resp = requests.get(
            "https://ge.globo.com/futebol/times/palmeiras/",
            headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "pt-BR,pt;q=0.9"},
            timeout=30,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        articles = (soup.select("div.feed-post-body") or soup.select("article"))[:15]

        news = []
        for a in articles:
            title = a.select_one("a.feed-post-link") or a.select_one("h2")
            link = a.select_one("a.feed-post-link")
            img = a.select_one("img")
            if title and link:
                news.append({
                    'title': title.get_text(strip=True),
                    'url': link.get("href", ""),
                    'image': img.get("src", "") if img else "",
                    'source': 'ge.globo',
                    'collected_at': datetime.now(timezone.utc).isoformat(),
                })

        client.table('news').delete().neq('id', '00000000-0000-0000-0000-000000000000').execute()
        for item in news:
            client.table('news').insert(item).execute()

        print(f"    ✅ Saved {len(news)} news")
    except Exception as e:
        print(f"    ❌ {e}")


if __name__ == '__main__':
    print(f"🏆 Palmeiras Collector — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    collect_matches()
    collect_standings()
    collect_news()
    print("✅ Done!")
