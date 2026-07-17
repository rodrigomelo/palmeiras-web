"""
Palmeiras Data Collector v2

Fetches matches, standings, news, and broadcast info from external APIs.
Saves to Supabase. Run via cron or manually.

Usage:
    cd apps/web
    python -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt
    python __init__.py
"""
import os
import json
import requests
import sys
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
import xml.etree.ElementTree as ET

from dotenv import load_dotenv
try:
    from collectors.crest_manager import get_or_download_crest
    from collectors.enrichment import palmeiras_venue_fallback
except ImportError:
    from crest_manager import get_or_download_crest
    from enrichment import palmeiras_venue_fallback  # type: ignore

load_dotenv(Path(__file__).parent.parent / '.env')

SILENT = False  # Set True for debugging
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

MATCH_COLUMNS = {
    'external_id',
    'home_team',
    'away_team',
    'home_score',
    'away_score',
    'half_time_home',
    'half_time_away',
    'utc_date',
    'status',
    'competition',
    'season',
    'matchday',
    'stage',
    'venue',
    'area',
    'referees',
    'broadcast',
    'updated_at',
}

# Known broadcast partners — single source of truth lives in broadcast_scraper.py
# Imported lazily below to avoid circular imports at module load
BROADCAST_MAP = None  # type: ignore[assignment]


def _get_broadcast_map() -> dict:
    """Get the broadcast map (lazy-loaded to avoid circular imports)."""
    global BROADCAST_MAP
    if BROADCAST_MAP is None:
        try:
            from collectors.broadcast_scraper import BROADCAST_MAP as _bm
        except ImportError:
            from broadcast_scraper import BROADCAST_MAP as _bm
        BROADCAST_MAP = _bm
    return BROADCAST_MAP


def get_supabase():
    if not (SUPABASE_URL and SUPABASE_KEY):
        _print("  Missing SUPABASE_URL or SUPABASE_KEY")
        return None
    from supabase import create_client
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def _json(value):
    return json.dumps(value or {}, ensure_ascii=False)


def _football_data_get(path, *, params=None, timeout=30, retries=2):
    """Fetch football-data.org JSON with small retry/backoff for transient errors."""
    url = path if path.startswith('http') else f'{API_BASE}{path}'
    last_error = None
    for attempt in range(retries + 1):
        try:
            resp = requests.get(url, headers=HEADERS, params=params, timeout=timeout)
            if resp.status_code in (429, 500, 502, 503, 504) and attempt < retries:
                time.sleep(2 * (attempt + 1))
                continue
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as error:
            last_error = error
            if attempt < retries:
                time.sleep(2 * (attempt + 1))
                continue
            raise last_error


def _cache_crests_for_match(home, away):
    for team in (home, away):
        tid = team.get('id')
        if tid:
            local_crest = get_or_download_crest(tid, team.get('crest', ''))
            if local_crest:
                team['crest'] = local_crest
            else:
                team['crest'] = None


def _match_to_record(match, now, *, cache_crests=True, broadcast=None):
    """Convert a football-data.org match object to the matches table schema."""
    if 'id' not in match:
        raise ValueError("Match missing required 'id' field")

    home = dict(match.get('homeTeam') or {})
    away = dict(match.get('awayTeam') or {})
    comp = dict(match.get('competition') or {})
    score = match.get('score') or {}
    ft = score.get('fullTime') or {}
    ht = score.get('halfTime') or {}

    if cache_crests:
        _cache_crests_for_match(home, away)

    venue = match.get('venue') or palmeiras_venue_fallback(home, away)

    if broadcast is None:
        broadcast = _get_broadcast_map().get(comp.get('code'), '')

    return {
        'external_id': int(match['id']),
        'home_team': _json(home),
        'away_team': _json(away),
        'home_score': ft.get('home'),
        'away_score': ft.get('away'),
        'utc_date': match.get('utcDate'),
        'status': match.get('status'),
        'competition': _json(comp),
        'matchday': match.get('matchday'),
        'venue': venue,
        'updated_at': now,
        'half_time_home': ht.get('home'),
        'half_time_away': ht.get('away'),
        'season': _json(match.get('season', {})),
        'stage': match.get('stage', ''),
        'area': _json(match.get('area', {})),
        'referees': json.dumps(match.get('referees', []) or [], ensure_ascii=False),
        'broadcast': broadcast or '',
    }


