"""
API-Football Collector — Supplements football-data.org with standings
not available in the free tier (notably Copa Libertadores).

API Key: 48158f75c594d982460e550dca67eb84
API Base: https://v3.football.api-sports.io

Usage:
    cd collectors
    python apifootball_collector.py

Requirements:
    pip install requests python-dotenv
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / '.env')

SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY')
API_FOOTBALL_KEY = os.environ.get('API_FOOTBALL_KEY', '48158f75c594d982460e550dca67eb84')
API_FOOTBALL_BASE = 'https://v3.football.api-sports.io'
HEADERS = {'x-apisports-key': API_FOOTBALL_KEY}

# League/season IDs for API-Football
# Libertadores = league ID 71 (Copa Libertadores)
# Copa do Brasil = league ID 26
# Brasileirão = league ID 71 (same as Libertadores? actually BSA is a different id)
# BSA (Brasileirão Série A) = league ID 71... let me check.
# Actually:
#   71 = Copa Libertadores
#   26 = Copa do Brasil
#   68 = Brasileirão Série A
#   126 = Brasileirão Série B
LIBERTADORES_LEAGUE_ID = 71
COPA_DO_BRASIL_LEAGUE_ID = 26
BSA_LEAGUE_ID = 68

# Current season (2025 or 2026 depending on current date)
CURRENT_SEASON = datetime.now(timezone.utc).year


def get_supabase():
    if not (SUPABASE_URL and SUPABASE_KEY):
        print("  Missing SUPABASE_URL or SUPABASE_KEY")
        return None
    from supabase import create_client
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def api_request(endpoint, params=None):
    """Make a request to API-Football."""
    try:
        resp = requests.get(
            f"{API_FOOTBALL_BASE}/{endpoint}",
            headers=HEADERS,
            params=params or {},
            timeout=30,
        )
        if resp.status_code == 429:
            print(f"  Rate limited by API-Football. Retry after: {resp.headers.get('x-ratelimit-reset')}")
            return None
        resp.raise_for_status()
        data = resp.json()
        if data.get('errors') and any(data['errors'].values()):
            print(f"  API errors: {data['errors']}")
        return data.get('response', [])
    except requests.exceptions.RequestException as e:
        print(f"  Request error: {e}")
        return None


def collect_libertadores_standings():
    """Fetch and save Libertadores standings via API-Football."""
    print("  Fetching Libertadores standings...")

    params = {
        'league': LIBERTADORES_LEAGUE_ID,
        'season': CURRENT_SEASON,
    }

    data = api_request('standings', params)
    if data is None:
        print("    Failed to fetch Libertadores standings")
        return

    # API-Football returns a list with one item per league
    # Structure: [{league: {...}, standings: [{stage: 'Regular Season', table: [...]}]}]
    all_tables = []
    for item in data:
        standings_list = item.get('standings', [])
        for stage_data in standings_list:
            table = stage_data.get('league', []) or stage_data.get('table', [])
            if table:
                all_tables.extend(table)

    if not all_tables:
        print("    No Libertadores standings found (season may not have started)")
        return

    print(f"    Found {len(all_tables)} teams in Libertadores")
    save_standings(all_tables, competition='CLI')


def collect_copa_brasil_standings():
    """Fetch Copa do Brasil standings/info via API-Football."""
    print("  Fetching Copa do Brasil info...")

    params = {
        'league': COPA_DO_BRASIL_LEAGUE_ID,
        'season': CURRENT_SEASON,
    }

    # Copa do Brasil doesn't always have a traditional standings table
    # since it's a knockout competition. Instead, collect match data.
    matches_data = api_request('fixtures', {
        'league': COPA_DO_BRASIL_LEAGUE_ID,
        'season': CURRENT_SEASON,
        'team': 1769,  # Palmeiras team ID
        'last': 10,
    })

    if matches_data:
        print(f"    Found {len(matches_data)} Copa do Brasil fixtures")
        save_copa_brasil_matches(matches_data)


def save_standings(table_entries, competition):
    """Save standings entries to Supabase."""
    client = get_supabase()
    if not client:
        return

    now = datetime.now(timezone.utc).isoformat()
    records = []
    for entry in table_entries:
        # API-Football structure varies; handle both formats
        team_data = entry.get('team', {}) or entry.get('team_id', {})
        if isinstance(team_data, dict):
            team_id = team_data.get('id')
            team_name = team_data.get('name', '')
            team_short = team_data.get('logo', '')  # URL, not short name
            team_crest = team_data.get('logo', '')
        else:
            team_id = team_data
            team_name = ''
            team_short = ''
            team_crest = ''

        # Handle rank/position
        position = entry.get('rank') or entry.get('position') or entry.get('0', {}).get('rank', 0)

        records.append({
            'competition': competition,
            'position': position,
            'team': json.dumps({
                'id': team_id,
                'name': team_name,
                'shortName': team_short,
                'crest': team_crest,
            }),
            'played_games': entry.get('games', {}).get('played') if isinstance(entry.get('games'), dict) else entry.get('games', 0),
            'won': entry.get('games', {}).get('win', {}).get('total') if isinstance(entry.get('games'), dict) else entry.get('win', 0),
            'drawn': entry.get('games', {}).get('draw', {}).get('total') if isinstance(entry.get('games'), dict) else entry.get('draw', 0),
            'lost': entry.get('games', {}).get('lose', {}).get('total') if isinstance(entry.get('games'), dict) else entry.get('lose', 0),
            'goals_for': entry.get('points', 0),  # may need adjustment
            'goals_against': 0,
            'goal_difference': entry.get('points', 0),  # will fix below
            'points': entry.get('points', 0),
            'updated_at': now,
        })

    # Fix goal stats if available
    for entry in all_tables:
        goals = entry.get('goals', {})
        if isinstance(goals, dict):
            gf = goals.get('for', {}).get('total') if isinstance(goals.get('for'), dict) else goals.get('for', 0)
            ga = goals.get('against', {}).get('total') if isinstance(goals.get('against'), dict) else goals.get('against', 0)
            gd = gf - ga
            # Find matching record
            team_data = entry.get('team', {})
            tid = team_data.get('id') if isinstance(team_data, dict) else team_data
            for rec in records:
                rec_team = json.loads(rec['team'])
                if rec_team.get('id') == tid:
                    rec['goals_for'] = gf or rec.get('goals_for', 0)
                    rec['goals_against'] = ga or rec.get('goals_against', 0)
                    rec['goal_difference'] = gd

    try:
        # Clear old data for this competition
        client.table('standings').delete().eq('competition', competition).execute()
        for record in records:
            client.table('standings').insert(record).execute()
        print(f"    Saved {len(records)} standings for {competition}")
    except Exception as e:
        print(f"    Error saving standings: {e}")


def save_copa_brasil_matches(fixtures):
    """Save Copa do Brasil fixtures to Supabase."""
    client = get_supabase()
    if not client:
        return

    now = datetime.now(timezone.utc).isoformat()
    records = []

    for fix in fixtures:
        league = fix.get('league', {})
        teams = fix.get('teams', {})
        home = teams.get('home', {})
        away = teams.get('away', {})
        goals = fix.get('goals', {})
        score = fix.get('score', {})

        records.append({
            'external_id': f"apifootball-copa-{fix.get('fixture', {}).get('id', '')}",
            'home_team': json.dumps({'id': home.get('id'), 'name': home.get('name'), 'crest': home.get('logo')}),
            'away_team': json.dumps({'id': away.get('id'), 'name': away.get('name'), 'crest': away.get('logo')}),
            'home_score': goals.get('home'),
            'away_score': goals.get('away'),
            'utc_date': fix.get('fixture', {}).get('date'),
            'status': _map_fixture_status(fix.get('fixture', {}).get('status', '')),
            'competition': json.dumps({'code': 'COPA', 'name': league.get('name', 'Copa do Brasil')}),
            'matchday': fix.get('league', {}).get('round'),
            'venue': None,
            'broadcast': None,
            'updated_at': now,
            'half_time_home': score.get('halftime', {}).get('home'),
            'half_time_away': score.get('halftime', {}).get('away'),
        })

    if records:
        try:
            client.table('matches').upsert(records, on_conflict='external_id').execute()
            print(f"    Saved {len(records)} Copa do Brasil matches")
        except Exception as e:
            print(f"    Error saving Copa do Brasil matches: {e}")


def _map_fixture_status(status_code):
    """Map API-Football fixture status to our format."""
    mapping = {
        'FT': 'FINISHED',
        'HT': 'HALFTIME',
        '1H': 'IN_PLAY',
        '2H': 'IN_PLAY',
        'ET': 'IN_PLAY',
        'P': 'IN_PLAY',
        'FT-P': 'FINISHED',
        'NS': 'SCHEDULED',
        'PST': 'POSTPONED',
        'CANC': 'CANCELLED',
    }
    return mapping.get(status_code, status_code or 'SCHEDULED')


def collect_bsa_standings_apifootball():
    """Fetch Brasileirão standings via API-Football (backup for football-data.org)."""
    print("  Fetching Brasileirão standings via API-Football...")

    params = {
        'league': BSA_LEAGUE_ID,
        'season': CURRENT_SEASON,
    }

    data = api_request('standings', params)
    if data is None:
        print("    Failed to fetch")
        return

    all_tables = []
    for item in data:
        for stage_data in item.get('standings', []):
            table = stage_data.get('league', []) or stage_data.get('table', [])
            if table:
                all_tables.extend(table)

    if all_tables:
        save_standings(all_tables, competition='BSA')
    else:
        print("    No BSA standings found")


if __name__ == '__main__':
    print(f"API-Football Collector — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  API Key: {API_FOOTBALL_KEY[:10]}...")
    print(f"  Season: {CURRENT_SEASON}")

    collect_libertadores_standings()
    collect_copa_brasil_standings()
    collect_bsa_standings_apifootball()

    print("Done!")
