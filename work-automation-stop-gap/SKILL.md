---
name: work-automation-stop-gap
description: Wait for this Mac to be online and unlocked before a work automation continues. Then skip the run if the user's Google Calendar marks them out of office for the whole local day. Use when an automation needs this gate or the user invokes work-automation-stop-gap.
---

# Work Automation Stop Gap

Run this gate before any downstream work. Check the laptop before Calendar. Continue only after both checks pass. A waiting, failed, unknown, or skipped result does not permit work to continue.

This skill gates the current run. It does not create an automation, change its schedule, or disable future runs. While waiting, do not perform the gated work, including through another agent.

## 1. Wait for this laptop to be online and unlocked

Resolve [scripts/wait_for_laptop.py](scripts/wait_for_laptop.py) relative to this `SKILL.md`. Run it with Python 3 on the user's actual Mac. Do not use a devbox, container, or cloud host.

The helper:

- Checks immediately. After an unsuccessful check, it waits five minutes.
- Performs at most **60 checks total**, including the initial check. It enforces a **five-hour elapsed-time deadline**, including laptop sleep. With fast probes, check 60 occurs around 4 hours 55 minutes. Do not add a 61st check to fill five hours.
- Requires a successful local HTTPS connection to `https://openai.com`. Any completed HTTP response proves connectivity. TLS verification remains enabled.
- Requires an explicitly unlocked, logged-in console session for the user who runs the helper. A missing lock property or probe error does not prove that the session is unlocked.
- Emits JSON progress. Only when both conditions hold in the same check, it exits `0` with `status: laptop_ready`. The full gate has not yet passed.
- On exhaustion, deadline, interruption, or an unsupported platform, it exits nonzero with `status: stop`. Cancel all remaining steps of this run.

If the shell runtime sandboxes local session state or the HTTPS probe, request its normal host/elevated approval for the initial helper launch. Get approval before starting or yielding a resumable process. Do not launch the helper sandboxed and defer approval to later polling. Losing the approval transport can destroy the resumable session after its five-hour budget starts. If launch approval is unavailable or fails, stop this run without starting the helper. Do not bypass the sandbox.

After any required launch approval succeeds, use one resumable shell execution session. Yield promptly. Poll the same process with waits of at most 60 seconds. The helper sleeps in chunks of at most 60 seconds.

Across context compaction, preserve the session ID, original start time, deadline, and attempt count. Never restart a five-hour budget for the same run.

If you cannot resume execution or the runtime cannot wait reliably, stop the remaining steps. Report the limitation. Do not invent a scheduled retry or install a background service. Never unlock the screen, keep the laptop awake, or change network settings.

The helper's `--check` flag performs one diagnostic check without waiting. Do not use it instead of the production retry loop.

## 2. Check today's Google Calendar for whole-day out of office

After the helper returns `laptop_ready`:

1. Resolve **today at the time readiness passes**. Use the laptop's current local date and timezone. Do not use the date the automation started. Construct the half-open interval from today's midnight to tomorrow's midnight. Use the correct offset at each boundary. Daylight-saving days are not always 24 hours.
2. Use the authenticated Google Calendar connector. If the user specified another work calendar, use it. Otherwise, use the user's `primary` calendar. Do not substitute coworkers' or team absence calendars.
3. Discover the available read/search tools. With `google_calendar.search_events`, pass the calendar ID, explicit RFC3339 `time_min` and `time_max`, and the local IANA `timezone_str`. Leave `query` unset to include events with custom out-of-office titles. Before deciding that no whole-day absence exists, follow every `next_page_token`.
4. Evaluate occurrences that overlap today, including multi-day events and recurring instances. If search results omit the event type or other decisive fields, read event details. The connector can expose `event_type`, `start`, and `end`. The raw API uses `eventType`, `start.date`/`start.dateTime`, and `end.date`/`end.dateTime`. If you use the raw API, request expanded instances with `singleEvents=true`. For raw API results, exclude deleted events. Do not send raw API options to a connector that does not accept them.
5. Identify the user's own absence. Prefer the structured `outOfOffice` event type regardless of title. If ownership and meaning are unambiguous, an ordinary all-day event that explicitly marks the user's own absence also counts. Examples include `OOO`, `Out of office`, `PTO`, or `Vacation`. Do not treat a coworker's absence, a holiday, working location, focus time, or a busy day as the user's out-of-office status. Ignore cancelled events and invitations the user declined.
6. Check whether the absence covers the whole local day. For date-only all-day events, use `start_date <= today < end_date`. The end date is exclusive. For timestamped absence, require coverage from today's midnight through tomorrow's midnight. Include multi-day spans. Merge touching or overlapping out-of-office intervals when their union covers the day. A partial-day absence alone does not stop this gate. Do not use assumed working hours instead of the whole day. If the absence covers the whole local day, stop.

If Calendar access fails, pagination is incomplete, recurrence cannot be resolved, or an ambiguous candidate prevents a whole-day absence decision, stop the remaining steps. Report that you could not verify the gate. Do not treat an error as an empty calendar.

Google's [event schema](https://developers.google.com/workspace/calendar/api/v3/reference/events) defines event types and exclusive ends. [Event listing](https://developers.google.com/workspace/calendar/api/v3/reference/events/list) documents overlap bounds, pagination, and recurrence expansion.

## 3. Continue or stop

- **Continue:** Laptop readiness passed and a complete Calendar check found no whole-day absence. Briefly report that the gate passed. Perform only the original automation's authorized remaining steps. If there are no remaining steps, report the result. Do not invent work.
- **Stop — out of office:** Briefly report the local date and matching absence. End this run without performing remaining steps.
- **Stop — laptop unavailable:** Report exhausted checks or the deadline and the last observed readiness state. End this run.
- **Stop — unable to verify:** State the missing access, tool, or evidence. End this run. Do not claim that either check passed.

These decisions cancel only the current run's downstream steps. They do not cancel the recurring automation.