def _sanitize_match_record(record):
    """Drop collector-only fields before writing to Supabase."""
    return {key: value for key, value in record.items() if key in MATCH_COLUMNS}


def _deterministic_external_id(*parts):
    """Create a stable positive integer id for scraped fixtures without API ids."""
    import hashlib
    digest = hashlib.md5('|'.join(str(part) for part in parts).encode()).hexdigest()
    return 980_000_000 + (int(digest[:8], 16) % 100_000_000)


def collect_matches():
    """Fetch all Palmeiras matches with enhanced data."""
    _print("  Fetching matches...")
    client = get_supabase()
    if not client or not FOOTBALL_API_KEY:
        return False

    try:
        # Past + current matches
        matches = _football_data_get(f"/teams/{TEAM_ID}/matches", params={'limit': 100}).get('matches', [])

        # Future scheduled
        try:
            resp2 = _football_data_get(f"/teams/{TEAM_ID}/matches", params={'status': 'SCHEDULED,TIMED'})
            existing = {m['id'] for m in matches}
            for m in resp2.get('matches', []):
                if m['id'] not in existing:
                    matches.append(m)
        except Exception as error:
            _print(f"    Upcoming matches fetch warning: {error}")

        # Also fetch from other competitions (Libertadores, Copa do Brasil)
        for comp in ['CBC', 'CL']:
            try:
                resp3 = _football_data_get(
                    f"/teams/{TEAM_ID}/matches",
                    params={'competitions': comp, 'limit': 50},
                )
                existing = {m['id'] for m in matches}
                for m in resp3.get('matches', []):
                    if m['id'] not in existing:
                        matches.append(m)
            except Exception as error:
                _print(f"    {comp} fetch warning: {error}")

        _print(f"    Found {len(matches)} matches")
        if not matches:
            return False
        now = datetime.now(timezone.utc).isoformat()

        records = []
        skipped = 0
        for m in matches:
            try:
                records.append(_match_to_record(m, now, cache_crests=True))
            except Exception as e:
                skipped += 1
                _print(f"    Skipping malformed match {m.get('id', '?')}: {e}")

        if skipped:
            _print(f"    Skipped {skipped} malformed matches out of {len(matches)}")

        try:
            if records:
                client.table('matches').upsert(records, on_conflict='external_id').execute()
            _print(f"    Saved {len(records)} matches")
            return bool(records)
        except Exception as e:
            _print(f"    Error saving matches: {e}")
            return False

    except Exception as e:
        _print(f"    Error: {e}")
        return False


