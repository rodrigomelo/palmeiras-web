"""
Supabase client factory.
Shared across all API functions.
"""
import os
import json

try:
    from supabase import create_client
    HAS_SUPABASE = True
except ImportError:
    HAS_SUPABASE = False

SUPABASE_URL = os.environ.get('SUPABASE_URL', '')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY', '')


def get_supabase():
    if not (SUPABASE_URL and SUPABASE_KEY and HAS_SUPABASE):
        return None
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def parse_json(val):
    """Parse JSON string or return dict."""
    if isinstance(val, str):
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return {}
    return val if isinstance(val, dict) else {}
