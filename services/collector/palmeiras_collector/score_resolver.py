"""
Score Resolver — backfills results for past matches missing final scores.

Part of the data collection pipeline. Runs after fixture collectors to close
the loop: fixtures come in as SCHEDULED → match happens → score resolver
finds the result and updates the database.

Design:
  - Idempotent: safe to run multiple times, only touches unresolved matches
  - Multi-source with graceful fallback: API → Google → skip
  - Rate-limited: respectful delays between external calls
  - Validates every result before writing
  - Logs clearly for debugging

Usage (standalone):
    python collectors/score_resolver.py

Usage (from collector pipeline):
    from collectors.score_resolver import resolve_scores
    resolve_scores()
"""
import json
import html
import os
import re
import time
import unicodedata
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[3] / '.env')
except ImportError:
    pass

SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY')
FOOTBALL_API_KEY = os.environ.get('FOOTBALL_API_KEY')
TEAM_ID = 1769
API_BASE = 'https://api.football-data.org/v4'

SILENT = False
GRACE_HOURS = 2  # minimum hours past kickoff before resolving
MAX_SCORE = 20   # sanity upper bound for individual team score
REQUEST_DELAY = 1.5  # seconds between external requests (rate limiting)


def _print(*args, **kwargs):
    if not SILENT:
        print(*args, **kwargs)


def _get_supabase():
    if not (SUPABASE_URL and SUPABASE_KEY):
        _print("    No Supabase credentials")
        return None
    from supabase import create_client
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def _parse_team(match, side):
    """Extract team name from a match record."""
    raw = match.get(side, '{}')
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {'name': '?', 'shortName': '?'}
    return raw if isinstance(raw, dict) else {}


def _parse_json_field(match, field):
    """Extract a JSON object field from a match record."""
    raw = match.get(field, '{}')
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {}
    return raw if isinstance(raw, dict) else {}


def _parse_match_datetime(match):
    """Parse a match UTC date from the database record."""
    raw = match.get('utc_date')
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace('Z', '+00:00'))
    except (TypeError, ValueError):
        return None


def _normalize_text(value):
    """Normalize text for resilient Portuguese/accent-insensitive matching."""
    text = html.unescape(str(value or '')).lower()
    text = unicodedata.normalize('NFKD', text)
    return ''.join(ch for ch in text if not unicodedata.combining(ch))


def _visible_text(raw_html):
    """Extract a simple text representation from an HTML response."""
    raw = html.unescape(raw_html or '')
    raw = re.sub(
        r'</?(?:article|br|div|h[1-6]|li|p|section|table|tbody|td|th|thead|tr)\b[^>]*>',
        '\n',
        raw,
        flags=re.IGNORECASE,
    )
    text = re.sub(r'<[^>]+>', ' ', raw)
    lines = [re.sub(r'\s+', ' ', line).strip() for line in text.splitlines()]
    return '\n'.join(line for line in lines if line)


def _date_tokens(match):
    """Return acceptable date tokens for validating a scraped score result."""
    dt = _parse_match_datetime(match)
    if not dt:
        return []

    month_names = {
        1: ('jan', 'janeiro'),
        2: ('fev', 'fevereiro'),
        3: ('mar', 'março'),
        4: ('abr', 'abril'),
        5: ('mai', 'maio'),
        6: ('jun', 'junho'),
        7: ('jul', 'julho'),
        8: ('ago', 'agosto'),
        9: ('set', 'setembro'),
        10: ('out', 'outubro'),
        11: ('nov', 'novembro'),
        12: ('dez', 'dezembro'),
    }

    # Brazilian sources normally present the local BRT date; stored dates are UTC.
    # Keep both to avoid rejecting midnight-UTC/date-only manual fixtures.
    candidate_dates = {dt.date(), (dt - timedelta(hours=3)).date()}
    tokens = []
    for date in sorted(candidate_dates):
        day = date.day
        month = date.month
        year = date.year
        month_short, month_full = month_names[month]
        tokens.extend([
            date.isoformat(),
            f'{day:02d}/{month:02d}/{year}',
            f'{day}/{month}/{year}',
            f'{day} de {month_full} de {year}',
            f'{day} {month_short} {year}',
            f'{day} {month_full} {year}',
        ])
    return list(dict.fromkeys(tokens))


