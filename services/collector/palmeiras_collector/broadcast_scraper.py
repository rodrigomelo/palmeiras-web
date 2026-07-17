"""
Broadcast scraper — dynamically finds where Palmeiras matches are televised.

Primary source: ge.globo.com match pages (window.trv2.transmission.match.liveWatchSources)
Fallback: Static BROADCAST_MAP when ge.globo has no page yet (match too far out).

Usage:
    from collectors.broadcast_scraper import collect_broadcast_info
    updated = collect_broadcast_info()
"""

from __future__ import annotations

import json
import re
import os
import time
from datetime import datetime, timezone, timedelta
from typing import Optional, List

import requests

# ── Static fallback ────────────────────────────────────────────────────────
BROADCAST_MAP = {
    'BSA': 'Premiere / Globo',
    'COPA': 'SporTV / Premiere',
    'COPA_DO_BRASIL': 'SporTV / Premiere',
    'CLI': 'ESPN / Star+',
    'LIBERTADORES': 'ESPN / Star+',
    'COPA_LIBERTADORES': 'ESPN / Star+',
}

# Map ge.globo transmission names to clean display names.
# Only include real TV/streaming channels — skip Cartola, Ge TV, etc.
TRANSMISSION_NAME_MAP = {
    'sportv': 'SporTV',
    'Premiere': 'Premiere',
    'Globo': 'Globo',
    'globoplay': 'Globoplay',
    'ESPN': 'ESPN',
    'Star+': 'Star+',
    'Paramount+': 'Paramount+',
    'Amazon Prime': 'Prime Video',
    'Disney+': 'Disney+',
    'TNT': 'TNT Sports',
    'DAZN': 'DAZN',
    'NOW': 'NOW',
}

# Channels to exclude (not real broadcast channels)
EXCLUDED_CHANNELS = {'Cartola', 'Ge TV'}

# ── Supabase helper ────────────────────────────────────────────────────────

def _get_supabase():
    """Get Supabase client from environment variables."""
    url = os.environ.get('SUPABASE_URL', '')
    key = os.environ.get('SUPABASE_KEY', '')
    if not (url and key):
        return None
    from supabase import create_client
    return create_client(url, key)


# ── URL construction ───────────────────────────────────────────────────────

# Competition -> ge.globo URL slug
# Note: 'COPA' (Copa do Brasil) not included — ge.globo URLs differ per round/opponent
# and aren't predictable. Copa do Brasil falls back to BROADCAST_MAP.
COMPETITION_SLUGS = {
    'BSA': 'brasileirao-serie-a',
    'COPA_DO_BRASIL': 'copa-do-brasil',
    'COPA_LIBERTADORES': 'copa-libertadores',
    'LIBERTADORES': 'copa-libertadores',
    'CLI': 'copa-libertadores',
    'PAULISTA': 'campeonato-paulista',
}

# Brazilian states with ge.globo sub-sites (most common for Série A teams)
TEAM_STATE = {
    'flamengo': 'rj',
    'fluminense': 'rj',
    'vasco': 'rj',
    'botafogo': 'rj',
    'palmeiras': 'sp',
    'corinthians': 'sp',
    'são paulo': 'sp',
    'sao paulo': 'sp',
    'santos': 'sp',
    'bragantino': 'sp',
    'mirassol': 'sp',
    'gremio': 'rs',
    'grêmio': 'rs',
    'internacional': 'rs',
    'juventude': 'rs',
    'atletico-mg': 'mg',
    'atlético-mg': 'mg',
    'mineiro': 'mg',
    'cruzeiro': 'mg',
    'bahia': 'ba',
    'vitoria': 'ba',
    'vitória': 'ba',
    'fortaleza': 'ce',
    'ceará': 'ce',
    'ceara': 'ce',
    'coritiba': 'pr',
    'athletico-pr': 'pr',
    'paranaense': 'pr',
    'chapecoense': 'sc',
    'cuiabá': 'mt',
    'cuiaba': 'mt',
    'goiás': 'go',
    'goias': 'go',
    'sport': 'pe',
    'nautico': 'pe',
    'américa-mg': 'mg',
    'america-mg': 'mg',
    'atlético goianiense': 'go',
    'criciúma': 'sc',
    'criciuma': 'sc',
    'são bernardo': 'sp',
    'águia de marabá': 'pa',
    'tendil/diniz': 'mg',
    'jacuipense': 'ba',
    'anzanese': 'sp',
}

