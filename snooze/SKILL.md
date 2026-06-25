---
name: snooze
description: Archive the current Codex conversation or session and schedule a one-time local-time wake-up that unarchives the same thread. Use when the user invokes /snooze or asks to snooze, hide, or archive this conversation until later, with a duration such as "for two days" or a future local timestamp such as "until 9pm on Thursday".
---

# Snooze

Archive the current thread only after an OS-level one-time wake-up has been scheduled successfully.

## Workflow

1. Require macOS.
   - Check the runtime platform first. If it is not already known, run `uname -s`.
   - Continue only when the result is `Darwin`.
   - Otherwise show: `Snooze requires macOS LaunchAgents and is not supported on this platform.` Then stop before parsing time, changing the title, scheduling anything, or archiving the thread.

2. Require a wake time.
   - Accept a relative duration, for example `/snooze for two days`, `/snooze for 90 minutes`, or `/snooze until tomorrow morning`.
   - Accept a local wall-clock target, for example `/snooze until 9pm on Thursday` or `/snooze until July 2 at 10:30am`.
   - Accept an optional follow-up after a clear separator such as `. Then`, `, then`, or `; then`. For example: `/snooze until 9am. Then try the failed action again` or `/snooze for 10min, then fetch the latest news`.
   - Resolve the time from the text before the separator. Preserve the text after `then` as the follow-up prompt without executing it now.
   - If the request has no duration or target time, ask: `How long should I snooze this conversation?` Then stop without scheduling or archiving anything.
   - If the user writes `then` but provides no follow-up text, ask one concise clarification and stop.
   - If the phrase cannot be resolved to one future instant, ask one concise clarification and stop.

3. Resolve the wake instant in the user's current local timezone.
   - Use the timezone and current local date/time supplied by the runtime; do not silently assume UTC.
   - Interpret days, weeks, months, and named dates as local calendar arithmetic. Interpret hours and minutes as elapsed time.
   - For a weekday without a date, choose the next future occurrence: use today only when the named time is still ahead; otherwise use the following week.
   - For an explicit date that is already past, ask for a future time instead of guessing.
   - Preserve the resolved IANA timezone and timezone abbreviation in the confirmation. Round up to the next schedulable minute if necessary; never wake earlier than requested.
   - Ask for clarification if daylight-saving rules make the requested local wall time nonexistent or genuinely ambiguous.

4. Capture the active conversation/session ID.
   - Use the current thread ID supplied by the runtime or invocation context. If needed, read only `CODEX_THREAD_ID` with `printenv CODEX_THREAD_ID`; never dump the full environment.
   - Treat the ID as required input; do not guess from a title or pick a thread from a search result.
   - If the runtime does not expose the current ID, ask the user to provide it and stop without changing state.

5. Create a detached one-shot wake-up before archiving.
   - Do not use a Codex heartbeat or cron automation. Heartbeats are attached to the target thread, and Codex cron accepts only limited repeating schedule shapes; neither is reliable for an archived thread at an arbitrary exact time.
   - Run `scripts/schedule_snooze.py schedule --thread-id <current thread ID> --wake-at <resolved ISO-8601 instant with offset> --timezone <IANA timezone>`. When the user supplied a follow-up, append `--follow-up-prompt <verbatim follow-up prompt>`.
   - Request escalation for this command: it writes a per-user LaunchAgent and registers it with `launchctl`.
   - The helper schedules one native macOS calendar trigger that starts a short-lived `codex app-server --stdio` client with `multi_agent`, `multi_agent_mode`, and `collaboration_modes` disabled. Through App Server JSON-RPC it unarchives the thread, reads its current title, removes one leading `⏰ ` with `thread/name/set`, and starts the optional follow-up as a new turn. It then removes its own LaunchAgent.
   - Do not ask a resumed model turn to remove the title. Dynamic Codex app tools are unavailable in `codex exec` mode; title cleanup must use App Server `thread/read` and `thread/name/set` directly.
   - The helper also enables `RunAtLoad`. Its absolute-time guard exits harmlessly before the target, but catches up immediately after a reboot or login that happened after the target time.
   - Pass a wake instant no more than 366 days in the future. If the user asks for a farther target, explain that the native one-shot scheduler cannot safely encode the year and ask for a nearer time instead of approximating.
   - Verify the helper's success output and resolved local wake time before continuing. If scheduling fails, report the error and leave the thread unarchived.

6. Prefix the title and archive the same thread.
   - Read the current title for `<current thread ID>`.
   - If it does not already start with `⏰ `, call `set_thread_title` with `threadId=<current thread ID>` and title `⏰ <existing title>`.
   - Do not add a second clock prefix when the thread is snoozed again.
   - If renaming fails after the wake-up was created, run `scripts/schedule_snooze.py cancel --thread-id <current thread ID>` with escalation, then report the failure and leave the thread unarchived.
   - Call `set_thread_archived` with `threadId=<current thread ID>` and `archived=true`.
   - If archiving fails after the wake-up was created, run `scripts/schedule_snooze.py cancel --thread-id <current thread ID>` with escalation, then report the failure so no surprise wake-up remains.

7. Confirm briefly.
   - State the resolved local wake time and timezone, for example: `Snoozed until Thu, Jun 25 at 9:00 PM PDT.`
   - If a follow-up was supplied, mention that it is queued for the wake-up.
   - Do not include internal IDs or raw schedule syntax unless the user asks.

## Guardrails

- Never archive first and schedule later.
- Never create a recurring wake-up.
- Never use a Codex heartbeat or cron automation for a snooze that archives its target thread.
- Never snooze a different thread than the active conversation/session ID.
- Never execute the optional follow-up before the wake time; preserve it verbatim for the resumed turn.
- Do not reinterpret an explicit timezone; when the user names one, resolve in that timezone and say so.
