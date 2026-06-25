#!/usr/bin/env python3
"""Schedule a one-shot macOS LaunchAgent that unarchives a Codex session."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import plistlib
import re
import selectors
import shutil
import subprocess
import sys
import time
from collections import deque
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
LABEL_PREFIX = "com.openai.codex.snooze"
MAX_AHEAD = dt.timedelta(days=366)
CLOCK_PREFIX = "⏰ "
APP_SERVER_REQUEST_TIMEOUT_SECONDS = 30.0
FOLLOW_UP_TIMEOUT_SECONDS = 60.0 * 60.0
DISABLED_APP_SERVER_FEATURES = (
    "multi_agent",
    "multi_agent_mode",
    "collaboration_modes",
)


def fail(message: str) -> "None":
    raise SystemExit(message)


def validate_thread_id(thread_id: str) -> str:
    if not UUID_RE.fullmatch(thread_id):
        fail("thread ID must be a UUID")
    return thread_id.lower()


def parse_wake_at(value: str) -> dt.datetime:
    try:
        wake_at = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        fail(f"invalid --wake-at: {exc}")
    if wake_at.tzinfo is None:
        fail("--wake-at must include a UTC offset")
    if wake_at.second or wake_at.microsecond:
        wake_at = (wake_at + dt.timedelta(minutes=1)).replace(second=0, microsecond=0)
    return wake_at


def label_for(thread_id: str) -> str:
    return f"{LABEL_PREFIX}.{thread_id}"


def plist_for(thread_id: str) -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{label_for(thread_id)}.plist"


def launchd_domain() -> str:
    return f"gui/{os.getuid()}"


def run_launchctl(*arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["launchctl", *arguments],
        check=check,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def bootout(label: str) -> None:
    run_launchctl("bootout", f"{launchd_domain()}/{label}", check=False)


def cleanup(label: str, plist_path: Path) -> None:
    try:
        plist_path.unlink(missing_ok=True)
    finally:
        bootout(label)


def codex_path() -> str:
    path = shutil.which("codex")
    if not path:
        fail("could not find codex on PATH")
    return str(Path(path).resolve())


class AppServerError(RuntimeError):
    pass


class AppServerClient:
    """Minimal newline-delimited JSON-RPC client for a detached wake-up."""

    def __init__(self, codex: str) -> None:
        command = [codex]
        for feature in DISABLED_APP_SERVER_FEATURES:
            command.extend(["--disable", feature])
        command.extend(["app-server", "--stdio"])
        self.process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
        )
        if self.process.stdin is None or self.process.stdout is None or self.process.stderr is None:
            raise AppServerError("failed to open app-server stdio pipes")
        self._selector = selectors.DefaultSelector()
        self._selector.register(self.process.stdout, selectors.EVENT_READ, "stdout")
        self._selector.register(self.process.stderr, selectors.EVENT_READ, "stderr")
        self._next_id = 1
        self._responses: dict[int, dict[str, Any]] = {}
        self._notifications: deque[dict[str, Any]] = deque()
        self._stderr_tail: deque[str] = deque(maxlen=10)
        self._stdout_buffer = b""

    def initialize(self) -> None:
        self.request(
            "initialize",
            {
                "clientInfo": {
                    "name": "snooze",
                    "title": "Snooze Wake-Up",
                    "version": "1.0.0",
                },
                "capabilities": {
                    "experimentalApi": True,
                    "optOutNotificationMethods": [
                        "codex/event/agent_message_content_delta",
                        "codex/event/agent_message_delta",
                        "codex/event/agent_reasoning_delta",
                        "codex/event/exec_command_output_delta",
                        "codex/event/reasoning_content_delta",
                        "item/agentMessage/delta",
                        "item/commandExecution/outputDelta",
                        "item/reasoning/summaryTextDelta",
                        "item/reasoning/textDelta",
                    ],
                },
            },
        )
        self.notify("initialized", {})

    def notify(self, method: str, params: dict[str, Any]) -> None:
        self._send({"method": method, "params": params})

    def request(
        self,
        method: str,
        params: dict[str, Any],
        timeout_seconds: float = APP_SERVER_REQUEST_TIMEOUT_SECONDS,
    ) -> dict[str, Any]:
        request_id = self._next_id
        self._next_id += 1
        self._send({"id": request_id, "method": method, "params": params})
        deadline = time.monotonic() + timeout_seconds
        while request_id not in self._responses:
            self._dispatch(self._read_message(deadline))
        response = self._responses.pop(request_id)
        error = response.get("error")
        if error is not None:
            raise AppServerError(f"{method} failed: {json.dumps(error, sort_keys=True)}")
        result = response.get("result")
        if result is None:
            return {}
        if not isinstance(result, dict):
            raise AppServerError(f"{method} returned a non-object result")
        return result

    def next_notification(self, timeout_seconds: float) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_seconds
        while not self._notifications:
            self._dispatch(self._read_message(deadline))
        return self._notifications.popleft()

    def close(self) -> None:
        self._selector.close()
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)

    def _send(self, message: dict[str, Any]) -> None:
        if self.process.stdin is None:
            raise AppServerError("app-server stdin is unavailable")
        try:
            payload = (json.dumps(message, separators=(",", ":")) + "\n").encode()
            self.process.stdin.write(payload)
            self.process.stdin.flush()
        except BrokenPipeError as exc:
            raise AppServerError(self._process_failure("app-server closed stdin")) from exc

    def _read_message(self, deadline: float) -> dict[str, Any]:
        while True:
            if b"\n" in self._stdout_buffer:
                line, self._stdout_buffer = self._stdout_buffer.split(b"\n", 1)
                try:
                    message = json.loads(line.decode())
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise AppServerError(f"invalid app-server JSON: {line!r}") from exc
                if not isinstance(message, dict):
                    raise AppServerError("app-server returned a non-object message")
                return message
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("timed out waiting for app-server")
            ready = self._selector.select(remaining)
            if not ready:
                raise TimeoutError("timed out waiting for app-server")
            for key, _ in ready:
                chunk = os.read(key.fileobj.fileno(), 4096)
                if not chunk:
                    try:
                        self._selector.unregister(key.fileobj)
                    except KeyError:
                        pass
                    if key.data == "stdout":
                        raise AppServerError(self._process_failure("app-server closed stdout"))
                    continue
                if key.data == "stderr":
                    text = chunk.decode(errors="replace")
                    self._stderr_tail.extend(text.rstrip().splitlines())
                    print(text, end="", file=sys.stderr)
                    continue
                self._stdout_buffer += chunk

    def _dispatch(self, message: dict[str, Any]) -> None:
        if "id" in message and "method" in message:
            method = message.get("method")
            self._send(
                {
                    "id": message["id"],
                    "error": {
                        "code": -32000,
                        "message": f"detached snooze client cannot handle server request {method}",
                    },
                }
            )
            return
        if "id" in message:
            response_id = message["id"]
            if isinstance(response_id, int):
                self._responses[response_id] = message
            return
        if "method" in message:
            self._notifications.append(message)

    def _process_failure(self, prefix: str) -> str:
        code = self.process.poll()
        detail = f"; exit code {code}" if code is not None else ""
        if self._stderr_tail:
            detail += "; stderr: " + " | ".join(self._stderr_tail)
        return prefix + detail


def remove_clock_prefix(client: AppServerClient, thread_id: str) -> bool:
    result = client.request(
        "thread/read",
        {"threadId": thread_id, "includeTurns": False},
    )
    thread = result.get("thread")
    if not isinstance(thread, dict):
        raise AppServerError("thread/read did not return thread metadata")
    title = thread.get("name")
    if not isinstance(title, str) or not title.startswith(CLOCK_PREFIX):
        return False
    client.request(
        "thread/name/set",
        {"threadId": thread_id, "name": title[len(CLOCK_PREFIX) :]},
    )
    return True


def run_follow_up(client: AppServerClient, thread_id: str, prompt: str) -> str:
    client.request(
        "thread/resume",
        {
            "threadId": thread_id,
            "excludeTurns": True,
            "approvalPolicy": "never",
        },
    )
    result = client.request(
        "turn/start",
        {
            "threadId": thread_id,
            "input": [{"type": "text", "text": prompt}],
            "approvalPolicy": "never",
        },
    )
    turn = result.get("turn")
    if not isinstance(turn, dict) or not isinstance(turn.get("id"), str):
        raise AppServerError("turn/start did not return a turn ID")
    turn_id = turn["id"]
    deadline = time.monotonic() + FOLLOW_UP_TIMEOUT_SECONDS
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(f"timed out waiting for follow-up turn {turn_id}")
        notification = client.next_notification(remaining)
        method = notification.get("method")
        params = notification.get("params")
        if not isinstance(params, dict) or params.get("threadId") != thread_id:
            continue
        if method == "error" and params.get("turnId") == turn_id:
            if not params.get("willRetry", False):
                raise AppServerError(
                    f"follow-up turn {turn_id} failed: "
                    f"{json.dumps(params.get('error'), sort_keys=True)}"
                )
            continue
        if method != "turn/completed":
            continue
        completed_turn = params.get("turn")
        if not isinstance(completed_turn, dict) or completed_turn.get("id") != turn_id:
            continue
        status = completed_turn.get("status")
        if status != "completed":
            raise AppServerError(f"follow-up turn {turn_id} ended with status {status}")
        return turn_id


def build_plist(
    *,
    thread_id: str,
    wake_at: dt.datetime,
    timezone: str,
    label: str,
    plist_path: Path,
    codex: str,
    follow_up_prompt: str | None,
) -> dict[str, object]:
    try:
        requested_zone = ZoneInfo(timezone)
    except Exception as exc:
        fail(f"invalid --timezone: {exc}")

    # LaunchAgent calendar fields use the Mac's local timezone. Preserve the
    # absolute instant in --wake-at, but convert calendar fields for launchd.
    requested_local = wake_at.astimezone(requested_zone)
    host_local = requested_local.astimezone()
    script_path = str(Path(__file__).resolve())
    python_path = str(Path(sys.executable).resolve())
    log_stem = f"/tmp/codex-snooze-{thread_id[:8]}"
    environment = {
        "HOME": str(Path.home()),
        "PATH": os.environ.get("PATH", "/usr/bin:/bin:/usr/sbin:/sbin"),
        "CODEX_HOME": os.environ.get("CODEX_HOME", str(Path.home() / ".codex")),
    }
    program_arguments = [
            python_path,
            script_path,
            "run",
            "--thread-id",
            thread_id,
            "--wake-at",
            wake_at.isoformat(),
            "--timezone",
            timezone,
            "--label",
            label,
            "--plist",
            str(plist_path),
            "--codex",
            codex,
        ]
    if follow_up_prompt:
        program_arguments.extend(["--follow-up-prompt", follow_up_prompt])
    return {
        "Label": label,
        "ProgramArguments": program_arguments,
        # Run once whenever the agent is loaded. Before the target, run()
        # returns without cleanup; after a missed shutdown/login, it catches
        # up immediately instead of waiting for next year's calendar match.
        "RunAtLoad": True,
        "StartCalendarInterval": {
            "Month": host_local.month,
            "Day": host_local.day,
            "Hour": host_local.hour,
            "Minute": host_local.minute,
        },
        "EnvironmentVariables": environment,
        "StandardOutPath": f"{log_stem}.out",
        "StandardErrorPath": f"{log_stem}.err",
    }


def schedule(args: argparse.Namespace) -> None:
    thread_id = validate_thread_id(args.thread_id)
    wake_at = parse_wake_at(args.wake_at)
    now = dt.datetime.now(dt.timezone.utc)
    wake_utc = wake_at.astimezone(dt.timezone.utc)
    if wake_utc <= now:
        fail("--wake-at must be in the future")
    if wake_utc - now > MAX_AHEAD:
        fail("--wake-at must be no more than 366 days in the future")

    label = label_for(thread_id)
    plist_path = plist_for(thread_id)
    plist = build_plist(
        thread_id=thread_id,
        wake_at=wake_at,
        timezone=args.timezone,
        label=label,
        plist_path=plist_path,
        codex=codex_path(),
        follow_up_prompt=args.follow_up_prompt,
    )
    if args.dry_run:
        sys.stdout.buffer.write(plistlib.dumps(plist, fmt=plistlib.FMT_XML))
        return

    plist_path.parent.mkdir(parents=True, exist_ok=True)
    bootout(label)
    temporary_path = plist_path.with_suffix(".plist.tmp")
    with temporary_path.open("wb") as output:
        plistlib.dump(plist, output, fmt=plistlib.FMT_XML)
    os.replace(temporary_path, plist_path)
    try:
        run_launchctl("bootstrap", launchd_domain(), str(plist_path))
    except subprocess.CalledProcessError as exc:
        plist_path.unlink(missing_ok=True)
        details = (exc.stderr or exc.stdout or str(exc)).strip()
        fail(f"launchctl bootstrap failed: {details}")

    print(
        json.dumps(
            {
                "label": label,
                "plist": str(plist_path),
                "wakeAt": wake_at.isoformat(),
                "timezone": args.timezone,
                "hasFollowUpPrompt": bool(args.follow_up_prompt),
            }
        )
    )


def cancel(args: argparse.Namespace) -> None:
    thread_id = validate_thread_id(args.thread_id)
    label = label_for(thread_id)
    plist_path = plist_for(thread_id)
    cleanup(label, plist_path)
    print(json.dumps({"canceled": label}))


def run(args: argparse.Namespace) -> None:
    thread_id = validate_thread_id(args.thread_id)
    wake_at = parse_wake_at(args.wake_at)
    now = dt.datetime.now(dt.timezone.utc)
    if now + dt.timedelta(seconds=30) < wake_at.astimezone(dt.timezone.utc):
        # Protect against an early calendar match; keep the job loaded for the
        # intended local date instead of unarchiving early.
        return

    client: AppServerClient | None = None
    errors: list[str] = []
    try:
        client = AppServerClient(args.codex)
        client.initialize()
        client.request("thread/unarchive", {"threadId": thread_id})
        print(json.dumps({"threadId": thread_id, "unarchived": True}))

        try:
            title_updated = remove_clock_prefix(client, thread_id)
            print(json.dumps({"threadId": thread_id, "titleUpdated": title_updated}))
        except (AppServerError, TimeoutError) as exc:
            message = f"title cleanup failed: {exc}"
            print(message, file=sys.stderr)
            errors.append(message)

        if args.follow_up_prompt:
            try:
                turn_id = run_follow_up(client, thread_id, args.follow_up_prompt)
                print(
                    json.dumps(
                        {
                            "threadId": thread_id,
                            "followUpCompleted": True,
                            "turnId": turn_id,
                        }
                    )
                )
            except (AppServerError, TimeoutError) as exc:
                message = f"follow-up failed: {exc}"
                print(message, file=sys.stderr)
                errors.append(message)
    except (AppServerError, TimeoutError, OSError) as exc:
        message = f"wake-up failed: {exc}"
        print(message, file=sys.stderr)
        errors.append(message)
    finally:
        if client is not None:
            client.close()
        cleanup(args.label, Path(args.plist))
    raise SystemExit(1 if errors else 0)


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)

    schedule_parser = commands.add_parser("schedule")
    schedule_parser.add_argument("--thread-id", required=True)
    schedule_parser.add_argument("--wake-at", required=True)
    schedule_parser.add_argument("--timezone", required=True)
    schedule_parser.add_argument("--follow-up-prompt")
    schedule_parser.add_argument("--dry-run", action="store_true")
    schedule_parser.set_defaults(func=schedule)

    cancel_parser = commands.add_parser("cancel")
    cancel_parser.add_argument("--thread-id", required=True)
    cancel_parser.set_defaults(func=cancel)

    run_parser = commands.add_parser("run")
    run_parser.add_argument("--thread-id", required=True)
    run_parser.add_argument("--wake-at", required=True)
    run_parser.add_argument("--timezone", required=True)
    run_parser.add_argument("--label", required=True)
    run_parser.add_argument("--plist", required=True)
    run_parser.add_argument("--codex", required=True)
    run_parser.add_argument("--follow-up-prompt")
    run_parser.set_defaults(func=run)
    return root


def main() -> None:
    args = parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
