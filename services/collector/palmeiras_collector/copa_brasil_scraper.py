"""
Playwright-based scraper for Copa do Brasil and other Brazilian competitions.

Uses browser automation to extract match data from JS-rendered pages:
- ge.globo Copa do Brasil schedule
- CBF Copa do Brasil fixtures
- Google search as fallback

This supplements football-data.org which only covers BSA + Libertadores.
"""
import json
import re
from datetime import datetime, timezone, timedelta

TEAM_ID = 1769
BR_TZ = timezone(timedelta(hours=-3))


def parse_date_br(text):
    """Parse Brazilian date formats to UTC ISO 8601."""
    text = text.strip()
    # Remove day of week
    text = re.sub(r'^(dom|seg|ter|qua|qui|sex|sab)[a-z]*,?\s*', '', text, flags=re.IGNORECASE)
    for fmt in ['%d/%m/%Y %H:%M', '%d/%m/%Y']:
        try:
            dt = datetime.strptime(text, fmt)
            br = dt.replace(tzinfo=timezone(timedelta(hours=-3)))
            return br.astimezone(timezone.utc).isoformat()
        except ValueError:
            continue
    return None


def detect_competition(text):
    """Detect competition from text."""
    t = text.lower()
    if 'libertadores' in t:
        return 'CLI'
    if 'copa do brasil' in t or 'copa-do-brasil' in t:
        return 'COPA'
    if 'brasileir' in t or 'série a' in t:
        return 'BSA'
    if 'paulista' in t:
        return 'PAU'
    if 'supercopa' in t:
        return 'SUP'
    if 'recopa' in t:
        return 'REC'
    return 'OTHER'


def scrape_ge_globo_copa_brasil():
    """
    Scrape Copa do Brasil matches from ge.globo.
    Returns list of match dicts.
    
    Usage from collector:
        from collectors.copa_brasil_scraper import scrape_ge_globo_copa_brasil
        matches = scrape_ge_globo_copa_brasil()
    """
    matches = []
    
    try:
        import requests
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        }
        
        # Try ge.globo Copa do Brasil page
        resp = requests.get(
            'https://ge.globo.com/futebol/copa-do-brasil/',
            headers=headers, timeout=30
        )
        
        # Extract embedded match data
        html = resp.text
        marker = 'window.byTeamScheduleTeamData = '
        start = html.find(marker)
        if start != -1:
            json_start = html.find('{', start)
            depth = 0
            i = json_start
            while i < len(html):
                if html[i] == '{':
                    depth += 1
                elif html[i] == '}':
                    depth -= 1
                    if depth == 0:
                        break
                i += 1
            
            data = json.loads(html[json_start:i+1])
            for m in data.get('matches', []):
                comp_name = m.get('championship', {}).get('name', '')
                comp_code = detect_competition(comp_name)
                
                if comp_code not in ('COPA',):
                    continue
                
                home = m.get('firstContestant', {})
                away = m.get('secondContestant', {})
                date_info = m.get('date', {})
                
                h_name = home.get('popularName', home.get('name', '?'))
                a_name = away.get('popularName', away.get('name', '?'))
                
                utc_date = None
                if isinstance(date_info, dict):
                    dt_str = date_info.get('dateTime', '')
                    if dt_str:
                        try:
                            utc_date = datetime.fromisoformat(
                                dt_str.replace('Z', '+00:00')
                            ).isoformat()
                        except ValueError:
                            pass
                
                matches.append({
                    'home_team_name': h_name,
                    'away_team_name': a_name,
                    'utc_date': utc_date,
                    'competition_code': 'COPA',
                    'competition_name': comp_name,
                    'status': 'SCHEDULED',
                    'source': 'ge.globo',
                })
    except Exception as e:
        print(f"    ge.globo Copa do Brasil error: {e}")
    
    return matches


