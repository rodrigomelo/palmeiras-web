"""
Selenium collector for JS-rendered football sites (SofaScore / FlashScore).

This module complements the existing football-data.org collectors by scraping
sites that require JavaScript rendering.

Usage:
    cd collectors
    python sofascore_collector.py

Requirements:
    pip install selenium webdriver-manager
    Also requires Chrome or Chromium installed.
"""
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

load_dotenv(Path(__file__).parent.parent / '.env')

SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY')


def get_supabase():
    if not (SUPABASE_URL and SUPABASE_KEY):
        print("  Missing SUPABASE_URL or SUPABASE_KEY")
        return None
    from supabase import create_client
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def get_driver(headless=True):
    """Create a headless Chrome driver."""
    if not SELENIUM_AVAILABLE:
        raise RuntimeError("selenium not installed. Run: pip install selenium webdriver-manager")

    options = Options()
    if headless:
        options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

    try:
        from webdriver_manager.chrome import ChromeDriverManager
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
    except Exception:
        # Fallback: try system chromedriver
        driver = webdriver.Chrome(options=options)

    driver.set_page_load_timeout(30)
    return driver


def scrape_sofascore_palmeiras():
    """
    Scrape Palmeiras matches from SofaScore.
    Returns a list of match dicts.
    """
    driver = None
    matches = []

    try:
        print("  Launching Chrome...")
        driver = get_driver(headless=True)
        print("  Opening SofaScore Palmeiras page...")
        driver.get('https://www.sofascore.com/football/brazil/brasileirao-serie-a/results')

        # Wait for matches to load
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, '.sc-1aac5d31-2, .event-cell-container'))
        )
        time.sleep(3)  # Extra wait for JS to finish

        # Find match elements
        # SofaScore uses various selectors; try multiple patterns
        selectors = [
            '.event-cell-container',
            '[class*="eventCell"]',
            '.sc-1aac5d31-2',
            'div[aria-label*="match"]',
        ]

        elements = []
        for sel in selectors:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, sel)
                if elements:
                    print(f"    Found {len(elements)} elements with selector: {sel}")
                    break
            except Exception:
                continue

        # Also try getting JSON data embedded in page
        page_source = driver.page_source
        # Look for __NEXT_DATA__ or similar embedded JSON
        import re
        next_data_match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', page_source, re.DOTALL)
        if next_data_match:
            try:
                next_data = json.loads(next_data_match.group(1))
                # Navigate the embedded structure
                props = next_data.get('props', {}).get('pageProps', {})
                events = props.get('events', [])
                if events:
                    print(f"    Found {len(events)} events in __NEXT_DATA__")
                    for evt in events:
                        matches.append(_parse_sofascore_event(evt))
            except (json.JSONDecodeError, KeyError) as e:
                print(f"    __NEXT_DATA__ parse error: {e}")

        # Try standard HTML parsing as fallback
        if not matches:
            print("    Trying HTML parsing fallback...")
            matches.extend(_scrape_sofascore_html(driver))

        print(f"    Total matches scraped: {len(matches)}")

    except Exception as e:
        print(f"  Error: {e}")
    finally:
        if driver:
            driver.quit()

    return matches


def _parse_sofascore_event(evt):
    """Parse a SofaScore event from embedded JSON."""
    try:
        home = evt.get('homeTeam', {})
        away = evt.get('awayTeam', {})
        start_time = evt.get('startTimestamp')
        status = evt.get('status', {}).get('description', '')

        return {
            'external_id': f"sofascore-{evt.get('id', '')}",
            'home_team': json.dumps({'id': home.get('id'), 'name': home.get('name'), 'shortName': home.get('shortName'), 'crest': home.get('logo')}),
            'away_team': json.dumps({'id': away.get('id'), 'name': away.get('name'), 'shortName': away.get('shortName'), 'crest': away.get('logo')}),
            'utc_date': datetime.fromtimestamp(start_time, tz=timezone.utc).isoformat() if start_time else None,
            'status': _map_sofascore_status(status),
            'home_score': evt.get('homeScore', {}).get('current'),
            'away_score': evt.get('awayScore', {}).get('current'),
            'competition': json.dumps({'code': 'BSA', 'name': 'Brasileirão Série A'}),
            'matchday': evt.get('roundInfo', {}).get('round'),
            'venue': None,
            'broadcast': None,
            'source': 'sofascore',
        }
    except Exception as e:
        print(f"    Event parse error: {e}")
        return None


