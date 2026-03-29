"""
Scraper for Palmeiras matches from ge.globo — covers all competitions.
football-data.org free tier only covers BSA + Libertadores.
This scraper fills the gap for Copa do Brasil, Paulista, Supercopa, Recopa.
"""
import json
import re
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup
import requests

TEAM_ID = 1769
PALMEIRAS_HOME = "Allianz Parque"

# Map ge.globo competition names to our codes
COMP_MAP = {
    'brasileirão': 'BSA',
    'serie a': 'BSA',
    'libertadores': 'CLI',
    'copa do brasil': 'COPA',
    'paulista': 'PAU',
    'supercopa': 'SUP',
    'recopa': 'REC',
}


def detect_comp(text):
    """Detect competition code from text."""
    text_lower = text.lower()
    for key, code in COMP_MAP.items():
        if key in text_lower:
            return code
    return 'OTHER'


def parse_date(date_str):
    """Parse ge.globo date format to ISO 8601 UTC."""
    try:
        # ge.globo uses formats like "dom, 20/04/2025 16:00" or "20/04/2025"
        clean = date_str.strip()
        # Remove day of week
        clean = re.sub(r'^(dom|seg|ter|qua|qui|sex|sab)[a-z]*,\s*', '', clean, flags=re.IGNORECASE)
        # Try with time
        for fmt in ['%d/%m/%Y %H:%M', '%d/%m/%Y']:
            try:
                dt = datetime.strptime(clean, fmt)
                br_tz = timezone(timedelta(hours=-3))
                dt = dt.replace(tzinfo=br_tz)
                return dt.astimezone(timezone.utc).isoformat()
            except ValueError:
                continue
    except Exception:
        pass
    return None


def scrape_palmeiras_matches():
    """Scrape Palmeiras schedule from ge.globo."""
    matches = []
    urls = [
        'https://ge.globo.com/futebol/times/palmeiras/',
    ]

    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        'Accept-Language': 'pt-BR,pt;q=0.9',
    }

    for url in urls:
        try:
            resp = requests.get(url, headers=headers, timeout=30)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, 'html.parser')

            # Find match schedule elements — ge.globo uses various patterns
            for el in soup.select('[class*="jogo"], [class*="match"], [class*="agenda"]'):
                title_el = el.select_one('a[title], [class*="title"], [class*="nome"]')
                date_el = el.select_one('[class*="data"], [class*="date"], time')
                comp_el = el.select_one('[class*="competicao"], [class*="campeonato"], [class*="tournament"]')

                if not title_el:
                    continue

                title = title_el.get_text(strip=True) or title_el.get('title', '')
                date_text = date_el.get_text(strip=True) if date_el else ''
                comp_text = comp_el.get_text(strip=True) if comp_el else ''

                if not title or 'palmeiras' not in title.lower():
                    continue

                # Parse teams from title like "Palmeiras x Corinthians"
                parts = re.split(r'\s+x\s+|\s+vs\s+', title, flags=re.IGNORECASE)
                if len(parts) != 2:
                    continue

                home_name = parts[0].strip()
                away_name = parts[1].strip()
                is_home = 'palmeiras' in home_name.lower()

                utc_date = parse_date(date_text) if date_text else None
                comp_code = detect_comp(comp_text or title)

                matches.append({
                    'home_team_name': home_name,
                    'away_team_name': away_name,
                    'is_home': is_home,
                    'utc_date': utc_date,
                    'competition_code': comp_code,
                    'competition_name': comp_text,
                    'source': 'ge.globo',
                    'status': 'SCHEDULED',
                })
        except Exception as e:
            print(f"    ge.globo scraper error: {e}")

    return matches


def scrape_cbf_copa_brasil():
    """Try to scrape Copa do Brasil fixtures from CBF."""
    matches = []
    try:
        resp = requests.get(
            'https://www.cbf.com.br/futebol-brasileiro-competicoes/copa-brasil-masculino/2026',
            headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'},
            timeout=30,
        )
        if resp.status_code != 200:
            return matches

        soup = BeautifulSoup(resp.text, 'html.parser')
        for row in soup.select('table tr, [class*="jogo"]'):
            text = row.get_text()
            if 'palmeiras' not in text.lower():
                continue
            # Extract match info from table row
            cols = row.select('td')
            if len(cols) >= 3:
                matches.append({
                    'raw': text.strip()[:200],
                    'source': 'cbf.com.br',
                    'competition_code': 'COPA',
                    'competition_name': 'Copa do Brasil',
                })
    except Exception as e:
        print(f"    CBF scraper error: {e}")

    return matches


if __name__ == '__main__':
    print("Scraping ge.globo for Palmeiras matches...")
    globo_matches = scrape_palmeiras_matches()
    print(f"  Found {len(globo_matches)} matches")
    for m in globo_matches:
        print(f"  {m['competition_code']}: {m['home_team_name']} vs {m['away_team_name']}")

    print("\nScraping CBF for Copa do Brasil...")
    cbf_matches = scrape_cbf_copa_brasil()
    print(f"  Found {len(cbf_matches)} matches")
