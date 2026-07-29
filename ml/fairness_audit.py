#!/usr/bin/env python3
"""
Fairness audit for ML ranking — compares exposure of new vs established freelancers.

Usage:
  export DATABASE_URL=postgresql://...
  python ml/fairness_audit.py
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd
import psycopg2
from dotenv import load_dotenv

load_dotenv()

NEW_THRESHOLD = int(os.environ.get("ML_RANKING_COLD_START_MIN_HISTORY", "2")) + 1


def connect():
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL is required")
    return psycopg2.connect(url)


def audit_from_shadow_events(conn) -> dict:
    query = """
    SELECT ml_ranking, created_at
    FROM ml_ranking_shadow_events
    WHERE mode = 'freelancers_for_job'
      AND fallback_used = false
      AND created_at > NOW() - INTERVAL '30 days'
    """
    events = pd.read_sql(query, conn)
    if events.empty:
        return {"status": "no_shadow_data", "message": "Enable ML_RANKING_SHADOW_MODE and collect events first"}

    keys = []
    for _, row in events.iterrows():
        ranking = row["ml_ranking"]
        if isinstance(ranking, str):
            ranking = json.loads(ranking)
        for item in ranking:
            pk = item.get("publicKey")
            if pk:
                keys.append(pk)

    if not keys:
        return {"status": "empty", "impressions": 0}

    profiles = pd.read_sql(
        "SELECT public_key, completed_jobs FROM profiles WHERE public_key = ANY(%s)",
        conn,
        params=(keys,),
    )
    cohort_map = {
        r.public_key: ("new" if (r.completed_jobs or 0) < NEW_THRESHOLD else "established")
        for r in profiles.itertuples()
    }

    counts = {"new": 0, "established": 0, "unknown": 0}
    for key in keys:
        counts[cohort_map.get(key, "unknown")] += 1

    total = sum(counts.values()) or 1
    report = {
        "status": "ok",
        "impressions": total,
        "new_freelancer_share": round(counts["new"] / total, 3),
        "established_freelancer_share": round(counts["established"] / total, 3),
        "unknown_share": round(counts["unknown"] / total, 3),
        "new_threshold_completed_jobs": NEW_THRESHOLD,
        "mitigation": "exploration_boost + reserved exploration slots in mlRankingService",
    }

    if report["new_freelancer_share"] < 0.1:
        report["bias_detected"] = True
        report["recommendation"] = "Increase ML_RANKING_EXPLORATION_BUDGET or exploration_boost in model fairness config"
    else:
        report["bias_detected"] = False

    return report


def audit_from_training_data(conn) -> dict:
    """Offline audit: acceptance rate parity across cohorts on historical applications."""
    query = """
    SELECT
      a.status,
      p.completed_jobs,
      CASE WHEN p.completed_jobs < %s THEN 'new' ELSE 'established' END AS cohort
    FROM applications a
    JOIN profiles p ON p.public_key = a.freelancer_address
    """
    df = pd.read_sql(query, conn, params=(NEW_THRESHOLD,))
    if df.empty:
        return {"status": "no_data"}

    summary = (
        df.assign(accepted=df["status"] == "accepted")
        .groupby("cohort")["accepted"]
        .agg(["mean", "count"])
        .reset_index()
    )

    return {
        "status": "ok",
        "historical_acceptance_by_cohort": summary.to_dict(orient="records"),
    }


def main():
    conn = connect()
    try:
        shadow = audit_from_shadow_events(conn)
        historical = audit_from_training_data(conn)
    finally:
        conn.close()

    report = {"shadow_mode": shadow, "historical": historical}
    out = Path(__file__).resolve().parent / "fairness_audit_report.json"
    out.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