def collect_standings():
    """Fetch league standings with form."""
    _print("  Fetching standings...")
    client = get_supabase()
    if not client or not FOOTBALL_API_KEY:
        return False

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
            return False

        _print(f"    Found {len(table)} teams")
        now = datetime.now(timezone.utc).isoformat()

        # Build all records first, then upsert atomically
        records = []
        skipped = 0
        for entry in table:
            try:
                position = entry.get('position')
                if position is None:
                    raise ValueError("Standings entry missing 'position' field")
                records.append({
                    'competition': 'BSA',
                    'position': position,
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
            except Exception as e:
                skipped += 1
                _print(f"    Skipping malformed standings entry: {e}")

        if skipped:
            _print(f"    Skipped {skipped} malformed standings entries out of {len(table)}")

        saved = 0
        for record in records:
            existing = (
                client.table('standings')
                .select('id')
                .eq('competition', record['competition'])
                .eq('position', record['position'])
                .limit(1)
                .execute()
            )
            if existing.data:
                client.table('standings').update(record).eq('id', existing.data[0]['id']).execute()
            else:
                client.table('standings').insert(record).execute()
            saved += 1

        _print(f"    Saved {saved} standings")
        return bool(records)

    except Exception as e:
        _print(f"    Error: {e}")
        return False


def collect_news():
    """Fetch Palmeiras news from multiple sources."""
    _print("  Fetching news...")
    client = get_supabase()
    if not client:
        return False

    user_agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    headers = {"User-Agent": user_agent, "Accept-Language": "pt-BR,pt;q=0.9"}
    news = []
    now = datetime.now(timezone.utc).isoformat()

    def parse_rss_date(value):
        if not value:
            return None
        try:
            dt = parsedate_to_datetime(value)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).isoformat()
        except (TypeError, ValueError, IndexError, AttributeError):
            return None

    # Source 0: Google News RSS aggregator. This provides publication dates and
    # tends to keep working even when individual sports sites change markup.
    try:
        resp = requests.get(
            "https://news.google.com/rss/search",
            params={"q": "Palmeiras futebol", "hl": "pt-BR", "gl": "BR", "ceid": "BR:pt-419"},
            headers=headers,
            timeout=30,
        )
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        rss_count = 0
        for item in root.findall("./channel/item")[:25]:
            title = (item.findtext("title") or "").strip()
            href = (item.findtext("link") or "").strip()
            source_el = item.find("source")
            source_name = (source_el.text or "Google News").strip() if source_el is not None else "Google News"
            suffix = f" - {source_name}"
            if source_name and title.endswith(suffix):
                title = title[: -len(suffix)].strip()
            if title and href:
                news.append({
                    'title': title,
                    'url': href,
                    'image': "",
                    'source': source_name or 'Google News',
                    'published_at': parse_rss_date(item.findtext("pubDate")),
                    'collected_at': now,
                })
                rss_count += 1
        _print(f"    Google News RSS: {rss_count} articles")
    except Exception as e:
        _print(f"    Google News RSS error: {e}")

    try:
        from bs4 import BeautifulSoup
    except ImportError:
        BeautifulSoup = None  # type: ignore
        _print("    beautifulsoup4 not installed, skipping direct HTML sources")

    # Source 1: ge.globo
    if BeautifulSoup:
        try:
            resp = requests.get(
                "https://ge.globo.com/futebol/times/palmeiras/",
                headers=headers,
                timeout=30,
            )
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            articles = (soup.select("div.feed-post-body") or soup.select("article"))[:10]

            ge_count = 0
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
                    ge_count += 1
            _print(f"    ge.globo: {ge_count} articles")
        except Exception as e:
            _print(f"    ge.globo error: {e}")

    # Source 2: lance.com.br
    if BeautifulSoup:
        try:
            resp = requests.get(
                "https://www.lance.com.br/palmeiras",
                headers=headers,
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
                    # Prefer link text if title element contains a link with more complete text
                    link_text = link.get_text(strip=True)
                    title_text = title.get_text(strip=True)
                    final_title = link_text if len(link_text) > len(title_text) else title_text
                    href = link.get("href", "")
                    if href and not href.startswith("http"):
                        href = "https://www.lance.com.br" + href
                    news.append({
                        'title': final_title,
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
    if BeautifulSoup:
        try:
            resp = requests.get(
                "https://www.gazetaesportiva.com/futebol/times/palmeiras/",
                headers=headers,
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
    if BeautifulSoup:
        try:
            resp = requests.get(
                "https://www.uol.com.br/esporte/futebol/times/palmeiras/",
                headers=headers,
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
    SKIP_SOURCES = {
        'facebook.com', 'instagram.com', 'threads.net', 'tiktok.com',
        'twitter.com', 'x.com', 'youtube.com',
    }
    filtered = []
    seen_urls = set()
    for item in news:
        title = item.get('title', '').strip()
        title_lower = title.lower()
        url = item.get('url', '').strip()
        source_lower = item.get('source', '').strip().lower()
        if not url:
            continue  # Skip articles without URL
        if url in seen_urls:
            continue
        if source_lower in SKIP_SOURCES:
            continue
        if title_lower in SKIP_TITLES:
            continue  # Skip generic titles
        if len(title) < 15:
            continue  # Skip very short or likely truncated titles
        if len(title) > 180:
            continue  # Skip social embeds and malformed snippets
        seen_urls.add(url)
        filtered.append(item)
    removed = len(news) - len(filtered)
    if removed:
        _print(f"    Filtered out {removed} low-quality articles")

    # Save all news only if we got results. Use explicit update/insert instead
    # of on_conflict='url' so existing DBs without the optional unique index
    # still refresh correctly.
    if filtered:
        try:
            saved = 0
            for item in filtered:
                existing = (
                    client.table('news')
                    .select('id')
                    .eq('url', item['url'])
                    .limit(1)
                    .execute()
                )
                if existing.data:
                    client.table('news').update(item).eq('id', existing.data[0]['id']).execute()
                else:
                    client.table('news').insert(item).execute()
                saved += 1
            _print(f"    Saved {saved} news articles")
            return True
        except Exception as e:
            _print(f"    Error saving news: {e}")
            return False
    else:
        _print("    No news collected, keeping existing data")
        return True


def apply_broadcast_info():
    """Scrape broadcast info from ge.globo + static fallback.

    Delegates to collectors.broadcast_scraper for dynamic ge.globo scraping
    with BROADCAST_MAP as fallback when no match page exists yet.
    """
    _print("  Applying broadcast info (ge.globo + static fallback)...")
    try:
        from collectors.broadcast_scraper import collect_broadcast_info
    except ImportError:
        from broadcast_scraper import collect_broadcast_info
    try:
        collect_broadcast_info(limit=10)
        return True
    except Exception as error:
        _print(f"    Broadcast info error: {error}")
        return False


def collect_copa_brasil():
    """Collect Copa do Brasil matches from free sources (scrapers)."""
    _print("  Copa do Brasil (free sources)...")
    client = get_supabase()
    if not client:
        return False

    try:
        try:
            from collectors.copa_brasil_scraper import get_copa_brasil_matches
        except ImportError:
            from copa_brasil_scraper import get_copa_brasil_matches
        matches = get_copa_brasil_matches()
        if not matches:
            _print("    No Copa do Brasil matches found from scrapers")
            return True

        # Check if matches are Supabase-ready dicts or raw scraper output
        saved = 0
        for m in matches:
            if 'external_id' in m:
                # Already Supabase-ready (known data)
                ext_id = m.get('external_id')
                source = m.get('source')
                record = _sanitize_match_record(m)
                existing = client.table('matches').select('external_id').eq('external_id', ext_id).execute()
                if not existing.data:
                    client.table('matches').insert(record).execute()
                    saved += 1
                else:
                    # Protect manual entries (external_id >= 990000):
                    # Only update scores/status, never overwrite date/venue/teams
                    is_manual = source == 'manual' or (isinstance(ext_id, int) and 990000 <= ext_id < 991000)
                    if is_manual and source != 'manual':
                        # Collector trying to overwrite a manual entry — skip
                        _print(f"    Manual entry {ext_id} protected from overwrite")
                        continue
                    # Normal update
                    client.table('matches').update(record).eq('external_id', ext_id).execute()
                    saved += 1
            else:
                # Raw scraper output — convert to Supabase format
                h_name = m.get('home_team_name', '?')
                a_name = m.get('away_team_name', '?')
                comp_code = m.get('competition_code', 'COPA')
                comp_name = m.get('competition_name', 'Copa do Brasil')
                utc_date = m.get('utc_date')

                if not utc_date:
                    continue

                # Create a deterministic integer ID that matches the DB schema.
                ext_id = _deterministic_external_id(comp_code, h_name, a_name, utc_date[:10])

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
        return True
    except Exception as e:
        _print(f"    Copa do Brasil error: {e}")
        return False


if __name__ == '__main__':
    _print(f"Palmeiras Collector v2 — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    results = {
        'matches': collect_matches(),
        'standings': collect_standings(),
        'news': collect_news(),
        'copa_brasil': collect_copa_brasil(),
    }
    try:
        from collectors.score_resolver import resolve_scores
    except ImportError:
        from score_resolver import resolve_scores
    try:
        resolve_scores()
        results['score_resolver'] = True
    except Exception as error:
        _print(f"  Score resolver error: {error}")
        results['score_resolver'] = False
    results['broadcast_info'] = apply_broadcast_info()

    critical = ('matches', 'standings')
    failed_critical = [name for name in critical if not results.get(name)]
    warnings = [name for name, ok in results.items() if name not in critical and not ok]
    if warnings:
        _print(f"Done with warnings: {', '.join(warnings)}")
    if failed_critical:
        _print(f"FAILED critical collector stages: {', '.join(failed_critical)}")
        sys.exit(1)
    _print("Done!")
