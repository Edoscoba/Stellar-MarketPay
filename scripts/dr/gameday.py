#!/usr/bin/env python3
"""Measure MarketPay multi-cluster failover without hiding unsafe assumptions."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable


@dataclass
class GameDayConfig:
    primary_url: str
    secondary_url: str
    public_url: str
    secondary_region: str
    failure_command: str
    restore_command: str | None
    rto_target_seconds: float = 600
    rpo_target_seconds: float = 60
    timeout_seconds: float = 900
    poll_seconds: float = 5


@dataclass
class GameDayResult:
    mode: str
    passed: bool
    rto_target_seconds: float
    rto_actual_seconds: float | None
    rpo_target_seconds: float
    rpo_actual_seconds: float | None
    secondary_region: str
    failure_reason: str | None


def fetch_health(url: str) -> dict:
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        response = urllib.request.urlopen(request, timeout=5)
        payload = response.read()
    except urllib.error.HTTPError as error:
        # A passive replica intentionally returns 503 but its JSON contains the
        # replay lag needed for the pre-failure RPO measurement.
        payload = error.read()
    return json.loads(payload)


def shell(command: str) -> None:
    subprocess.run(command, shell=True, check=True)


def run_game_day(
    config: GameDayConfig,
    *,
    health: Callable[[str], dict] = fetch_health,
    execute: Callable[[str], None] = shell,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    mode: str = "live",
) -> GameDayResult:
    try:
        primary = health(config.primary_url)
    except Exception as error:
        return GameDayResult(
            mode, False, config.rto_target_seconds, None,
            config.rpo_target_seconds, None, config.secondary_region,
            f"Primary preflight failed: {error}",
        )
    if (
        primary.get("status") != "healthy"
        or primary.get("database", {}).get("writable") is not True
    ):
        return GameDayResult(
            mode, False, config.rto_target_seconds, None,
            config.rpo_target_seconds, None, config.secondary_region,
            "Primary was not healthy and writable before injection.",
        )

    try:
        secondary = health(config.secondary_url)
    except Exception as error:
        return GameDayResult(
            mode, False, config.rto_target_seconds, None,
            config.rpo_target_seconds, None, config.secondary_region,
            f"Secondary preflight failed: {error}",
        )
    database = secondary.get("database", {})
    lag = database.get("replay_lag_seconds")
    if database.get("status") != "ok" or database.get("role") != "replica":
        return GameDayResult(
            mode, False, config.rto_target_seconds, None,
            config.rpo_target_seconds, None, config.secondary_region,
            "Secondary database was not a healthy replica before injection.",
        )
    if not isinstance(lag, (int, float)) or lag > config.rpo_target_seconds:
        return GameDayResult(
            mode, False, config.rto_target_seconds, None,
            config.rpo_target_seconds, lag, config.secondary_region,
            "Replication lag exceeded the RPO target before injection.",
        )

    started = monotonic()
    failure_reason = None
    rto = None
    try:
        try:
            execute(config.failure_command)
        except Exception as error:
            failure_reason = f"Failure injection command failed: {error}"

        deadline = started + config.timeout_seconds
        while failure_reason is None and monotonic() < deadline:
            try:
                public = health(config.public_url)
                public_db = public.get("database", {})
                if (
                    public.get("status") == "healthy"
                    and public.get("region") == config.secondary_region
                    and public_db.get("writable") is True
                ):
                    rto = monotonic() - started
                    break
            except (OSError, ValueError, json.JSONDecodeError):
                pass
            sleep(config.poll_seconds)
        if failure_reason is None and rto is None:
            failure_reason = "Public traffic did not recover on the writable secondary."
        elif failure_reason is None and rto > config.rto_target_seconds:
            failure_reason = "Measured RTO exceeded the target."
    finally:
        if config.restore_command:
            try:
                execute(config.restore_command)
            except Exception as error:
                restore_error = f"Restoration command failed: {error}"
                # Never silently discard an earlier failure reason (e.g. the
                # failure-injection command itself failing) just because
                # restoration also failed — an operator reading the report
                # needs both, not whichever happened last.
                failure_reason = (
                    f"{failure_reason}; {restore_error}"
                    if failure_reason
                    else restore_error
                )

    return GameDayResult(
        mode=mode,
        passed=failure_reason is None,
        rto_target_seconds=config.rto_target_seconds,
        rto_actual_seconds=rto,
        rpo_target_seconds=config.rpo_target_seconds,
        rpo_actual_seconds=float(lag),
        secondary_region=config.secondary_region,
        failure_reason=failure_reason,
    )


def write_reports(result: GameDayResult, json_path: Path, markdown_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(asdict(result), indent=2) + "\n")
    qualification = (
        "Production evidence" if result.mode == "live"
        else "Control-plane simulation only; this does not certify production RTO/RPO"
    )
    markdown_path.write_text(
        "\n".join(
            [
                "# Disaster-recovery game-day result",
                "",
                f"- Evidence: {qualification}",
                f"- Result: {'PASS' if result.passed else 'FAIL'}",
                f"- RTO: {result.rto_actual_seconds}s actual / {result.rto_target_seconds}s target",
                f"- RPO: {result.rpo_actual_seconds}s actual / {result.rpo_target_seconds}s target",
                f"- Failover region: `{result.secondary_region}`",
                f"- Failure reason: {result.failure_reason or 'None'}",
                "",
            ]
        )
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        required=True,
        choices=["live", "simulation"],
        help=(
            "'live' certifies production evidence and must only be used against "
            "real primary/secondary clusters. 'simulation' is for a dry run "
            "against mock endpoints/commands and is labeled as such in the "
            "report — it must never be reported as production evidence. There "
            "is no default: the operator running this must consciously say "
            "which one they're doing, since the report's own qualification "
            "language depends on it."
        ),
    )
    parser.add_argument("--primary-url", required=True)
    parser.add_argument("--secondary-url", required=True)
    parser.add_argument("--public-url", required=True)
    parser.add_argument("--secondary-region", required=True)
    parser.add_argument("--failure-command", required=True)
    parser.add_argument("--restore-command")
    parser.add_argument("--rto-target-seconds", type=float, default=600)
    parser.add_argument("--rpo-target-seconds", type=float, default=60)
    parser.add_argument("--timeout-seconds", type=float, default=900)
    parser.add_argument("--poll-seconds", type=float, default=5)
    parser.add_argument("--report-json", type=Path, default=Path("artifacts/dr-gameday.json"))
    parser.add_argument(
        "--report-markdown", type=Path, default=Path("artifacts/dr-gameday.md")
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_game_day(
        GameDayConfig(
            primary_url=args.primary_url,
            secondary_url=args.secondary_url,
            public_url=args.public_url,
            secondary_region=args.secondary_region,
            failure_command=args.failure_command,
            restore_command=args.restore_command,
            rto_target_seconds=args.rto_target_seconds,
            rpo_target_seconds=args.rpo_target_seconds,
            timeout_seconds=args.timeout_seconds,
            poll_seconds=args.poll_seconds,
        ),
        mode=args.mode,
    )
    write_reports(result, args.report_json, args.report_markdown)
    print(json.dumps(asdict(result), indent=2))
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
