"""
Crest Manager — Download and cache team logos locally.

Usage:
    from crest_manager import get_or_download_crest
    crest_url = get_or_download_crest(team_id, original_url)
"""
import os
import json
import hashlib
import requests
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
CRESTS_DIR = PROJECT_ROOT / 'apps' / 'web' / 'static' / 'crests'
MANIFEST_PATH = CRESTS_DIR / 'manifest.json'

# Known crest URLs for teams without football-data.org crests
FALLBACK_CRESTS = {
    1769: 'https://crests.football-data.org/1769.png',  # Palmeiras (override gstatic)
    # Add more fallbacks here as needed
}

# Teams known to have no crest available anywhere
NO_CREST = set()


def load_manifest():
    if MANIFEST_PATH.exists():
        with open(MANIFEST_PATH) as f:
            return json.load(f)
    return {}


def save_manifest(manifest):
    CRESTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(MANIFEST_PATH, 'w') as f:
        json.dump(manifest, f, indent=2)


def get_or_download_crest(team_id, original_url=None):
    """
    Return local crest path for a team. Downloads if not cached.
    Returns: '/static/crests/{team_id}.png' or None if no crest available.
    """
    if not team_id:
        return None

    team_id = int(team_id)
    local_filename = f'{team_id}.png'
    local_path = CRESTS_DIR / local_filename

    # Already cached locally
    if local_path.exists():
        return f'/static/crests/{local_filename}'

    # Known to have no crest
    if team_id in NO_CREST:
        return None

    # Determine URL to fetch
    url = FALLBACK_CRESTS.get(team_id) or original_url
    if not url:
        # Try football-data.org standard URL
        url = f'https://crests.football-data.org/{team_id}.png'

    # Download
    try:
        resp = requests.get(url, timeout=15, headers={
            'User-Agent': 'PalmeirasDashboard/1.0'
        })
        if resp.status_code == 200 and len(resp.content) > 100:
            # Verify it's actually an image (PNG or SVG)
            content_type = resp.headers.get('content-type', '')
            if 'image' in content_type or resp.content[:4] == b'\x89PNG' or b'<svg' in resp.content[:200].lower():
                local_path.write_bytes(resp.content)
                print(f'    Saved crest: {team_id} ({len(resp.content)} bytes)')
                return f'/static/crests/{local_filename}'
            else:
                print(f'    Not an image: {team_id} (content-type: {content_type})')
        else:
            print(f'    No crest for {team_id} (HTTP {resp.status_code})')
    except Exception as e:
        print(f'    Error downloading crest {team_id}: {e}')

    # Mark as no crest to avoid retrying
    NO_CREST.add(team_id)
    return None


def cache_all_crests(matches):
    """Process a list of matches and cache all team crests."""
    CRESTS_DIR.mkdir(parents=True, exist_ok=True)

    teams_seen = set()
    for m in matches:
        home = m.get('homeTeam', {})
        away = m.get('awayTeam', {})
        for team in (home, away):
            tid = team.get('id')
            if tid and tid not in teams_seen:
                teams_seen.add(tid)
                crest_url = team.get('crest', '')
                local = get_or_download_crest(tid, crest_url)
                if local:
                    team['crest'] = local
                elif tid in NO_CREST:
                    team['crest'] = None

    return matches
