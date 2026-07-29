-- V15__ml_ranking_shadow_mode.up.sql
-- Shadow-mode logging for ML vs baseline ranking comparisons (Issue #89)

CREATE TABLE IF NOT EXISTS ml_ranking_shadow_events (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  mode              TEXT NOT NULL CHECK (mode IN ('jobs_for_freelancer', 'freelancers_for_job')),
  subject_key       TEXT NOT NULL,
  context_key       TEXT,
  ml_ranking        JSONB NOT NULL DEFAULT '[]'::jsonb,
  baseline_ranking  JSONB NOT NULL DEFAULT '[]'::jsonb,
  latency_ms        INTEGER NOT NULL DEFAULT 0,
  fallback_used     BOOLEAN NOT NULL DEFAULT false,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ml_ranking_shadow_events_mode_created_idx
  ON ml_ranking_shadow_events(mode, created_at DESC);

CREATE INDEX IF NOT EXISTS ml_ranking_shadow_events_subject_idx
  ON ml_ranking_shadow_events(subject_key, created_at DESC);
