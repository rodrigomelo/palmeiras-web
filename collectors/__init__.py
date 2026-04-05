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

SILENT = True  # Set False for debugging
def _print(*args, **kwargs):
    if not SILENT:
        print(*args, **kwargs)

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
        _print("  Missing SUPABASE_URL or SUPABASE_KEY")
        return None
    from supabase import create_client
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def collect_matches():
    """Fetch all Palmeiras matches with enhanced data."""
    _print("  Fetching matches...")
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

        _print(f"    Found {len(matches)} matches")
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
            _print(f"    Saved {len(records)} matches")
        except Exception as e:
            _print(f"    Error saving matches: {e}")

    except Exception as e:
        _print(f"    Error: {e}")


def collect_standings():
    """Fetch league standings with form."""
    _print("  Fetching standings...")
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
            _print("    No standings data found")
            return

        _print(f"    Found {len(table)} teams")
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

        _print(f"    Saved {len(records)} standings")

    except Exception as e:
        _print(f"    Error: {e}")


def collect_news():
    """Fetch Palmeiras news from multiple sources."""
    _print("  Fetching news...")
    client = get_supabase()
    if not client:
        return

    try:
        from bs4 import BeautifulSoup
    except ImportError:
        _print("    beautifulsoup4 not installed, skipping")
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
        _print(f"    ge.globo: {len(news)} articles")
    except Exception as e:
        _print(f"    ge.globo error: {e}")

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
        _print(f"    lance.com.br: {lance_count} articles")
    except Exception as e:
        _print(f"    lance.com.br error: {e}")

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
        _print(f"    gazetaesportiva.com: {gazeta_count} articles")
    except Exception as e:
        _print(f"    gazetaesportiva.com error: {e}")

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
        _print(f"    uol.com.br: {uol_count} articles")
    except Exception as e:
        _print(f"    uol.com.br error: {e}")

    # Filter out low-quality articles
    SKIP_TITLES = {
        'jogos', 'vídeos curtos do verdão!', 'vídeos', 'vídeo',
        'ao vivo', 'mais lidas', 'mais lidas da semana',
    }
    filtered = []
    for item in news:
        title = item.get('title', '').strip().lower()
        url = item.get('url', '').strip()
        if not url:
            continue  # Skip articles without URL
        if title in SKIP_TITLES:
            continue  # Skip generic titles
        if len(title) < 5:
            continue  # Skip very short titles
        filtered.append(item)
    removed = len(news) - len(filtered)
    if removed:
        _print(f"    Filtered out {removed} low-quality articles")

    # Save all news only if we got results
    if filtered:
        try:
            client.table('news').delete().neq('id', '00000000-0000-0000-0000-000000000000').execute()
            for item in filtered:
                client.table('news').insert(item).execute()
            _print(f"    Saved {len(filtered)} news articles")
        except Exception as e:
            _print(f"    Error saving news: {e}")
    else:
        _print("    No news collected, keeping existing data")


def apply_broadcast_info():
    """Apply known broadcast partners to upcoming matches based on competition code."""
    _print("  Applying broadcast info...")
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

    _print(f"    Updated {updated} matches")


def collect_copa_brasil():
    """Collect Copa do Brasil matches from free sources (scrapers)."""
    _print("  Copa do Brasil (free sources)...")
    client = get_supabase()
    if not client:
        return

    try:
        try:
            from collectors.copa_brasil_scraper import get_copa_brasil_matches
        except ImportError:
            from copa_brasil_scraper import get_copa_brasil_matches
        matches = get_copa_brasil_matches()
        if not matches:
            _print("    No Copa do Brasil matches found from scrapers")
            return

        # Check if matches are Supabase-ready dicts or raw scraper output
        saved = 0
        for m in matches:
            if 'external_id' in m:
                # Already Supabase-ready (known data)
                ext_id = m.get('external_id')
                existing = client.table('matches').select('external_id').eq('external_id', ext_id).execute()
                if not existing.data:
                    client.table('matches').insert(m).execute()
                    saved += 1
                else:
                    # Update existing (maybe new scores/dates)
                    client.table('matches').update(m).eq('external_id', ext_id).execute()
                    saved += 1
            else:
                # Raw scraper output — convert to Supabase format
                h_name = m.get('home_team_name', '?')
                a_name = m.get('away_team_name', '?')
                comp_code = m.get('competition_code', 'COPA')
                comp_name = m.get('competition_name', 'Copa do Brasil')
                utc_date = m.get('utc_date')
                source = m.get('source', 'scraper')

                if not utc_date:
                    continue

                # Create a deterministic ID
                import hashlib
                id_str = f"{comp_code}_{h_name}_{a_name}_{utc_date[:10]}"
                ext_id = f"CBC_{hashlib.md5(id_str.encode()).hexdigest()[:8]}"

                record = {
                    'external_id': ext_id,
                    'utc_date': utc_date,
                    'status': 'SCHEDULED',
                    'matchday': None,
                    'stage': 'COPA_DO_BRASIL',
                    'home_team': json.dumps({'name': h_name, 'shortName': h_name, 'tla': h_name[:3].upper()}),
                    'away_team': json.dumps({'name': a_name, 'shortName': a_name, 'tla': a_name[:3].upper()}),
                    'competition': json.dumps({'code': comp_code, 'name': comp_name}),
                    'season': json.dumps({'year': 2026}),
                    'venue': '',
                    'home_score': None,
                    'away_score': None,
                    'half_time_home': None,
                    'half_time_away': None,
                    'referees': '[]',
                    'broadcast': 'SporTV / Premiere',
                }

                existing = client.table('matches').select('external_id').eq('external_id', ext_id).execute()
                if not existing.data:
                    client.table('matches').insert(record).execute()
                    saved += 1

        _print(f"    Copa do Brasil: {saved} matches saved/updated")
    except Exception as e:
        _print(f"    Copa do Brasil error: {e}")


if __name__ == '__main__':
    _print(f"Palmeiras Collector v2 — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    collect_matches()
    collect_standings()
    collect_news()
    collect_copa_brasil()
    apply_broadcast_info()
    _print("Done!")