def _competition_tokens(match):
    """Return competition tokens used to validate scraped search snippets."""
    competition = _parse_json_field(match, 'competition')
    code = str(competition.get('code') or '').upper()
    name = str(competition.get('name') or '')
    normalized_name = _normalize_text(name)

    tokens = [name] if name else []
    if code == 'COPA' or 'copa do brasil' in normalized_name:
        tokens.extend(['Copa do Brasil', 'Copa'])
    if code == 'CLI' or 'libertadores' in normalized_name:
        tokens.extend(['Libertadores', 'CONMEBOL Libertadores'])
    if code == 'BSA' or 'brasileir' in normalized_name or 'serie a' in normalized_name:
        tokens.extend(['Brasileirão', 'Brasileirao', 'Série A', 'Serie A', 'Campeonato Brasileiro'])
    if code == 'WC' or 'world cup' in normalized_name or 'copa do mundo' in normalized_name:
        tokens.extend(['FIFA World Cup', 'World Cup', 'Copa do Mundo'])

    return [token for token in dict.fromkeys(tokens) if token]


def _has_any_token(text, tokens):
    """Check whether any normalized token appears in normalized text."""
    normalized_text = _normalize_text(text)
    return any(_normalize_text(token) in normalized_text for token in tokens)


def _score_context_segment(text, start, end):
    """Return the rendered search-result/snippet segment containing a score."""
    line_start = text.rfind('\n', 0, start)
    line_end = text.find('\n', end)
    if line_start == -1:
        line_start = 0
    else:
        line_start += 1
    if line_end == -1:
        line_end = len(text)
    return text[line_start:line_end]


FINAL_SCORE_TOKENS = (
    'resultado final',
    'placar final',
    'fim de jogo',
    'jogo encerrado',
    'encerrado',
    'finalizado',
    'partida encerrada',
    'tempo regulamentar',
    'full-time',
    'full time',
    'ft',
)


def _has_final_score_signal(text):
    """Check whether nearby text says the score is final/full-time."""
    normalized_text = _normalize_text(text)
    for token in FINAL_SCORE_TOKENS:
        normalized_token = _normalize_text(token)
        # "ft" is the conventional full-time result marker.
        if normalized_token == 'ft':  # nosec B105
            if re.search(r'(^|[^a-z0-9])ft([^a-z0-9]|$)', normalized_text):
                return True
        elif normalized_token in normalized_text:
            return True
    return False


def _has_score_context(text, start, end, match):
    """
    Validate that a scraped score belongs to the expected finished fixture.

    Team names alone are not enough because repeated fixtures happen across legs,
    home/away reversals, seasons, and competitions. A Google fallback result is
    trusted only when the score appears near the expected match date, competition
    context, and a final/full-time indicator.
    """
    date_tokens = _date_tokens(match)
    competition_tokens = _competition_tokens(match)
    if not date_tokens or not competition_tokens:
        return False

    # Bind context to the same rendered snippet as the matched score. Do not use
    # a broad page-level window: Google pages can contain query echoes or nearby
    # result cards with the right date/competition/final words next to a
    # different Palmeiras score.
    window = _score_context_segment(text, start, end)
    return (
        _has_any_token(window, date_tokens)
        and _has_any_token(window, competition_tokens)
        and _has_final_score_signal(window)
    )


def _validate_score(home, away):
    """Sanity check before writing to database."""
    if not isinstance(home, int) or not isinstance(away, int):
        return False
    if home < 0 or away < 0:
        return False
    if home > MAX_SCORE or away > MAX_SCORE:
        return False
    return True


# ═══════════════════════════════════════════════════════════════════════════
# Sources — each returns a dict {home_score, away_score, half_time_*?} or None
# ═══════════════════════════════════════════════════════════════════════════

# Results for fixtures that are not covered by football-data.org. These are
# keyed by our protected manual IDs and sourced from the official Palmeiras
# match reports. Keeping them in the resolver prevents a stale SCHEDULED row
# from surviving when a live scraper changes markup or becomes unavailable.
VERIFIED_RESULTS = {
    990001: {'home_score': 3, 'away_score': 0},
    990002: {
        'home_score': 1,
        'away_score': 4,
        'utc_date': '2026-05-14T00:30:00+00:00',
        'venue': 'Estádio do Café',
    },
}


