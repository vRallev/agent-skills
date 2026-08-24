"""Run with: python3 -B -m unittest discover -s <skill>/scripts -p 'test_*.py'."""

import copy
import plistlib
import subprocess
import unittest
from unittest.mock import Mock, patch

import wait_for_laptop as gate


READY = {"online": True, "unlocked": True, "errors": []}
UNAVAILABLE = {"online": False, "unlocked": False, "errors": []}
SESSION = {
    "IOConsoleLocked": False,
    "IOConsoleUsers": [{
        "kCGSSessionUserIDKey": 501,
        "kCGSSessionOnConsoleKey": True,
        "kCGSessionLoginDoneKey": True,
    }],
}


class Clock:
    def __init__(self):
        self.now = 0
        self.sleeps = []

    def read(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


class SessionTests(unittest.TestCase):
    def test_unlocked_logged_in_console(self):
        self.assertTrue(gate.session_unlocked(SESSION, 501))
        self.assertTrue(gate.session_unlocked([SESSION], 501))

    def test_locked_or_inactive_sessions_do_not_pass(self):
        variants = []
        locked = copy.deepcopy(SESSION)
        locked["IOConsoleLocked"] = True
        variants.append(locked)
        for field, value in (
            ("kCGSSessionUserIDKey", 502),
            ("kCGSSessionOnConsoleKey", False),
            ("kCGSessionLoginDoneKey", False),
        ):
            document = copy.deepcopy(SESSION)
            document["IOConsoleUsers"][0][field] = value
            variants.append(document)
        variants.append({"IOConsoleLocked": False, "IOConsoleUsers": []})
        for document in variants:
            with self.subTest(document=document):
                self.assertFalse(gate.session_unlocked(document, 501))

    def test_missing_or_invalid_state_is_unknown_not_unlocked(self):
        for document in ({}, [], {"IOConsoleLocked": "false"}, {"IOConsoleLocked": False}):
            with self.subTest(document=document), self.assertRaises(ValueError):
                gate.session_unlocked(document, 501)


class ProbeTests(unittest.TestCase):
    def test_https_and_lock_must_both_pass(self):
        for code, body, expected_online in ((0, "204", True), (0, "302", False), (6, "000", False)):
            with self.subTest(code=code, body=body):
                results = [
                    subprocess.CompletedProcess([], code, stdout=body),
                    subprocess.CompletedProcess([], 0, stdout=plistlib.dumps(SESSION)),
                ]
                with patch.object(gate.subprocess, "run", side_effect=results), patch.object(gate.os, "getuid", return_value=501):
                    result = gate.probe_laptop()
                self.assertIs(result["online"], expected_online)
                self.assertIs(result["unlocked"], True)
                self.assertEqual(gate.is_ready(result), expected_online)

    def test_probe_errors_fail_closed(self):
        for error in (OSError(), subprocess.TimeoutExpired("probe", 5), subprocess.CalledProcessError(1, "probe")):
            with self.subTest(error=error), patch.object(gate.subprocess, "run", side_effect=error):
                result = gate.probe_laptop()
                self.assertFalse(gate.is_ready(result))
                self.assertIsNone(result["unlocked"])

    def test_missing_lock_key_fails_closed(self):
        results = [
            subprocess.CompletedProcess([], 0, stdout="204"),
            subprocess.CompletedProcess([], 0, stdout=plistlib.dumps({})),
        ]
        with patch.object(gate.subprocess, "run", side_effect=results):
            result = gate.probe_laptop()
        self.assertIsNone(result["unlocked"])
        self.assertFalse(gate.is_ready(result))


class RetryTests(unittest.TestCase):
    def run_gate(self, probe, clock=None, wall_clock=None):
        clock = clock or Clock()
        records = []
        code = gate.wait_for_laptop(
            probe=probe, emit=records.append, sleep=clock.sleep,
            wall_clock=wall_clock or clock.read, steady_clock=clock.read,
        )
        return code, records, clock

    def test_immediate_success_does_not_sleep(self):
        code, records, clock = self.run_gate(lambda: READY)
        self.assertEqual(code, 0)
        self.assertEqual(records[-1]["status"], "laptop_ready")
        self.assertEqual(clock.sleeps, [])

    def test_requires_online_and_unlocked_in_the_same_check(self):
        probe = Mock(side_effect=[
            {"online": True, "unlocked": False},
            {"online": False, "unlocked": True},
            READY,
        ])
        code, records, clock = self.run_gate(probe)
        self.assertEqual(code, 0)
        self.assertEqual([r["elapsed_seconds"] for r in records], [0, 300, 600])
        self.assertLessEqual(max(clock.sleeps), 60)

    def test_stops_after_exactly_sixty_checks(self):
        probe = Mock(return_value=UNAVAILABLE)
        code, records, clock = self.run_gate(probe)
        self.assertEqual(code, 1)
        self.assertEqual(probe.call_count, 60)
        self.assertEqual(clock.now, 59 * 300)
        self.assertEqual(records[-1]["reason"], "checks_exhausted")

    def test_unknown_state_never_passes(self):
        code, records, _ = self.run_gate(lambda: {"online": None, "unlocked": None})
        self.assertEqual(code, 1)
        self.assertEqual(records[-1]["reason"], "checks_exhausted")

    def test_sleep_past_deadline_stops_without_a_new_probe(self):
        clock = Clock()
        clock.sleep = lambda _: setattr(clock, "now", 18001)
        probe = Mock(return_value=UNAVAILABLE)
        code, records, _ = self.run_gate(probe, clock)
        self.assertEqual(code, 1)
        self.assertEqual(probe.call_count, 1)
        self.assertEqual(records[-1]["reason"], "deadline_reached")

    def test_wall_clock_includes_sleep_when_monotonic_clock_does_not(self):
        clock = Clock()
        probe = Mock(return_value=UNAVAILABLE)
        wall = lambda: 0 if clock.now == 0 else 18001
        code, records, _ = self.run_gate(probe, clock, wall)
        self.assertEqual(code, 1)
        self.assertEqual(probe.call_count, 1)
        self.assertEqual(records[-1]["reason"], "deadline_reached")

    def test_readiness_after_deadline_cannot_pass(self):
        clock = Clock()

        def late_probe():
            clock.now = 18000
            return READY

        code, records, _ = self.run_gate(late_probe, clock)
        self.assertEqual(code, 1)
        self.assertEqual(records[-1]["reason"], "deadline_reached")

    def test_interruption_stops_the_gate(self):
        code, records, _ = self.run_gate(Mock(side_effect=KeyboardInterrupt))
        self.assertEqual(code, 130)
        self.assertEqual(records[-1]["reason"], "interrupted")

    def test_unsupported_platform_never_probes(self):
        with patch.object(gate.sys, "platform", "linux"), patch.object(gate.sys, "argv", ["gate"]), patch.object(gate, "emit_json") as emit, patch.object(gate, "probe_laptop") as probe:
            self.assertEqual(gate.main(), 2)
        probe.assert_not_called()
        self.assertEqual(emit.call_args.args[0]["reason"], "requires_local_macos")


if __name__ == "__main__":
    unittest.main()
