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
from collections import deque
from io import BytesIO
from pathlib import Path
from threading import get_ident

from PIL import Image, UnidentifiedImageError

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


def _remove_edge_background(image):
    """Remove only pale pixels connected to the image edge.

    CBF publishes club crests as JPEGs on a white or light-gray canvas. A
    simple color key would also erase white lettering inside the badge, so the
    traversal deliberately starts at the outer edge and stops at colored or
    dark badge pixels.
    """
    image = image.convert("RGBA")
    width, height = image.size
    pixels = image.load()
    visited = bytearray(width * height)
    pending = deque()

    def is_background(x, y):
        red, green, blue, alpha = pixels[x, y]
        if alpha == 0:
            return True
        darkest = min(red, green, blue)
        spread = max(red, green, blue) - darkest
        return darkest >= 208 and spread <= 52

    def add(x, y):
        index = y * width + x
        if visited[index] or not is_background(x, y):
            return
        visited[index] = 1
        pending.append((x, y))

    for x in range(width):
        add(x, 0)
        add(x, height - 1)
    for y in range(height):
        add(0, y)
        add(width - 1, y)

    while pending:
        x, y = pending.popleft()
        red, green, blue, alpha = pixels[x, y]
        darkest = min(red, green, blue)
        # Fully remove the CBF canvas and retain a short antialiased transition
        # at badge edges so outlines remain clean on the green hero surface.
        edge_alpha = 0 if darkest >= 238 else min(255, (238 - darkest) * 9)
        pixels[x, y] = (red, green, blue, min(alpha, edge_alpha))
        if x:
            add(x - 1, y)
        if x + 1 < width:
            add(x + 1, y)
        if y:
            add(x, y - 1)
        if y + 1 < height:
            add(x, y + 1)

    return image


def normalize_crest_image(content, *, remove_edge_background=False):
    """Decode an upstream badge and return a verified, browser-safe PNG."""
    if not content or len(content) > 4 * 1024 * 1024:
        raise ValueError("invalid crest size")
    try:
        with Image.open(BytesIO(content)) as source:
            source.load()
            if source.width > 2048 or source.height > 2048:
                raise ValueError("invalid crest dimensions")
            image = source.convert("RGBA")
    except (UnidentifiedImageError, OSError) as error:
        raise ValueError("invalid crest image") from error

    if remove_edge_background:
        image = _remove_edge_background(image)

    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()


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
            # Decode and re-encode instead of trusting the extension or MIME
            # type supplied upstream. CBF JPEGs receive a transparent canvas.
            content_type = resp.headers.get('content-type', '')
            if 'image' in content_type or resp.content[:4] == b'\x89PNG':
                is_cbf_jpeg = (
                    'jpeg' in content_type
                    or str(url).lower().endswith(('.jpg', '.jpeg'))
                    or 'conteudo.cbf.com.br/clubes/' in str(url).lower()
                )
                normalized = normalize_crest_image(
                    resp.content,
                    remove_edge_background=is_cbf_jpeg,
                )
                CRESTS_DIR.mkdir(parents=True, exist_ok=True)
                temporary_path = local_path.with_name(f'.{team_id}.{os.getpid()}.{get_ident()}.tmp')
                temporary_path.write_bytes(normalized)
                os.replace(temporary_path, local_path)
                print(f'    Saved crest: {team_id} ({len(normalized)} bytes)')
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
