"""Operational runner for the Palmeiras data collector.

This module is intentionally separate from the collector functions: systemd can
run it on a timer, and it keeps one failed source from preventing the rest of
the data pipeline from trying to refresh.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import time
import traceback
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

from . import (
    apply_broadcast_info,
    collect_copa_brasil,
    collect_matches,
    collect_news,
    collect_standings,
    collect_world_cup,
)
from .score_resolver import resolve_scores

DEFAULT_LOCK_PATH = "/tmp/palmeiras-collector.lock"
BASE_REQUIRED_ENV = ("SUPABASE_URL", "SUPABASE_KEY")
STEP_REQUIRED_ENV = {
    "matches": ("FOOTBALL_API_KEY",),
    "world_cup": ("FOOTBALL_API_KEY",),
    "standings": ("FOOTBALL_API_KEY",),
}


@dataclass
class StepResult:
    name: str
    status: str
    duration_ms: int
    detail: str = ""


@contextmanager
def exclusive_lock(path: str):
    lock_path = Path(path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("w") as lock_file:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _missing_env(required: Iterable[str]) -> list[str]:
    return [name for name in required if not os.environ.get(name)]


def _detail_from_result(value) -> str:
    if value is None:
        return "completed"
    if isinstance(value, tuple):
        return ", ".join(str(part) for part in value)
    return str(value)


def _run_step(name: str, func: Callable[[], object]) -> StepResult:
    start = time.monotonic()
    try:
        missing = _missing_env(STEP_REQUIRED_ENV.get(name, ()))
        if missing:
            raise RuntimeError(f"Missing required environment: {', '.join(missing)}")
        value = func()
        status = "ok"
        detail = _detail_from_result(value)
    except Exception as error:
        status = "error"
        detail = f"{type(error).__name__}: {error}"
        traceback.print_exc()
    duration_ms = round((time.monotonic() - start) * 1000)
    return StepResult(name=name, status=status, duration_ms=duration_ms, detail=detail)


def _steps(include_world_cup: bool) -> Iterable[tuple[str, Callable[[], object]]]:
    yield "matches", collect_matches
    yield "copa_brasil", collect_copa_brasil
    if include_world_cup:
        yield "world_cup", collect_world_cup
    yield "standings", collect_standings
    yield "score_resolver", resolve_scores
    yield "broadcasts", apply_broadcast_info
    yield "news", collect_news


def run(*, include_world_cup: bool = True, lock_path: str = DEFAULT_LOCK_PATH) -> tuple[int, dict]:
    started_at = datetime.now(timezone.utc).isoformat()
    missing = _missing_env(BASE_REQUIRED_ENV)
    if missing:
        summary = {
            "status": "error",
            "started_at": started_at,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "error": "missing_environment",
            "missing": missing,
        }
        return 2, summary

    with exclusive_lock(lock_path) as acquired:
        if not acquired:
            summary = {
                "status": "skipped",
                "started_at": started_at,
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "reason": "collector_already_running",
            }
            return 0, summary

        results = []
        print(f"[collector] started at {started_at}", flush=True)
        for name, func in _steps(include_world_cup):
            print(f"[collector] step={name} status=running", flush=True)
            result = _run_step(name, func)
            results.append(result)
            print(
                f"[collector] step={result.name} status={result.status} "
                f"duration_ms={result.duration_ms} detail={result.detail}",
                flush=True,
            )

    failed = [result.name for result in results if result.status != "ok"]
    status = "error" if failed else "ok"
    summary = {
        "status": status,
        "started_at": started_at,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "failed_steps": failed,
        "steps": [asdict(result) for result in results],
    }
    return (1 if failed else 0), summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Palmeiras data collector pipeline.")
    parser.add_argument(
        "--skip-world-cup",
        action="store_true",
        help="Skip the Copa 2026 data section after that tournament is retired.",
    )
    parser.add_argument(
        "--lock-path",
        default=os.environ.get("PALMEIRAS_COLLECTOR_LOCK", DEFAULT_LOCK_PATH),
        help="Path used to prevent overlapping collector runs.",
    )
    parser.add_argument("--json", action="store_true", help="Print only the final JSON summary.")
    args = parser.parse_args(argv)

    code, summary = run(include_world_cup=not args.skip_world_cup, lock_path=args.lock_path)
    payload = json.dumps(summary, ensure_ascii=False, sort_keys=True)
    if args.json:
        print(payload)
    else:
        print(f"[collector] summary={payload}", flush=True)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
