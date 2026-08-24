---
name: work-automation-stop-gap
description: Gate the remaining steps of a work automation on this Mac being online and unlocked, then skip the run if the user's Google Calendar marks them out of office for the whole local day. Use when an automation needs this preflight or the user invokes work-automation-stop-gap.
---

# Work Automation Stop Gap

Run this gate before any downstream work. Continue only after both the laptop check and the Calendar check pass, in that order. A waiting, failed, unknown, or skipped result is never permission to continue.

This skill gates the current run; it does not create an automation, change its schedule, or disable future runs. Do not perform the gated work while waiting, including through another agent.

## 1. Wait for this laptop to be online and unlocked

Run [scripts/wait_for_laptop.py](scripts/wait_for_laptop.py) with Python 3 on the user's actual Mac, not a devbox, container, or cloud host. Resolve the script path relative to this `SKILL.md`.

The helper:

- Checks immediately, then waits five minutes between unsuccessful checks.
- Performs at most **60 checks total**, including the initial check, and enforces a **five-hour elapsed-time deadline**, including laptop sleep. With fast probes, check 60 occurs around 4 hours 55 minutes; do not add a 61st check to fill five hours.
- Requires a successful local HTTPS connection to `https://openai.com` and an explicitly unlocked, logged-in console session belonging to the user running the helper. Any completed HTTP response is sufficient for connectivity; TLS verification remains enabled. A missing lock property or probe error does not mean unlocked.
- Emits JSON progress and exits `0` with `status: laptop_ready` only when both conditions hold in the same check. This is not yet a pass for the full gate.
- Exits nonzero with `status: stop` on exhaustion, deadline, interruption, or an unsupported platform. Cancel all remaining steps of this run.

If the shell runtime sandboxes access to local session state or the HTTPS probe, request its normal host/elevated approval on the initial helper launch before starting or yielding a resumable process. Do not begin the helper sandboxed and defer an approval request into later polling: losing that approval transport can destroy the resumable session after its five-hour budget has started. If launch approval is unavailable or fails, stop this run without starting the helper; do not bypass the sandbox.

After any required launch approval succeeds, use one resumable shell execution session, yield promptly, and poll that same process with waits of at most 60 seconds. The helper sleeps in chunks of at most 60 seconds. Preserve the session ID, original start time, deadline, and attempt count across context compaction; never restart a fresh five-hour budget for the same run. If execution cannot be resumed or the runtime cannot wait reliably, stop the remaining steps and report the limitation. Do not invent a scheduled retry or install a background service. Never unlock the screen, keep the laptop awake, or change network settings.

The helper's `--check` flag performs a single diagnostic check without waiting. Do not use this flag as a replacement for the production retry loop.

## 2. Check today's Google Calendar for whole-day out of office

Only after `laptop_ready`:

1. Resolve **today at the time readiness passes**, using the laptop's current local date and timezone, not the date the automation started. Construct the half-open interval from today's midnight to tomorrow's midnight with the correct offset at each boundary; daylight-saving days are not always 24 hours.
2. Use the authenticated Google Calendar connector. Default to the user's `primary` calendar unless the user has specified another work calendar. Do not search coworkers' or team absence calendars as a substitute.
3. Discover the available read/search tools. With `google_calendar.search_events`, pass the calendar ID, explicit RFC3339 `time_min` and `time_max`, and the local IANA `timezone_str`. Leave `query` unset so custom-titled out-of-office events are not missed. Follow every `next_page_token` before deciding that no whole-day absence exists.
4. Evaluate the actual occurrences overlapping today, including multi-day events and recurring instances. Read event details when search results omit the event type or other decisive fields. The connector can expose `event_type`, `start`, and `end`; the raw API uses `eventType`, `start.date`/`start.dateTime`, and `end.date`/`end.dateTime`. If using the raw API, request expanded instances with `singleEvents=true` and exclude deleted events. Do not send raw API options to a connector that does not accept them.
5. Identify the user's own absence: prefer the structured `outOfOffice` event type regardless of title. An ordinary all-day event explicitly marking the user's own absence, such as `OOO`, `Out of office`, `PTO`, or `Vacation`, also counts when ownership and meaning are unambiguous. Do not mistake a coworker's absence, a holiday, working location, focus time, or a busy day for the user's out-of-office status. Ignore cancelled events and invitations the user declined.
6. Stop if the absence covers the whole local day. For date-only all-day events, `start_date <= today < end_date`; the end date is exclusive. For timestamped absence, require coverage from today's midnight through tomorrow's midnight. Include multi-day spans and merge touching/overlapping out-of-office intervals when their union covers the day. A partial-day absence alone does not stop this gate. Do not substitute assumed working hours for the whole day.

If Calendar access fails, pagination is incomplete, recurrence cannot be resolved, or an ambiguous candidate prevents determining whether the user is away all day, stop the remaining steps and report that the gate could not be verified. Do not interpret an error as an empty calendar.

Google's [event schema](https://developers.google.com/workspace/calendar/api/v3/reference/events) defines event types and exclusive ends; [event listing](https://developers.google.com/workspace/calendar/api/v3/reference/events/list) documents overlap bounds, pagination, and recurrence expansion.

## 3. Continue or stop

- **Continue:** Laptop readiness passed and a complete Calendar check found no whole-day absence. Briefly report the gate passed, then perform only the original automation's authorized remaining steps. If there are no remaining steps, report the result without inventing work.
- **Stop — out of office:** Briefly report the local date and matching absence, then end this run without performing any remaining steps.
- **Stop — laptop unavailable:** Report exhausted checks or the deadline and the last observed readiness state, then end this run.
- **Stop — unable to verify:** State the missing access, tool, or evidence and end this run. Do not claim either check passed.

These decisions cancel only the current run's downstream steps, not the recurring automation itself.