# Team name -> URL slug (lowercase, accented chars stripped)
TEAM_SLUGS = {
    'palmeiras': 'palmeiras',
    'flamengo': 'flamengo',
    'corinthians': 'corinthians',
    'são paulo': 'sao-paulo',
    'sao paulo': 'sao-paulo',
    'santos': 'santos',
    'botafogo': 'botafogo',
    'fluminense': 'fluminense',
    'vasco': 'vasco',
    'grêmio': 'gremio',
    'gremio': 'gremio',
    'internacional': 'internacional',
    'atlético-mg': 'atletico-mg',
    'atletico-mg': 'atletico-mg',
    'atlético': 'atletico-mg',
    'mineiro': 'atletico-mg',
    'cruzeiro': 'cruzeiro',
    'bahia': 'bahia',
    'fortaleza': 'fortaleza',
    'ceará': 'ceara',
    'ceara': 'ceara',
    'sport': 'sport',
    'chapecoense': 'chapecoense',
    'coritiba': 'coritiba',
    'athletico-pr': 'athletico-pr',
    'paranaense': 'athletico-pr',
    'juventude': 'juventude',
    'cuiabá': 'cuiaba',
    'cuiaba': 'cuiaba',
    'goiás': 'goias',
    'goias': 'goias',
    'américa-mg': 'america-mg',
    'america-mg': 'america-mg',
    'bragantino': 'bragantino',
    'mirassol': 'mirassol',
    'vitória': 'vitoria',
    'vitoria': 'vitoria',
    'criciúma': 'criciuma',
    'criciuma': 'criciuma',
    'náutico': 'nautico',
    'junior': 'junior',
    'junior fc': 'junior',
    'atlético goianiense': 'atletico-go',
    'jacuipense': 'jacuipense',
    'atlético goianiense': 'atletico-go',
}


def _team_slug(team_name: str) -> str:
    """Convert team name to URL slug for ge.globo URLs."""
    if not team_name:
        return ''
    name = team_name.strip().lower()
    # Direct lookup
    if name in TEAM_SLUGS:
        return TEAM_SLUGS[name]
    # Try short name (e.g. "SE Palmeiras" -> extract last word)
    parts = name.split()
    for part in reversed(parts):
        if part in TEAM_SLUGS:
            return TEAM_SLUGS[part]
    # Fallback: strip accents, replace spaces with hyphens
    slug = name.replace(' ', '-').replace('á', 'a').replace('é', 'e').replace('í', 'i')
    slug = slug.replace('ó', 'o').replace('ú', 'u').replace('ã', 'a').replace('õ', 'o')
    slug = slug.replace('ç', 'c').replace('ê', 'e').replace('ô', 'o').replace('â', 'a')
    return re.sub(r'[^a-z0-9-]', '', slug)


def _utc_to_brazil_date(utc_date_str: str) -> str:
    """Convert UTC date to Brazilian local date (BRT = UTC-3).

    ge.globo uses Brazilian local dates in URLs.
    A game at 2026-05-24T00:00:00Z is actually May 23rd in Brazil (21:00 BRT).
    """
    try:
        dt = datetime.fromisoformat(utc_date_str.replace('Z', '+00:00'))
        brt = timezone(timedelta(hours=-3))
        local_dt = dt.astimezone(brt)
        return local_dt.strftime('%d-%m-%Y')
    except (ValueError, AttributeError):
        return ''


def _get_team_state(team_name: str) -> str:
    """Get the Brazilian state prefix for a team's ge.globo URL."""
    name = team_name.strip().lower()
    if name in TEAM_STATE:
        return TEAM_STATE[name]
    # Try parts
    for part in name.split():
        if part in TEAM_STATE:
            return TEAM_STATE[part]
    return 'sp'  # default for Palmeiras-centric usage


def _build_match_urls(date_str: str, home_name: str, away_name: str, comp_code: str) -> List[str]:
    """Build candidate ge.globo match page URLs.

    Returns multiple URLs to try (different state prefixes).
    ge.globo pages can be under the home team's state or the away team's state,
    so we try both.
    """
    comp_slug = COMPETITION_SLUGS.get(comp_code)
    if not comp_slug:
        return []

    date_path = _utc_to_brazil_date(date_str)
    if not date_path:
        return []

    home_slug = _team_slug(home_name)
    away_slug = _team_slug(away_name)
    if not home_slug or not away_slug:
        return []

    # Try home team's state first (most common), then away team's state, then 'sp'
    states = []
    home_state = _get_team_state(home_name)
    away_state = _get_team_state(away_name)
    states.append(home_state)
    if away_state != home_state:
        states.append(away_state)
    if 'sp' not in states:
        states.append('sp')

    urls = []
    for state in states:
        url = f'https://ge.globo.com/{state}/futebol/{comp_slug}/jogo/{date_path}/{home_slug}-{away_slug}.ghtml'
        if url not in urls:
            urls.append(url)

    return urls


# ── Scraping ───────────────────────────────────────────────────────────────

_session = requests.Session()
_session.headers.update({
    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'pt-BR,pt;q=0.9,en;q=0.5',
})


