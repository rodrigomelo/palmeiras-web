-- Palmeiras Data Schema v2 — Enhanced fields
-- Run in Supabase SQL Editor

BEGIN;

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Matches (enhanced)
CREATE TABLE IF NOT EXISTS matches (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    external_id INTEGER UNIQUE,
    home_team JSONB,
    away_team JSONB,
    home_score INTEGER,
    away_score INTEGER,
    half_time_home INTEGER,
    half_time_away INTEGER,
    utc_date TIMESTAMPTZ,
    status VARCHAR(20),
    competition JSONB,
    season JSONB,
    matchday INTEGER,
    stage VARCHAR(100),
    venue VARCHAR(255),
    area JSONB,
    referees JSONB,
    broadcast VARCHAR(255),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Standings
CREATE TABLE IF NOT EXISTS standings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    competition VARCHAR(50),
    position INTEGER,
    team JSONB,
    played_games INTEGER,
    won INTEGER,
    drawn INTEGER,
    lost INTEGER,
    goals_for INTEGER,
    goals_against INTEGER,
    goal_difference INTEGER,
    points INTEGER,
    form VARCHAR(10),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- News
CREATE TABLE IF NOT EXISTS news (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    title VARCHAR(500),
    summary TEXT,
    url TEXT,
    image TEXT,
    source VARCHAR(100),
    published_at TIMESTAMPTZ,
    collected_at TIMESTAMPTZ DEFAULT NOW()
);

-- Unique constraints for upsert support
CREATE UNIQUE INDEX IF NOT EXISTS standings_competition_position_uniq ON standings(competition, position);
CREATE UNIQUE INDEX IF NOT EXISTS news_url_uniq ON news(url);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_matches_status ON matches(status);
CREATE INDEX IF NOT EXISTS idx_matches_date ON matches(utc_date);
CREATE INDEX IF NOT EXISTS idx_standings_competition ON standings(competition);
CREATE INDEX IF NOT EXISTS idx_news_collected ON news(collected_at DESC);

-- RLS
ALTER TABLE matches ENABLE ROW LEVEL SECURITY;
ALTER TABLE standings ENABLE ROW LEVEL SECURITY;
ALTER TABLE news ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS matches_read ON matches;
DROP POLICY IF EXISTS matches_write ON matches;
DROP POLICY IF EXISTS matches_update ON matches;
DROP POLICY IF EXISTS standings_read ON standings;
DROP POLICY IF EXISTS standings_write ON standings;
DROP POLICY IF EXISTS standings_update ON standings;
DROP POLICY IF EXISTS standings_delete ON standings;
DROP POLICY IF EXISTS news_read ON news;
DROP POLICY IF EXISTS news_write ON news;
DROP POLICY IF EXISTS news_update ON news;
DROP POLICY IF EXISTS news_delete ON news;

CREATE POLICY matches_read ON matches FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY standings_read ON standings FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY news_read ON news FOR SELECT TO anon, authenticated USING (true);

REVOKE INSERT, UPDATE, DELETE ON matches FROM anon, authenticated;
REVOKE INSERT, UPDATE, DELETE ON standings FROM anon, authenticated;
REVOKE INSERT, UPDATE, DELETE ON news FROM anon, authenticated;
GRANT SELECT ON matches, standings, news TO anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON matches, standings, news TO service_role;

ALTER TABLE matches DROP CONSTRAINT IF EXISTS chk_home_score;
ALTER TABLE matches DROP CONSTRAINT IF EXISTS chk_away_score;
ALTER TABLE matches DROP CONSTRAINT IF EXISTS chk_half_time_home;
ALTER TABLE matches DROP CONSTRAINT IF EXISTS chk_half_time_away;
ALTER TABLE matches ADD CONSTRAINT chk_home_score CHECK (home_score IS NULL OR (home_score >= 0 AND home_score <= 30)) NOT VALID;
ALTER TABLE matches ADD CONSTRAINT chk_away_score CHECK (away_score IS NULL OR (away_score >= 0 AND away_score <= 30)) NOT VALID;
ALTER TABLE matches ADD CONSTRAINT chk_half_time_home CHECK (half_time_home IS NULL OR (half_time_home >= 0 AND half_time_home <= 30)) NOT VALID;
ALTER TABLE matches ADD CONSTRAINT chk_half_time_away CHECK (half_time_away IS NULL OR (half_time_away >= 0 AND half_time_away <= 30)) NOT VALID;

COMMIT;

-- Migration for existing installations:
-- ALTER TABLE matches ADD COLUMN IF NOT EXISTS half_time_home INTEGER;
-- ALTER TABLE matches ADD COLUMN IF NOT EXISTS half_time_away INTEGER;
-- ALTER TABLE matches ADD COLUMN IF NOT EXISTS season JSONB;
-- ALTER TABLE matches ADD COLUMN IF NOT EXISTS stage VARCHAR(100);
-- ALTER TABLE matches ADD COLUMN IF NOT EXISTS area JSONB;
-- ALTER TABLE matches ADD COLUMN IF NOT EXISTS referees JSONB;
-- ALTER TABLE matches ADD COLUMN IF NOT EXISTS broadcast VARCHAR(255);
-- ALTER TABLE standings ADD COLUMN IF NOT EXISTS form VARCHAR(10);
-- CREATE UNIQUE INDEX IF NOT EXISTS standings_competition_position_uniq ON standings(competition, position);
-- CREATE UNIQUE INDEX IF NOT EXISTS news_url_uniq ON news(url);

-- M2: CHECK constraints on score columns are added above as NOT VALID, so new
-- writes are protected without forcing a full scan of existing rows.
