#!/usr/bin/env python3
"""Read-only macOS readiness gate. Calendar must still be checked by the caller."""

import argparse
import json
import os
import plistlib
import subprocess
import sys
import time


MAX_CHECKS = 60
RETRY_SECONDS = 5 * 60
DEADLINE_SECONDS = 5 * 60 * 60


def session_unlocked(document, uid):
    """Require positive evidence of an unlocked console owned by this user."""
    if isinstance(document, list) and len(document) == 1:
        document = document[0]
    if not isinstance(document, dict):
        raise ValueError("Unexpected IORegistry document")
    locked = document.get("IOConsoleLocked")
    if not isinstance(locked, bool):
        raise ValueError("Missing or unrecognized IOConsoleLocked state")
    if locked:
        return False
    users = document.get("IOConsoleUsers")
    if not isinstance(users, list):
        raise ValueError("Missing console session information")
    return any(
        isinstance(user, dict)
        and user.get("kCGSSessionUserIDKey") == uid
        and user.get("kCGSSessionOnConsoleKey") is True
        and user.get("kCGSessionLoginDoneKey") is True
        for user in users
    )


def probe_laptop():
    result = {"online": None, "unlocked": None, "errors": []}
    try:
        response = subprocess.run(
            [
                "/usr/bin/curl", "-q", "--silent", "--show-error",
                "--output", "/dev/null", "--write-out", "%{http_code}",
                "--connect-timeout", "5", "--max-time", "10",
                "--proto", "=https", "https://www.google.com/generate_204",
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        # Do not follow a captive-portal redirect or weaken TLS verification.
        result["online"] = response.returncode == 0 and response.stdout.strip() == "204"
        if not result["online"]:
            result["errors"].append(f"HTTPS probe failed (curl exit {response.returncode})")
    except (OSError, subprocess.SubprocessError) as error:
        result["errors"].append(f"HTTPS probe unavailable: {type(error).__name__}")

    # Read the lock state after the network probe to avoid using a stale unlock.
    try:
        response = subprocess.run(
            ["/usr/sbin/ioreg", "-n", "Root", "-d", "1", "-a"],
            capture_output=True,
            timeout=5,
            check=True,
        )
        document = plistlib.loads(response.stdout)
        result["unlocked"] = session_unlocked(document, os.getuid())
    except (OSError, subprocess.SubprocessError, ValueError, plistlib.InvalidFileException) as error:
        result["errors"].append(f"Lock probe unavailable: {type(error).__name__}")
    return result


def is_ready(result):
    return result.get("online") is True and result.get("unlocked") is True


def emit_json(record):
    print(json.dumps(record), flush=True)


def wait_for_laptop(
    probe=probe_laptop,
    emit=emit_json,
    sleep=time.sleep,
    wall_clock=time.time,
    steady_clock=time.monotonic,
):
    started_at = wall_clock()
    started_steady = steady_clock()
    last = {"online": None, "unlocked": None, "errors": []}
    attempt = 0

    def elapsed():
        # Wall time includes macOS sleep; monotonic time resists clock rollback.
        return max(wall_clock() - started_at, steady_clock() - started_steady)

    def report(status, reason):
        emit({
            **last,
            "status": status,
            "reason": reason,
            "attempt": attempt,
            "max_checks": MAX_CHECKS,
            "started_at_epoch": started_at,
            "deadline_epoch": started_at + DEADLINE_SECONDS,
            "elapsed_seconds": round(elapsed(), 3),
        })

    try:
        while attempt < MAX_CHECKS:
            if elapsed() >= DEADLINE_SECONDS:
                report("stop", "deadline_reached")
                return 1
            attempt += 1
            last = probe()
            if elapsed() >= DEADLINE_SECONDS:
                report("stop", "deadline_reached")
                return 1
            if is_ready(last):
                report("laptop_ready", "online_and_unlocked")
                return 0
            if attempt == MAX_CHECKS:
                report("stop", "checks_exhausted")
                return 1
            report("waiting", "laptop_not_ready")
            next_check = elapsed() + RETRY_SECONDS
            while elapsed() < min(next_check, DEADLINE_SECONDS):
                remaining = min(next_check, DEADLINE_SECONDS) - elapsed()
                if remaining > 0:
                    sleep(min(60, remaining))
    except KeyboardInterrupt:
        report("stop", "interrupted")
        return 130
    return 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="One diagnostic probe; no waiting")
    args = parser.parse_args()
    if sys.platform != "darwin":
        emit_json({"status": "stop", "reason": "requires_local_macos"})
        return 2
    if args.check:
        result = probe_laptop()
        ready = is_ready(result)
        emit_json({**result, "status": "laptop_ready" if ready else "not_ready"})
        return 0 if ready else 1
    return wait_for_laptop()


if __name__ == "__main__":
    sys.exit(main())