class VerifiedResults:
    """Locally verified results for manually maintained fixtures."""

    name = "verified-results"

    def available(self):
        return True

    def resolve_batch(self, matches):
        return {
            match['external_id']: VERIFIED_RESULTS[match['external_id']]
            for match in matches
            if match.get('external_id') in VERIFIED_RESULTS
        }

class FootballAPI:
    """football-data.org — official source for BSA, Libertadores, etc."""

    name = "football-data.org"

    def __init__(self):
        self.headers = {'X-Auth-Token': FOOTBALL_API_KEY} if FOOTBALL_API_KEY else {}
        self._cache = None

    def available(self):
        return bool(FOOTBALL_API_KEY)

    def _add_finished_results(self, results, url, *, params=None):
        import requests

        resp = requests.get(url, headers=self.headers, params=params, timeout=20)
        if resp.status_code != 200:
            _print(f"    [{self.name}] HTTP {resp.status_code}")
            return

        for m in resp.json().get('matches', []):
            ext_id = m.get('id')
            ft = m.get('score', {}).get('fullTime', {})
            ht = m.get('score', {}).get('halfTime', {})

            if ext_id and ft.get('home') is not None:
                results[ext_id] = {
                    'home_score': ft['home'],
                    'away_score': ft['away'],
                    'half_time_home': ht.get('home'),
                    'half_time_away': ht.get('away'),
                }

    def resolve_batch(self, matches):
        """
        Query finished matches from the API. Returns dict keyed by external_id.
        Single API call for all matches — efficient.
        """
        if not self.available():
            return {}

        try:
            results = {}
            self._add_finished_results(
                results,
                f'{API_BASE}/teams/{TEAM_ID}/matches',
                params={'status': 'FINISHED', 'limit': 25},
            )

            comp_codes = {
                str(_parse_json_field(match, 'competition').get('code') or '').upper()
                for match in matches
            }
            if 'WC' in comp_codes:
                self._add_finished_results(
                    results,
                    f'{API_BASE}/competitions/WC/matches',
                    params={'season': 2026, 'status': 'FINISHED'},
                )
            return results

        except Exception as e:
            _print(f"    [{self.name}] error: {e}")
            return {}


class GoogleSearch:
    """Google search — universal fallback for any competition."""

    name = "google"

    def resolve_single(self, match):
        """
        Scrape Google result page for a match score.
        Returns dict or None.
        """
        import requests

        home = _parse_team(match, 'home_team')
        away = _parse_team(match, 'away_team')
        home_name = home.get('shortName') or home.get('name', 'Home')
        away_name = away.get('shortName') or away.get('name', 'Away')
        date_tokens = _date_tokens(match)
        competition_tokens = _competition_tokens(match)

        if not date_tokens or not competition_tokens:
            return None

        # Build a targeted query with date and competition identity context.
        query_date = next(
            (token for token in date_tokens if re.fullmatch(r'\d{2}/\d{2}/\d{4}', token)),
            date_tokens[0],
        )
        query_parts = [
            f'"{home_name}"',
            f'"{away_name}"',
            f'"{query_date}"',
            f'"{competition_tokens[0]}"',
            'placar resultado',
        ]
        query = ' '.join(query_parts)

        try:
            resp = requests.get(
                'https://www.google.com/search',
                params={'q': query},
                headers={
                    'User-Agent': (
                        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                        'AppleWebKit/537.36 (KHTML, like Gecko) '
                        'Chrome/120.0.0.0 Safari/537.36'
                    ),
                },
                timeout=15,
            )
        except Exception as e:
            _print(f"    [{self.name}] request error: {e}")
            return None

        if resp.status_code != 200:
            _print(f"    [{self.name}] HTTP {resp.status_code}")
            return None

        text = _visible_text(resp.text)

        # Try structured patterns: "Palmeiras 3 x 0 Jacuipense"
        for swapped, pattern in self._patterns(home_name, away_name):
            for found in re.finditer(pattern, text, re.IGNORECASE):
                if not _has_score_context(text, found.start(), found.end(), match):
                    continue
                s1, s2 = int(found.group(1)), int(found.group(2))
                h = s2 if swapped else s1
                a = s1 if swapped else s2
                if _validate_score(h, a):
                    return {'home_score': h, 'away_score': a}

        return None

    @staticmethod
    def _patterns(home, away):
        """Yield (swapped, regex_pattern) tuples."""
        yield False, rf'{re.escape(home)}\s+(\d+)\s*[×x]\s*(\d+)\s+{re.escape(away)}'
        yield True, rf'{re.escape(away)}\s+(\d+)\s*[×x]\s*(\d+)\s+{re.escape(home)}'