def _map_sofascore_status(status_str):
    """Map SofaScore status to our status format."""
    mapping = {
        'Finished': 'FINISHED',
        'Half Time': 'HALFTIME',
        '1st Half': 'IN_PLAY',
        '2nd Half': 'IN_PLAY',
        'Postponed': 'POSTPONED',
        'Canceled': 'CANCELLED',
        'Scheduled': 'SCHEDULED',
    }
    return mapping.get(status_str, status_str.upper())


def _scrape_sofascore_html(driver):
    """Fallback: scrape SofaScore using BeautifulSoup on the rendered HTML."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return []

    soup = BeautifulSoup(driver.page_source, 'html.parser')
    matches = []

    # Try to find match cards
    cards = soup.select('[class*="matchCard"], [class*="eventCard"]')
    for card in cards:
        try:
            home_name = card.select_one('[class*="home"] [class*="name"], [class*="homeTeam"]')
            away_name = card.select_one('[class*="away"] [class*="name"], [class*="awayTeam"]')
            score_el = card.select_one('[class*="scoreboard"], [class*="result"]')
            date_el = card.select_one('[class*="date"], [class*="time"]')

            if home_name and away_name:
                matches.append({
                    'external_id': f"sofascore-html-{hash(str(card))}",
                    'home_team': json.dumps({'name': home_name.get_text(strip=True)}),
                    'away_team': json.dumps({'name': away_name.get_text(strip=True)}),
                    'utc_date': date_el.get_text(strip=True) if date_el else None,
                    'status': 'FINISHED' if score_el else 'SCHEDULED',
                    'source': 'sofascore-html',
                })
        except Exception:
            continue

    return matches


def save_to_supabase(matches):
    """Save scraped matches to Supabase."""
    client = get_supabase()
    if not client or not matches:
        return

    now = datetime.now(timezone.utc).isoformat()
    records = []
    for m in matches:
        if not m:
            continue
        record = {
            'external_id': m.get('external_id', ''),
            'home_team': m.get('home_team', '{}'),
            'away_team': m.get('away_team', '{}'),
            'home_score': m.get('home_score'),
            'away_score': m.get('away_score'),
            'utc_date': m.get('utc_date'),
            'status': m.get('status', 'SCHEDULED'),
            'competition': m.get('competition', '{}'),
            'matchday': m.get('matchday'),
            'venue': m.get('venue'),
            'broadcast': m.get('broadcast'),
            'updated_at': now,
            'half_time_home': m.get('half_time_home'),
            'half_time_away': m.get('half_time_away'),
            'source': m.get('source', 'sofascore'),
        }
        records.append(record)

    if not records:
        print("  No valid records to save")
        return

    try:
        client.table('matches').upsert(records, on_conflict='external_id').execute()
        print(f"  Saved {len(records)} matches to Supabase")
    except Exception as e:
        print(f"  Supabase save error: {e}")


if __name__ == '__main__':
    print(f"Selenium SofaScore Collector — {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    if not SELENIUM_AVAILABLE:
        print("ERROR: selenium not installed.")
        print("  Fix: pip install selenium webdriver-manager")
        sys.exit(1)

    print("  Scraping SofaScore...")
    matches = scrape_sofascore_palmeiras()
    if matches:
        save_to_supabase(matches)
    else:
        print("  No matches scraped (site may have changed structure)")
    print("Done!")
