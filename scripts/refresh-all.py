#!/usr/bin/env python3
"""Refresh all Palmeiras Agenda data sources in Supabase."""
from datetime import datetime, timezone
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from collectors import (  # noqa: E402
    apply_broadcast_info,
    collect_copa_brasil,
    collect_matches,
    collect_news,
    collect_standings,
)
from collectors.score_resolver import resolve_scores  # noqa: E402


def run_stage(name, fn, *, attempts=1):
    for attempt in range(1, attempts + 1):
        started = time.monotonic()
        suffix = f' attempt {attempt}/{attempts}' if attempts > 1 else ''
        print(f'  {name}{suffix}...', flush=True)
        try:
            result = fn()
        except Exception as error:
            elapsed = time.monotonic() - started
            print(f'  {name}: ERROR after {elapsed:.1f}s — {type(error).__name__}: {error}', flush=True)
            result = False

        elapsed = time.monotonic() - started
        if result is not False:
            print(f'  {name}: ok after {elapsed:.1f}s', flush=True)
            return True

        print(f'  {name}: FAILED after {elapsed:.1f}s', flush=True)
        if attempt < attempts:
            time.sleep(3 * attempt)

    return False


def resolve_recent_scores():
    resolved, total = resolve_scores(max_age_days=7)
    print(f'    score resolver recent window: {resolved}/{total} resolved', flush=True)
    return True


def main():
    started = datetime.now(timezone.utc).isoformat()
    print(f'[{started}] Palmeiras full refresh starting', flush=True)

    stages = [
        ('matches', collect_matches, True, 2),
        ('standings', collect_standings, True, 3),
        ('news', collect_news, False, 2),
        ('copa_brasil', collect_copa_brasil, False, 1),
        ('score_resolver', resolve_recent_scores, False, 1),
        ('broadcast_info', apply_broadcast_info, False, 1),
    ]

    failed_critical = []
    warnings = []
    for name, fn, critical, attempts in stages:
        ok = run_stage(name, fn, attempts=attempts)
        if ok:
            continue
        if critical:
            failed_critical.append(name)
        else:
            warnings.append(name)

    finished = datetime.now(timezone.utc).isoformat()
    if warnings:
        print(f'[{finished}] Palmeiras full refresh warnings: {", ".join(warnings)}', flush=True)
    if failed_critical:
        print(f'[{finished}] Palmeiras full refresh FAILED: {", ".join(failed_critical)}', flush=True)
        return 1

    print(f'[{finished}] Palmeiras full refresh done', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
