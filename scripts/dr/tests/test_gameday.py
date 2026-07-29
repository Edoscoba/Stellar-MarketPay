import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gameday import GameDayConfig, GameDayResult, run_game_day, write_reports


class Clock:
    def __init__(self):
        self.value = 0.0

    def monotonic(self):
        return self.value

    def sleep(self, seconds):
        self.value += seconds


class GameDayTests(unittest.TestCase):
    def config(self):
        return GameDayConfig(
            primary_url="https://primary/health/ready",
            secondary_url="https://secondary/health/ready",
            public_url="https://public/health/ready",
            secondary_region="secondary-cluster",
            failure_command="inject",
            restore_command="restore",
            rto_target_seconds=60,
            rpo_target_seconds=30,
            timeout_seconds=90,
            poll_seconds=10,
        )

    def test_measures_successful_failover(self):
        clock = Clock()
        calls = {"public": 0, "commands": []}

        def health(url):
            if "primary" in url:
                return {"status": "healthy", "database": {"writable": True}}
            if "secondary" in url:
                return {
                    "database": {
                        "status": "ok",
                        "role": "replica",
                        "replay_lag_seconds": 12,
                    }
                }
            calls["public"] += 1
            if calls["public"] < 3:
                raise OSError("DNS still points to failed primary")
            return {
                "status": "healthy",
                "region": "secondary-cluster",
                "database": {"writable": True},
            }

        result = run_game_day(
            self.config(),
            health=health,
            execute=calls["commands"].append,
            monotonic=clock.monotonic,
            sleep=clock.sleep,
            mode="simulation",
        )

        self.assertTrue(result.passed)
        self.assertEqual(result.rto_actual_seconds, 20)
        self.assertEqual(result.rpo_actual_seconds, 12)
        self.assertEqual(calls["commands"], ["inject", "restore"])

    def test_refuses_failover_when_replication_exceeds_rpo(self):
        commands = []

        result = run_game_day(
            self.config(),
            health=lambda url: (
                {"status": "healthy", "database": {"writable": True}}
                if "primary" in url
                else {
                    "database": {
                        "status": "ok",
                        "role": "replica",
                        "replay_lag_seconds": 31,
                    }
                }
            ),
            execute=commands.append,
        )

        self.assertFalse(result.passed)
        self.assertIn("RPO", result.failure_reason)
        self.assertEqual(commands, [])

    def test_fails_when_recovered_database_is_not_writable(self):
        clock = Clock()

        def health(url):
            if "primary" in url:
                return {"status": "healthy", "database": {"writable": True}}
            if "secondary" in url:
                return {
                    "database": {
                        "status": "ok",
                        "role": "replica",
                        "replay_lag_seconds": 5,
                    }
                }
            return {
                "status": "healthy",
                "region": "secondary-cluster",
                "database": {"writable": False},
            }

        config = self.config()
        config.timeout_seconds = 20
        result = run_game_day(
            config,
            health=health,
            execute=lambda _command: None,
            monotonic=clock.monotonic,
            sleep=clock.sleep,
        )

        self.assertFalse(result.passed)
        self.assertIsNone(result.rto_actual_seconds)

    def test_reports_injection_failure_and_still_restores(self):
        commands = []

        def execute(command):
            commands.append(command)
            if command == "inject":
                raise RuntimeError("provider rejected request")

        def health(url):
            if "primary" in url:
                return {"status": "healthy", "database": {"writable": True}}
            return {
                "database": {
                    "status": "ok",
                    "role": "replica",
                    "replay_lag_seconds": 1,
                }
            }

        result = run_game_day(self.config(), health=health, execute=execute)

        self.assertFalse(result.passed)
        self.assertIn("injection", result.failure_reason.lower())
        self.assertEqual(commands, ["inject", "restore"])

    def test_writes_machine_and_human_readable_evidence(self):
        result = GameDayResult(
            mode="simulation",
            passed=True,
            rto_target_seconds=600,
            rto_actual_seconds=20,
            rpo_target_seconds=60,
            rpo_actual_seconds=12,
            secondary_region="secondary-cluster",
            failure_reason=None,
        )
        with tempfile.TemporaryDirectory() as directory:
            json_path = Path(directory) / "result.json"
            markdown_path = Path(directory) / "result.md"
            write_reports(result, json_path, markdown_path)

            self.assertIn('"passed": true', json_path.read_text())
            self.assertIn("does not certify production", markdown_path.read_text())


if __name__ == "__main__":
    unittest.main()
