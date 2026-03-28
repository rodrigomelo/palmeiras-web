# Supabase Backup Configuration

Palmeiras Agenda uses Supabase (PostgreSQL) as its backend. This guide explains how to configure automatic backups.

## Option 1: Supabase Dashboard (Recommended for Pro projects)

### Via pg_dump (Manual/External)

Supabase Pro projects support `pg_dum p` through the PostgreSQL connection string.

1. **Get your connection string:**
   - Go to Supabase Dashboard → Project Settings → Database
   - Copy the "Connection string" (URI format)

2. **Run pg_dump:**
   ```bash
   pg_dump "postgresql://postgres:[PASSWORD]@db.[PROJECT-REF].supabase.co:5432/postgres" \
     --file=palmeiras_backup_$(date +%Y%m%d).sql
   ```

3. **Automate with cron (macOS/Linux):**
   ```bash
   # Edit crontab
   crontab -e

   # Add: run backup daily at 3am
   0 3 * * * pg_dump "postgresql://postgres:[PASSWORD]@db.[REF].supabase.co:5432/postgres" \
     --file=/Users/rodrigomelo/backups/palmeiras_$(date +\%Y\%m\%d).sql

   # Also upload to cloud storage
   0 3 * * * pg_dump "postgresql://..." | gzip | \
     aws s3 cp - s3://my-bucket/palmeiras_$(date +\%Y\%m\%d).sql.gz
   ```

## Option 2: Point-in-Time Recovery (Supabase Pro)

Supabase Pro includes continuous WAL archiving and point-in-time recovery (PITR).

1. **Enable PITR:**
   - Supabase Dashboard → Database → Backups
   - Point-in-time recovery is available on Pro projects automatically

2. **Restore to a point in time:**
   ```bash
   # Via Supabase dashboard or
   psql "postgresql://postgres:[PASSWORD]@db.[REF].supabase.co:6543/postgres" \
     -c "SELECT pg_restore_to_point('2025-01-01 00:00:00-03', '/path/to/dump');"
   ```

## Option 3: Supabase Management API

Use the Supabase Management API to trigger backups programmatically:

```bash
# Get all backups
curl -X GET "https://api.supabase.com/v1/projects/[PROJECT-ID]/backups" \
  -H "Authorization: Bearer [ACCESS_TOKEN]" \
  -H "apikey: [ACCESS_TOKEN]"

# The Management API requires a Personal Access Token from
# https://app.supabase.com/account/tokens
```

## Option 4: Python Script (Custom Backup)

```python
# collectors/backup.py
import subprocess
import os
from datetime import datetime

def run_backup():
    conn = os.environ.get('SUPABASE_DB_URL')
    if not conn:
        print("SUPABASE_DB_URL not set")
        return

    filename = f"palmeiras_backup_{datetime.now().strftime('%Y%m%d_%H%M')}.sql"
    result = subprocess.run(
        ['pg_dump', conn, '--file', filename],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        print(f"Backup saved: {filename}")
    else:
        print(f"Backup failed: {result.stderr}")

if __name__ == '__main__':
    run_backup()
```

## Option 5: Supabase Native Backups (if available)

Check your project's backup settings:
1. Supabase Dashboard → Your Project → Database
2. Look for "Backups" section
3. Configure schedule (daily/weekly)

## Restore from Backup

```bash
# Restore a pg_dump backup
psql "postgresql://postgres:[PASSWORD]@db.[REF].supabase.co:6543/postgres" \
  < palmeiras_backup_20250101.sql
```

## Tables to Back Up

Palmeiras Agenda uses these tables:
- `matches` — all match data (critical)
- `standings` — league standings (rebuildable)
- `news` — scraped news articles (rebuildable)

**Priority:** Always backup the `matches` table first.

## Schedule Recommendation

| Frequency | What's backed up | Method |
|-----------|-----------------|--------|
| Daily 3am | Full `matches` + `standings` | pg_dump + cron |
| Weekly | Full database | pg_dump |
| Before collector runs | Optional safety backup | Python script |

## Storage Recommendations

- **Local:** `~/backups/palmeiras/` (for quick restore)
- **Cloud:** S3/GCS with lifecycle policy (auto-delete after 90 days)
- **Git:** ❌ Never commit backups — large and security risk
