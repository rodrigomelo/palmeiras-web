# Palmeiras Web Dashboard

**⚠️ THIS IS THE PRESENTATION LAYER ONLY**

This app does NOT:
- ❌ Fetch data from external APIs
- ❌ Store data locally
- ❌ Have its own data files

This app ONLY:
- ✅ Reads data from Data Lake API (port 5002)
- ✅ Displays the data in a nice UI

## Architecture

```
External APIs → Data Lake (5002) → This App (5001) → Browser
```

See `../palmeiras-data-lake/ARCHITECTURE.md` for full details.

## Running

```bash
source venv/bin/activate
python server.py
```

Open http://localhost:5001

## Data Source

All data comes from `http://localhost:5002` (Data Lake API).

If Data Lake is down, this app will show errors - it does NOT have local fallbacks.
