"""
Palmeiras Agenda — Automated Scheduler

Runs all collectors on a configurable schedule using Python's APScheduler.
This avoids depending on system cron while being portable.

Usage:
    cd collectors
    python scheduler.py                    # Run continuously
    python scheduler.py --once            # Run once and exit (for manual/cron triggers)
    python scheduler.py --collect-only   # Collect data without starting scheduler

Schedule (default):
    Every 4 hours:  collect all data
    Every 30 min:   collect only matches + standings (fast)
    On startup:     full collection

Environment variables (from .env):
    SUPABASE_URL, SUPABASE_KEY, FOOTBALL_API_KEY, API_FOOTBALL_KEY

Requirements:
    pip install apscheduler python-dotenv supabase requests beautifulsoup4
"""
import argparse
import os
import sys
import logging
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / '.env')

# Setup logging
LOG_DIR = Path(__file__).parent.parent / 'logs'
LOG_DIR.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / f'collector_{datetime.now().strftime("%Y%m%d")}.log'),
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger('scheduler')


def import_collectors():
    """Import and return the main collector functions."""
    sys.path.insert(0, str(Path(__file__).parent))
    # Import main collector
    from collectors import collect_matches, collect_standings, collect_news, apply_broadcast_info
    return {
        'matches': collect_matches,
        'standings': collect_standings,
        'news': collect_news,
        'broadcast': apply_broadcast_info,
    }


def run_full_collection():
    """Run all collectors."""
    logger.info("=== Starting full collection ===")
    try:
        collectors = import_collectors()
        collectors['matches']()
        collectors['standings']()
        collectors['news']()
        collectors['broadcast']()
        logger.info("=== Full collection complete ===")
    except Exception as e:
        logger.error(f"Collection error: {e}")


def run_quick_collection():
    """Run only fast collectors (matches + standings)."""
    logger.info("=== Starting quick collection ===")
    try:
        collectors = import_collectors()
        collectors['matches']()
        collectors['standings']()
        logger.info("=== Quick collection complete ===")
    except Exception as e:
        logger.error(f"Quick collection error: {e}")


def run_selenuim_collection():
    """Run Selenium collectors (expensive, run less frequently)."""
    logger.info("=== Starting Selenium collection ===")
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from collectors.sofascore_collector import scrape_sofascore_palmeiras, save_to_supabase
        matches = scrape_sofascore_palmeiras()
        if matches:
            save_to_supabase(matches)
        logger.info("=== Selenium collection complete ===")
    except ImportError as e:
        logger.warning(f"Selenium not available: {e}")
    except Exception as e:
        logger.error(f"Selenium collection error: {e}")


def run_apifootball_collection():
    """Run API-Football collectors for Libertadores."""
    logger.info("=== Starting API-Football collection ===")
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from collectors.apifootball_collector import (
            collect_libertadores_standings,
            collect_copa_brasil_standings,
            collect_bsa_standings_apifootball,
        )
        collect_libertadores_standings()
        collect_copa_brasil_standings()
        collect_bsa_standings_apifootball()
        logger.info("=== API-Football collection complete ===")
    except ImportError as e:
        logger.warning(f"API-Football collector not available: {e}")
    except Exception as e:
        logger.error(f"API-Football collection error: {e}")


def start_scheduler(quick_interval_hours=0.5, full_interval_hours=4):
    """Start the APScheduler with configured intervals."""
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
    except ImportError:
        logger.error("apscheduler not installed. Run: pip install apscheduler")
        logger.info("Falling back to single run.")
        run_full_collection()
        return

    scheduler = BackgroundScheduler(timezone='America/Sao_Paulo', job_defaults={
        'coalesce': True,
        'max_instances': 1,
        'misfire_grace_time': 300,
    })

    # Quick collection every 30 min (matches + standings)
    scheduler.add_job(
        run_quick_collection,
        'interval',
        hours=quick_interval_hours,
        id='quick_collection',
        name='Quick collection (matches + standings)',
        replace_existing=True,
    )

    # Full collection every 4 hours (includes news, crests, etc.)
    scheduler.add_job(
        run_full_collection,
        'interval',
        hours=full_interval_hours,
        id='full_collection',
        name='Full data collection',
        replace_existing=True,
    )

    # Selenium (SofaScore) every 6 hours
    scheduler.add_job(
        run_selenuim_collection,
        'interval',
        hours=6,
        id='selenium_collection',
        name='Selenium SofaScore scraper',
        replace_existing=True,
    )

    # API-Football (Libertadores) every 4 hours
    scheduler.add_job(
        run_apifootball_collection,
        'interval',
        hours=4,
        id='apifootball_collection',
        name='API-Football Libertadores',
        replace_existing=True,
    )

    scheduler.start()
    logger.info(f"Scheduler started — quick={quick_interval_hours}h, full={full_interval_hours}h")
    logger.info(f"Jobs: {[j.id for j in scheduler.get_jobs()]}")
    return scheduler


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Palmeiras Agenda Scheduler')
    parser.add_argument('--once', action='store_true', help='Run all collectors once and exit')
    parser.add_argument('--collect-only', action='store_true', help='Run full collection once (alias for --once)')
    parser.add_argument('--quick', action='store_true', help='Run quick collection (matches + standings)')
    parser.add_argument('--selenium', action='store_true', help='Run Selenium collection only')
    parser.add_argument('--apifootball', action='store_true', help='Run API-Football collection only')
    args = parser.parse_args()

    if args.collect_only or args.once:
        run_full_collection()
    elif args.quick:
        run_quick_collection()
    elif args.selenium:
        run_selenuim_collection()
    elif args.apifootball:
        run_apifootball_collection()
    else:
        print("Palmeiras Agenda Scheduler")
        print("=" * 40)
        print("Starting background scheduler...")
        print("Options:")
        print("  --once          Run all collectors once")
        print("  --quick         Quick collection (matches + standings)")
        print("  --selenium      Selenium SofaScore collection")
        print("  --apifootball  API-Football Libertadores collection")
        print("  [no args]      Start background scheduler")
        print()
        scheduler = start_scheduler()
        print("Scheduler running. Press Ctrl+C to stop.")
        try:
            import time
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            print("\nStopping scheduler...")
            scheduler.shutdown(wait=False)
