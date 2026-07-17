#!/usr/bin/env python3
"""Refresh the Palmeiras news feed in Supabase."""
from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from collectors import collect_news  # noqa: E402


def main():
    started = datetime.now(timezone.utc).isoformat()
    print(f'[{started}] Palmeiras news refresh starting', flush=True)

    ok = collect_news()
    finished = datetime.now(timezone.utc).isoformat()
    if not ok:
        print(f'[{finished}] Palmeiras news refresh FAILED', flush=True)
        return 1

    print(f'[{finished}] Palmeiras news refresh done', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
