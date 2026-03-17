"""
Palmeiras Cache - Scheduled data fetcher
"""
import os
import json
import time
import requests

API_KEY = os.environ.get('FOOTBALL_API_KEY', 'eca8b30bb5c34fcfa80ec28ceedf84a0')
HEADERS = {'X-Auth-Token': API_KEY}

CACHE_FILE = '/tmp/palmeiras_cache.json'


def fetch_and_cache():
    """Fetch all data and save to cache file"""
    cache_data = {
        'timestamp': time.time(),
        'matches': [],
        'standings': None,
        'news': []
    }
    
    # Fetch matches
    try:
        r = requests.get(
            'https://api.football-data.org/v4/teams/1769/matches',
            headers=HEADERS,
            params={'limit': 50},
            timeout=10
        )
        if r.status_code == 200:
            cache_data['matches'] = r.json()
    except Exception as e:
        print(f"Error fetching matches: {e}")
    
    # Fetch standings
    try:
        r = requests.get(
            'https://api.football-data.org/v4/competitions/BSA/standings',
            headers=HEADERS,
            timeout=10
        )
        if r.status_code == 200:
            cache_data['standings'] = r.json()
    except Exception as e:
        print(f"Error fetching standings: {e}")
    
    # Save to file
    with open(CACHE_FILE, 'w') as f:
        json.dump(cache_data, f)
    
    return cache_data


def get_cached():
    """Get cached data"""
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, 'r') as f:
            return json.load(f)
    return None


# For Vercel serverless - fetch on demand if cache old
def ensure_fresh_cache(max_age_seconds=1800):
    """Ensure cache exists and is fresh (30 min default)"""
    data = get_cached()
    if data is None:
        return fetch_and_cache()
    
    age = time.time() - data.get('timestamp', 0)
    if age > max_age_seconds:
        return fetch_and_cache()
    
    return data
