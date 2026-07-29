-- V15__ml_ranking_shadow_mode.down.sql

DROP INDEX IF EXISTS ml_ranking_shadow_events_subject_idx;
DROP INDEX IF EXISTS ml_ranking_shadow_events_mode_created_idx;
DROP TABLE IF EXISTS ml_ranking_shadow_events;
