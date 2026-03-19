"""
Palmeiras Data Collector

Fetches matches, standings, and news from external APIs,
then saves to Supabase. Runs via cron or manually.
"""
import os
import json
import requests
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / '.env')

# Config
SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY')
FOOTBALL_API_KEY = os.environ.get('FOOTBALL_API_KEY')
TEAM_ID = 1769
API_BASE = 'https://api.football-data.org/v4'
HEADERS = {'X-Auth-Token': FOOTBALL_API_KEY} if FOOTBALL_API_KEY else {}


def get_supabase():
    """Create Supabase client."""
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
        # Past + current matches
        resp = requests.get(f"{API_BASE}/teams/{TEAM_ID}/matches?limit=100", headers=HEADERS, timeout=30)
        resp.raise_for_status()
        matches = resp.json().get('matches', [])

        # Future scheduled matches
        resp_future = requests.get(
            f"{API_BASE}/teams/{TEAM_ID}/matches?status=SCHEDULED,TIMED",
            headers=HEADERS, timeout=30,
        )
        if resp_future.status_code == 200:
            existing_ids = {m['id'] for m in matches}
            for m in resp_future.json().get('matches', []):
                if m['id'] not in existing_ids:
                    matches.append(m)

        print(f"    Found {len(matches)} matches")

        now = datetime.now(timezone.utc).isoformat()
        records = [
            {
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
            }
            for m in matches
        ]

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
        data = resp.json()

        table = []
        for standing in data.get('standings', []):
            if standing.get('type') == 'TOTAL':
                table = standing.get('table', [])
                break

        print(f"    Found {len(table)} teams")

        # Clear old standings
        client.table('standings').delete().neq('id', '00000000-0000-0000-0000-000000000000').execute()

        now = datetime.now(timezone.utc).isoformat()
        for entry in table:
            record = {
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
            }
            client.table('standings').insert(record).execute()

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
        print("    ⚠️  beautifulsoup4 not installed, skipping news")
        return

    try:
        resp = requests.get(
            "https://ge.globo.com/futebol/times/palmeiras/",
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "Accept-Language": "pt-BR,pt;q=0.9",
            },
            timeout=30,
        )
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        articles = soup.select("div.feed-post-body") or soup.select("article")[:15]

        news = []
        for article in articles:
            title_el = article.select_one("a.feed-post-link") or article.select_one("h2")
            link_el = article.select_one("a.feed-post-link")
            img_el = article.select_one("img")

            if title_el and link_el:
                news.append({
                    'title': title_el.get_text(strip=True),
                    'url': link_el.get("href", ""),
                    'image': img_el.get("src", "") if img_el else "",
                    'source': 'ge.globo',
                    'collected_at': datetime.now(timezone.utc).isoformat(),
                })

        # Replace old news
        client.table('news').delete().neq('id', '00000000-0000-0000-0000-000000000000').execute()
        for item in news:
            client.table('news').insert(item).execute()

        print(f"    ✅ Saved {len(news)} news")

    except Exception as e:
        print(f"    ❌ {e}")


def run_all():
    """Run all collectors."""
    print("=" * 50)
    print(f" 🏆 Palmeiras Data Collector")
    print(f"    {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 50)

    collect_matches()
    collect_standings()
    collect_news()

    print("\n ✅ Done!")


if __name__ == '__main__':
    run_all()