# ═══════════════════════════════════════════════════════════════════════════
# Pipeline
# ═══════════════════════════════════════════════════════════════════════════

SOURCES = [VerifiedResults, FootballAPI, GoogleSearch]


def resolve_scores():
    """
    Main entry point. Find unresolved past matches and backfill their scores.

    Returns (resolved, total) tuple.
    """
    _print("  Score Resolver...")
    client = _get_supabase()
    if not client:
        return 0, 0

    now_utc = datetime.now(timezone.utc)
    cutoff = (now_utc - timedelta(hours=GRACE_HOURS)).isoformat()

    # Find matches past their scheduled time but still unresolved
    try:
        result = client.table('matches').select('*') \
            .in_('status', ['SCHEDULED', 'TIMED']) \
            .lt('utc_date', cutoff) \
            .order('utc_date') \
            .execute()
        unresolved = result.data
    except Exception as e:
        _print(f"    DB query error: {e}")
        raise

    if not unresolved:
        _print("    All past matches resolved ✓")
        return 0, 0

    _print(f"    {len(unresolved)} unresolved match(es)")

    resolved = 0
    failed_writes = 0
    sources = [cls() for cls in SOURCES]

    # Phase 1: batch sources (single API call covers many matches)
    batch_sources = [s for s in sources if hasattr(s, 'resolve_batch')]
    batch_results = {}
    for source in batch_sources:
        if not source.available():
            continue
        source_results = source.resolve_batch(unresolved)
        if source_results:
            _print(f"    [{source.name}] found {len(source_results)} result(s)")
            # Merge all batch sources so a manual Copa result does not prevent
            # football-data.org from resolving unrelated competitions.
            batch_results.update(source_results)

    # Phase 2: resolve each match
    for match in unresolved:
        ext_id = match.get('external_id')
        home = _parse_team(match, 'home_team')
        away = _parse_team(match, 'away_team')
        label = f"{home.get('shortName', '?')} vs {away.get('shortName', '?')}"

        score = None

        # Check batch results first
        if ext_id in batch_results:
            score = batch_results[ext_id]

        # Try per-match sources
        if not score:
            for source in sources:
                if not hasattr(source, 'resolve_single'):
                    continue
                try:
                    score = source.resolve_single(match)
                except Exception as e:
                    _print(f"    [{source.name}] {label}: error — {e}")
                    score = None
                finally:
                    time.sleep(REQUEST_DELAY)
                if score:
                    _print(f"    [{source.name}] {label}")
                    break

        # Write to database
        if score and _validate_score(score['home_score'], score['away_score']):
            if ext_id is None or ext_id == '':
                _print(f"    ✗ {label}: missing external_id, skipping DB write")
                continue
            update = {
                'status': 'FINISHED',
                'home_score': score['home_score'],
                'away_score': score['away_score'],
            }
            if score.get('half_time_home') is not None:
                update['half_time_home'] = score['half_time_home']
                update['half_time_away'] = score['half_time_away']
            # A verified manual fixture may also correct placeholder schedule
            # metadata that was entered before the official kickoff was set.
            for field in ('utc_date', 'venue'):
                if score.get(field):
                    update[field] = score[field]

            try:
                client.table('matches').update(update).eq('external_id', ext_id).execute()
                resolved += 1
                _print(f"    ✓ {label}: {score['home_score']}x{score['away_score']}")
            except Exception as e:
                failed_writes += 1
                _print(f"    ✗ {label}: DB write failed — {e}")
        else:
            date_str = match.get('utc_date', '?')[:10]
            _print(f"    ? {label} ({date_str}): no result found")

    _print(f"    {resolved}/{len(unresolved)} resolved")
    if failed_writes:
        raise RuntimeError(f"{failed_writes} score update(s) failed")
    return resolved, len(unresolved)


# ═══════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    print(f"Score Resolver — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    resolved, total = resolve_scores()
    print(f"Done: {resolved}/{total}")