def scrape_google_copa_brasil():
    """
    Fallback: scrape Copa do Brasil info from Google search.
    Uses requests (no Playwright needed for Google search).
    """
    matches = []
    
    try:
        import requests
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        }
        
        resp = requests.get(
            'https://www.google.com/search?q=palmeiras+copa+do+brasil+2026+jogos+datas',
            headers=headers, timeout=30
        )
        
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # Extract text mentioning Copa do Brasil
        for el in soup.find_all(string=lambda t: t and 'palmeiras' in t.lower() and 'copa' in t.lower()):
            text = el.strip()
            if len(text) < 20:
                continue
            
            # Look for date patterns
            date_matches = re.findall(r'(\d{1,2}/\d{1,2}/\d{4})', text)
            # Look for team names with "x" separator
            team_matches = re.findall(r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+x\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)', text)
            
            for teams in team_matches:
                home, away = teams
                date = date_matches[0] if date_matches else None
                matches.append({
                    'home_team_name': home.strip(),
                    'away_team_name': away.strip(),
                    'utc_date': parse_date_br(date) if date else None,
                    'competition_code': 'COPA',
                    'competition_name': 'Copa do Brasil 2026',
                    'status': 'SCHEDULED',
                    'source': 'google',
                })
    except Exception as e:
        print(f"    Google Copa do Brasil error: {e}")
    
    return matches


# ---- Known Copa do Brasil 2026 data (manually verified) ----
# Palmeiras enters in the 5th phase (round of 16 equivalent)
# Source: ge.globo + Google search results (March 29, 2026)
# Updated: July 19, 2026 — both fifth-phase results verified against the
# official Palmeiras match reports and CBF fixture dates.
#
# IMPORTANT: Entries with source='manual' are protected from collector overwrites.
# The collector skips update() for manual entries — only scores are updated live.
COPA_BRASIL_2026_KNOWN = [
    {
        'external_id': 990001,
        'utc_date': '2026-04-23T22:30:00+00:00',  # April 23 19:30 BRT (Thu)
        'home_team': json.dumps({'id': TEAM_ID, 'name': 'SE Palmeiras', 'shortName': 'Palmeiras', 'tla': 'PAL'}),
        'away_team': json.dumps({'id': 0, 'name': 'Jacuipense BA', 'shortName': 'Jacuipense', 'tla': 'JAC'}),
        'competition': json.dumps({'code': 'COPA', 'name': 'Copa do Brasil 2026', 'emblem': ''}),
        'season': json.dumps({'year': 2026}),
        'status': 'FINISHED',
        'matchday': 5,  # 5th phase
        'stage': '5TH_PHASE',
        'venue': 'Allianz Parque',
        'home_score': 3,
        'away_score': 0,
        'source': 'manual',
    },
    {
        'external_id': 990002,
        'utc_date': '2026-05-14T00:30:00+00:00',  # May 13 21:30 BRT (Wed)
        'home_team': json.dumps({'id': 0, 'name': 'Jacuipense BA', 'shortName': 'Jacuipense', 'tla': 'JAC'}),
        'away_team': json.dumps({'id': TEAM_ID, 'name': 'SE Palmeiras', 'shortName': 'Palmeiras', 'tla': 'PAL'}),
        'competition': json.dumps({'code': 'COPA', 'name': 'Copa do Brasil 2026', 'emblem': ''}),
        'season': json.dumps({'year': 2026}),
        'status': 'FINISHED',
        'matchday': 5,  # 5th phase
        'stage': '5TH_PHASE',
        'venue': 'Estádio do Café',
        'home_score': 1,
        'away_score': 4,
        'source': 'manual',
    },
]


def get_copa_brasil_matches():
    """
    Main entry point. Returns Copa do Brasil matches from:
    1. Live scraping (ge.globo)
    2. Google search fallback
    3. Known data (verified manually)
    
    Returns list of Supabase-ready match dicts.
    """
    # Try live scraping first
    live_matches = scrape_ge_globo_copa_brasil()
    if live_matches:
        return live_matches
    
    # Try Google fallback
    google_matches = scrape_google_copa_brasil()
    if google_matches:
        return google_matches
    
    # Return known data
    return COPA_BRASIL_2026_KNOWN


if __name__ == '__main__':
    print("Copa do Brasil scraper")
    print()
    
    print("  ge.globo scraping...")
    globo = scrape_ge_globo_copa_brasil()
    print(f"    Found: {len(globo)} matches")
    for m in globo:
        print(f"    {m['home_team_name']} vs {m['away_team_name']} ({m['utc_date']})")
    
    print()
    print("  Google search fallback...")
    google = scrape_google_copa_brasil()
    print(f"    Found: {len(google)} matches")
    for m in google:
        print(f"    {m['home_team_name']} vs {m['away_team_name']} ({m['utc_date']})")
    
    print()
    print("  Known data (fallback):")
    for m in COPA_BRASIL_2026_KNOWN:
        h = json.loads(m['home_team']).get('shortName', '?')
        a = json.loads(m['away_team']).get('shortName', '?')
        print(f"    {h} vs {a} ({m['utc_date'][:10]}) [{m['matchday']}]")