def _scrape_broadcast_from_page(url: str) -> Optional[List[str]]:
    """Fetch a ge.globo match page and extract broadcast channel names.

    Returns:
        List of channel names (e.g. ['SporTV', 'Premiere', 'Globoplay']) or None.
    """
    for attempt in range(3):
        try:
            resp = _session.get(url, timeout=20, allow_redirects=True)
            if resp.status_code == 200:
                break
            if resp.status_code == 404:
                return None  # No point retrying a 404
        except requests.RequestException:
            if attempt == 2:
                return None
            time.sleep(2 ** attempt)
            continue
    else:
        return None

    # Reject tiny responses (error pages, redirects)
    if len(resp.text) < 1000:
        return None

    # Extract liveWatchSources JSON array
    # Allow trailing comma OR closing brace (handles last field in object)
    match = re.search(r'"liveWatchSources":\s*(\[.*?\])\s*[,}]', resp.text)
    if not match:
        return None

    try:
        sources = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None

    channels = []
    for source in sources:
        raw_name = source.get('name', '')
        clean_name = TRANSMISSION_NAME_MAP.get(raw_name, raw_name)
        # Skip non-broadcast sources
        if clean_name in EXCLUDED_CHANNELS:
            continue
        if clean_name not in channels:
            channels.append(clean_name)

    return channels if channels else None


def _format_broadcast(channels: List[str]) -> str:
    """Format channel list into display string like 'Premiere / SporTV'."""
    if not channels:
        return ''
    return ' / '.join(channels)


# ── Main collection logic ─────────────────────────────────────────────────

def _print(msg: str):
    """Print with timestamp."""
    ts = datetime.now().strftime('%H:%M:%S')
    print(f'[{ts}] {msg}', flush=True)


def collect_broadcast_info(limit: int = 10) -> int:
    """Scrape broadcast info for upcoming Palmeiras matches.

    Strategy:
    1. Fetch upcoming SCHEDULED/TIMED matches from Supabase
    2. For each, build ge.globo match URLs (multiple candidates) and try to scrape
    3. If scraping fails (404, no data), fall back to static BROADCAST_MAP
    4. Update Supabase with the best available broadcast string

    Args:
        limit: Max number of upcoming matches to process.

    Returns:
        Number of matches updated.
    """
    _print('📺 Collecting broadcast info...')
    client = _get_supabase()
    if not client:
        raise RuntimeError('No Supabase client')

    # Fetch upcoming matches
    try:
        result = client.table('matches').select(
            'external_id, home_team, away_team, utc_date, status, competition, broadcast'
        ).in_('status', ['SCHEDULED', 'TIMED']).order('utc_date').limit(limit).execute()
        matches = result.data
    except Exception as e:
        _print(f'  Error fetching matches: {e}')
        raise

    if not matches:
        _print('  No upcoming matches found')
        return 0

    _print(f'  Processing {len(matches)} matches...')
    updated = 0
    failed_updates = 0

    for match in matches:
        ext_id = match.get('external_id')
        if not ext_id:
            continue

        # Parse team names
        home_data = json.loads(match.get('home_team') or '{}')
        away_data = json.loads(match.get('away_team') or '{}')
        home_name = home_data.get('shortName') or home_data.get('name', '')
        away_name = away_data.get('shortName') or away_data.get('name', '')

        # Parse competition code
        comp_data = json.loads(match.get('competition') or '{}')
        comp_code = comp_data.get('code', '')

        # Try dynamic scrape with multiple URL candidates
        broadcast = None
        scraped = False
        urls = _build_match_urls(
            match.get('utc_date', ''), home_name, away_name, comp_code
        )

        for url in urls:
            channels = _scrape_broadcast_from_page(url)
            if channels:
                broadcast = _format_broadcast(channels)
                scraped = True
                break
            time.sleep(0.5)  # brief pause between URL attempts

        # Fallback to static map
        if not broadcast:
            broadcast = BROADCAST_MAP.get(comp_code, '')

        # Only update if we have something new/different
        current = match.get('broadcast') or ''
        if broadcast and broadcast != current:
            try:
                client.table('matches').update(
                    {'broadcast': broadcast}
                ).eq('external_id', ext_id).execute()
                updated += 1
                if scraped:
                    _print(f'  ✅ {home_name} x {away_name}: {broadcast} (ge.globo)')
                else:
                    _print(f'  🔄 {home_name} x {away_name}: {broadcast} (static fallback)')
            except Exception as e:
                failed_updates += 1
                _print(f'  ❌ Error updating {home_name} x {away_name}: {e}')
        elif not broadcast and not current:
            _print(f'  ⚪ {home_name} x {away_name}: no broadcast info available')

        # Be polite — don't hammer ge.globo between matches
        time.sleep(1.5)

    _print(f'  Updated {updated} matches')
    if failed_updates:
        raise RuntimeError(f'{failed_updates} broadcast update(s) failed')
    return updated


# ── CLI entry point ────────────────────────────────────────────────────────

if __name__ == '__main__':
    import sys
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
    count = collect_broadcast_info(limit=int(sys.argv[1]) if len(sys.argv) > 1 else 10)
    print(f'\nTotal updated: {count}')
