-- Palmeiras Data Schema for Supabase
-- Run in Supabase SQL Editor

BEGIN;

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Matches
CREATE TABLE IF NOT EXISTS matches (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    external_id INTEGER UNIQUE,
    home_team JSONB,
    away_team JSONB,
    home_score INTEGER,
    away_score INTEGER,
    utc_date TIMESTAMPTZ,
    status VARCHAR(20),
    competition JSONB,
    matchday INTEGER,
    venue VARCHAR(255),
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

-- Indexes
CREATE INDEX IF NOT EXISTS idx_matches_status ON matches(status);
CREATE INDEX IF NOT EXISTS idx_matches_date ON matches(utc_date);
CREATE INDEX IF NOT EXISTS idx_standings_competition ON standings(competition);
CREATE INDEX IF NOT EXISTS idx_news_collected ON news(collected_at DESC);

-- RLS (public read, authenticated write)
ALTER TABLE matches ENABLE ROW LEVEL SECURITY;
ALTER TABLE standings ENABLE ROW LEVEL SECURITY;
ALTER TABLE news ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'matches' AND policyname = 'matches_read') THEN
        CREATE POLICY "matches_read" ON matches FOR SELECT USING (true);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'matches' AND policyname = 'matches_write') THEN
        CREATE POLICY "matches_write" ON matches FOR INSERT WITH CHECK (true);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'matches' AND policyname = 'matches_update') THEN
        CREATE POLICY "matches_update" ON matches FOR UPDATE USING (true);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'standings' AND policyname = 'standings_read') THEN
        CREATE POLICY "standings_read" ON standings FOR SELECT USING (true);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'standings' AND policyname = 'standings_write') THEN
        CREATE POLICY "standings_write" ON standings FOR INSERT WITH CHECK (true);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'news' AND policyname = 'news_read') THEN
        CREATE POLICY "news_read" ON news FOR SELECT USING (true);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'news' AND policyname = 'news_write') THEN
        CREATE POLICY "news_write" ON news FOR INSERT WITH CHECK (true);
    END IF;
END $$;

COMMIT;
