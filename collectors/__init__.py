"""
Palmeiras Data Collector v2

Fetches matches, standings, news, and broadcast info from external APIs.
Saves to Supabase. Run via cron or manually.

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
try:
    from collectors.crest_manager import get_or_download_crest
except ImportError:
    from crest_manager import get_or_download_crest

load_dotenv(Path(__file__).parent.parent / '.env')

SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY')
FOOTBALL_API_KEY = os.environ.get('FOOTBALL_API_KEY')
TEAM_ID = 1769
API_BASE = 'https://api.football-data.org/v4'
HEADERS = {'X-Auth-Token': FOOTBALL_API_KEY} if FOOTBALL_API_KEY else {}
PALMEIRAS_HOME = 'Allianz Parque'

# Known broadcast partners for Brazilian football
BROADCAST_MAP = {
    'BSA': 'Premiere / Globo',
    'COPA': 'SporTV / Premiere',
    'COPA_DO_BRASIL': 'SporTV / Premiere',
    'CLI': 'ESPN / Star+',
    'LIBERTADORES': 'ESPN / Star+',
    'COPA_LIBERTADORES': 'ESPN / Star+',
}


def get_supabase():
    if not (SUPABASE_URL and SUPABASE_KEY):
        print("  Missing SUPABASE_URL or SUPABASE_KEY")
        return None
    from supabase import create_client
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def collect_matches():
    """Fetch all Palmeiras matches with enhanced data."""
    print("  Fetching matches...")
    client = get_supabase()
    if not client or not FOOTBALL_API_KEY:
        return

    try:
        # Past + current matches
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

        # Also fetch from other competitions (Libertadores, Copa do Brasil)
        for comp in ['CBC', 'CL']:
            try:
                resp3 = requests.get(
                    f"{API_BASE}/teams/{TEAM_ID}/matches?competitions={comp}&limit=50",
                    headers=HEADERS, timeout=30
                )
                if resp3.status_code == 200:
                    existing = {m['id'] for m in matches}
                    for m in resp3.json().get('matches', []):
                        if m['id'] not in existing:
                            matches.append(m)
            except Exception:
                pass

        print(f"    Found {len(matches)} matches")
        now = datetime.now(timezone.utc).isoformat()

        records = []
        for m in matches:
            home = m.get('homeTeam', {})
            away = m.get('awayTeam', {})
            comp = m.get('competition', {})
            score = m.get('score', {})
            ft = score.get('fullTime', {})
            ht = score.get('halfTime', {})

            # Cache team crests locally
            for team in (home, away):
                tid = team.get('id')
                if tid:
                    local_crest = get_or_download_crest(tid, team.get('crest', ''))
                    if local_crest:
                        team['crest'] = local_crest
                    elif tid:  # No crest available
                        team['crest'] = None

            # Determine venue
            venue = m.get('venue')
            if not venue and home.get('id') == TEAM_ID:
                venue = PALMEIRAS_HOME

            # Broadcast from known map
            broadcast = BROADCAST_MAP.get(comp.get('code'), '')

            # Referees
            referees = m.get('referees', [])

            records.append({
                'external_id': m['id'],
                'home_team': json.dumps(home),
                'away_team': json.dumps(away),
                'home_score': ft.get('home'),
                'away_score': ft.get('away'),
                'utc_date': m.get('utcDate'),
                'status': m.get('status'),
                'competition': json.dumps(comp),
                'matchday': m.get('matchday'),
                'venue': venue,
                'updated_at': now,
                'half_time_home': ht.get('home'),
                'half_time_away': ht.get('away'),
                'season': json.dumps(m.get('season', {})),
                'stage': m.get('stage', ''),
                'area': json.dumps(m.get('area', {})),
                'referees': json.dumps(referees),
                'broadcast': broadcast,
            })

        try:
            client.table('matches').upsert(records, on_conflict='external_id').execute()
            print(f"    Saved {len(records)} matches")
        except Exception as e:
            print(f"    Error saving matches: {e}")

    except Exception as e:
        print(f"    Error: {e}")


def collect_standings():
    """Fetch league standings with form."""
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

        if not table:
            print("    No standings data found")
            return

        print(f"    Found {len(table)} teams")
        now = datetime.now(timezone.utc).isoformat()

        # Build all records first, then replace atomically
        records = []
        for entry in table:
            records.append({
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
                'form': entry.get('form', ''),
                'updated_at': now,
            })

        # Delete old data only after we have new data ready
        client.table('standings').delete().neq('id', '00000000-0000-0000-0000-000000000000').execute()

        for record in records:
            client.table('standings').insert(record).execute()

        print(f"    Saved {len(records)} standings")

    except Exception as e:
        print(f"    Error: {e}")


def collect_news():
    """Fetch Palmeiras news from multiple sources."""
    print("  Fetching news...")
    client = get_supabase()
    if not client:
        return

    try:
        from bs4 import BeautifulSoup
    except ImportError:
        print("    beautifulsoup4 not installed, skipping")
        return

    news = []
    now = datetime.now(timezone.utc).isoformat()

    # Source 1: ge.globo
    try:
        resp = requests.get(
            "https://ge.globo.com/futebol/times/palmeiras/",
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36", "Accept-Language": "pt-BR,pt;q=0.9"},
            timeout=30,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        articles = (soup.select("div.feed-post-body") or soup.select("article"))[:10]

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
                    'collected_at': now,
                })
        print(f"    ge.globo: {len(news)} articles")
    except Exception as e:
        print(f"    ge.globo error: {e}")

    # Source 2: lance.com.br
    try:
        resp = requests.get(
            "https://www.lance.com.br/palmeiras",
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36", "Accept-Language": "pt-BR,pt;q=0.9"},
            timeout=30,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        articles = soup.select("article")[:5]
        lance_count = 0
        for a in articles:
            title = a.select_one("h2, h3, .title")
            link = a.select_one("a")
            img = a.select_one("img")
            if title and link:
                href = link.get("href", "")
                if href and not href.startswith("http"):
                    href = "https://www.lance.com.br" + href
                news.append({
                    'title': title.get_text(strip=True),
                    'url': href,
                    'image': img.get("src", "") if img else "",
                    'source': 'lance.com.br',
                    'collected_at': now,
                })
                lance_count += 1
        print(f"    lance.com.br: {lance_count} articles")
    except Exception as e:
        print(f"    lance.com.br error: {e}")

    # Source 3: Gazeta Esportiva
    try:
        resp = requests.get(
            "https://www.gazetaesportiva.com/futebol/times/palmeiras/",
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36", "Accept-Language": "pt-BR,pt;q=0.9"},
            timeout=30,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        articles = soup.select("article")[:5]
        gazeta_count = 0
        for a in articles:
            title = a.select_one("h2, h3, .title, a")
            link = a.select_one("a")
            if title and link:
                href = link.get("href", "")
                if href and not href.startswith("http"):
                    href = "https://www.gazetaesportiva.com" + href
                news.append({
                    'title': title.get_text(strip=True),
                    'url': href,
                    'image': "",
                    'source': 'gazetaesportiva.com',
                    'collected_at': now,
                })
                gazeta_count += 1
        print(f"    gazetaesportiva.com: {gazeta_count} articles")
    except Exception as e:
        print(f"    gazetaesportiva.com error: {e}")

    # Source 4: UOL Esporte
    try:
        resp = requests.get(
            "https://www.uol.com.br/esporte/futebol/times/palmeiras/",
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36", "Accept-Language": "pt-BR,pt;q=0.9"},
            timeout=30,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        articles = soup.select("article, .tileItem")[:5]
        uol_count = 0
        for a in articles:
            title = a.select_one("h2, h3, .title, a")
            link = a.select_one("a")
            if title and link:
                href = link.get("href", "")
                if href and not href.startswith("http"):
                    href = "https://www.uol.com.br" + href
                news.append({
                    'title': title.get_text(strip=True),
                    'url': href,
                    'image': "",
                    'source': 'uol.com.br',
                    'collected_at': now,
                })
                uol_count += 1
        print(f"    uol.com.br: {uol_count} articles")
    except Exception as e:
        print(f"    uol.com.br error: {e}")

    # Save all news only if we got results
    if news:
        try:
            client.table('news').delete().neq('id', '00000000-0000-0000-0000-000000000000').execute()
            for item in news:
                client.table('news').insert(item).execute()
            print(f"    Saved {len(news)} news articles")
        except Exception as e:
            print(f"    Error saving news: {e}")
    else:
        print("    No news collected, keeping existing data")


def apply_broadcast_info():
    """Apply known broadcast partners to upcoming matches based on competition code."""
    print("  Applying broadcast info...")
    client = get_supabase()
    if not client:
        return

    try:
        result = client.table('matches').select('*').in_('status', ['SCHEDULED', 'TIMED']).execute()
        upcoming = result.data[:5]
    except Exception:
        return

    updated = 0
    for match in upcoming:
        try:
            ext_id = match.get('external_id')
            comp = json.loads(match.get('competition') or '{}')
            comp_code = comp.get('code', '')

            broadcast = BROADCAST_MAP.get(comp_code, '')
            if broadcast and ext_id:
                client.table('matches').update({'broadcast': broadcast}).eq('external_id', ext_id).execute()
                updated += 1
        except Exception:
            continue

    print(f"    Updated {updated} matches")


if __name__ == '__main__':
    print(f"Palmeiras Collector v2 — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    collect_matches()
    collect_standings()
    collect_news()
    apply_broadcast_info()
    print("Done!")
