"""
Scraper for Palmeiras matches NOT covered by football-data.org free tier.

football-data.org covers: BSA (Brasileirão), CLI (Libertadores)
This covers: COPA (Copa do Brasil), PAU (Paulista), SUP (Supercopa), REC (Recopa)

Uses Wikipedia + ge.globo as free sources.
"""
import json
import re
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup
import requests

TEAM_ID = 1769
BR_TZ = timezone(timedelta(hours=-3))
NOW = datetime.now(timezone.utc)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
    'Accept-Language': 'pt-BR,pt;q=0.9',
}


def fetch_wikipedia_copa_brasil():
    """Scrape Copa do Brasil matches from Wikipedia."""
    matches = []
    try:
        resp = requests.get(
            'https://pt.wikipedia.org/wiki/Copa_do_Brasil_de_Futebol_de_2026',
            headers=HEADERS, timeout=30
        )
        if resp.status_code != 200:
            return matches

        soup = BeautifulSoup(resp.text, 'html.parser')
        # Find match tables
        for table in soup.select('table.wikitable'):
            rows = table.select('tr')
            for i, row in enumerate(rows):
                text = row.get_text().lower()
                if 'palmeiras' not in text:
                    continue
                cells = [td.get_text(strip=True) for td in row.select('td, th')]
                if len(cells) < 3:
                    continue
                # Try to extract match info
                for cell in cells:
                    # Look for patterns like "Palmeiras x Jacuipense" or dates
                    if 'palmeiras' in cell.lower():
                        for sep in [' x ', ' × ', ' vs ']:
                            if sep in cell:
                                parts = cell.split(sep)
                                if len(parts) == 2:
                                    matches.append({
                                        'home': parts[0].strip(),
                                        'away': parts[1].strip(),
                                        'competition': 'Copa do Brasil',
                                        'source': 'wikipedia',
                                    })
                                break
    except Exception as e:
        print(f"    Wikipedia Copa do Brasil error: {e}")
    return matches


def fetch_ge_globo_schedule():
    """Fetch Palmeiras schedule from ge.globo embedded data."""
    matches = []
    try:
        resp = requests.get(
            'https://ge.globo.com/futebol/times/palmeiras/agenda-de-jogos-do-palmeiras/',
            headers=HEADERS, timeout=30
        )
        if resp.status_code != 200:
            return matches

        html = resp.text
        # Extract window.byTeamScheduleTeamData JSON
        marker = 'window.byTeamScheduleTeamData = '
        start = html.find(marker)
        if start == -1:
            return matches

        json_start = html.find('{', start)
        depth = 0
        i = json_start
        while i < len(html):
            if html[i] == '{': depth += 1
            elif html[i] == '}':
                depth -= 1
                if depth == 0: break
            i += 1

        data = json.loads(html[json_start:i+1])
        for m in data.get('matches', []):
            home = m.get('firstContestant', {})
            away = m.get('secondContestant', {})
            comp = m.get('championship', {})
            date_info = m.get('date', {})

            h_name = home.get('popularName', home.get('name', '?'))
            a_name = away.get('popularName', away.get('name', '?'))
            comp_name = comp.get('name', '?')

            utc_date = None
            if isinstance(date_info, dict):
                dt_str = date_info.get('dateTime', '')
                if dt_str:
                    try:
                        dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
                        utc_date = dt.isoformat()
                    except ValueError:
                        pass

            matches.append({
                'home': h_name,
                'away': a_name,
                'competition': comp_name,
                'utc_date': utc_date,
                'source': 'ge.globo',
            })
    except Exception as e:
        print(f"    ge.globo schedule error: {e}")
    return matches


def scrape_all():
    """Run all scrapers and return deduplicated matches."""
    all_matches = []

    print("  Scraping Wikipedia (Copa do Brasil)...")
    wiki = fetch_wikipedia_copa_brasil()
    print(f"    Found {len(wiki)} matches")
    all_matches.extend(wiki)

    print("  Scraping ge.globo (all competitions)...")
    globo = fetch_ge_globo_schedule()
    print(f"    Found {len(globo)} matches")
    all_matches.extend(globo)

    return all_matches


if __name__ == '__main__':
    matches = scrape_all()
    print(f"\nTotal: {len(matches)} matches from free sources")
    for m in matches:
        d = m.get('utc_date', 'no date')[:16] if m.get('utc_date') else 'no date'
        print(f"  {m['competition']}: {m['home']} vs {m['away']} ({d}) [{m['source']}]")
