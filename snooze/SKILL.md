---
name: snooze
description: Schedule a one-time wake-up in local time, then archive the current Codex conversation or session. The wake-up unarchives the same thread. Use when the user invokes /snooze or asks to snooze, hide, or archive this conversation until later. Accept a duration such as "for two days" or a future local time such as "until 9pm on Thursday".
---

# Snooze

After the OS-level one-time wake-up is scheduled successfully, archive the current thread.

## Workflow

1. Require macOS.
   - Check the runtime platform first. If you do not know it, run `uname -s`.
   - If the result is `Darwin`, continue.
   - Otherwise show: `Snooze requires macOS LaunchAgents and is not supported on this platform.` Stop before parsing time, changing the title, scheduling a wake-up, or archiving the thread.

2. Require a wake time.
   - Accept a relative duration, for example `/snooze for two days`, `/snooze for 90 minutes`, or `/snooze until tomorrow morning`.
   - Accept a local wall-clock target, for example `/snooze until 9pm on Thursday` or `/snooze until July 2 at 10:30am`.
   - Accept an optional follow-up after a clear separator such as `. Then`, `, then`, or `; then`. For example: `/snooze until 9am. Then try the failed action again` or `/snooze for 10min, then fetch the latest news`.
   - Resolve the time from the text before the separator. Preserve the text after `then` as the follow-up prompt. Do not execute it now.
   - If the request has no duration or target time, ask: `How long should I snooze this conversation?` Stop without scheduling or archiving.
   - If the user writes `then` but provides no follow-up text, ask one concise clarification. Stop.
   - If you cannot resolve the phrase to one future instant, ask one concise clarification. Stop.

3. Resolve the wake instant in the user's current local timezone.
   - Use the runtime's timezone and current local date/time. Do not silently assume UTC.
   - Interpret days, weeks, months, and named dates as local calendar arithmetic. Interpret hours and minutes as elapsed time.
   - For a weekday without a date, choose its next future occurrence. If today is that weekday and the time is still ahead, use today. If today's occurrence has passed, use the following week.
   - If an explicit date is already past, ask for a future time. Do not guess.
   - Preserve the resolved IANA timezone and timezone abbreviation in the confirmation.
   - If needed, round up to the next schedulable minute. Never wake earlier than requested.
   - If daylight-saving rules make the requested local wall time nonexistent or ambiguous, ask for clarification.

4. Capture the active conversation/session ID.
   - Use the current thread ID from the runtime or invocation context.
   - If needed, read only `CODEX_THREAD_ID` with `printenv CODEX_THREAD_ID`. Never dump the full environment.
   - Require the ID. Do not guess from a title or choose a thread from a search result.
   - If the runtime does not expose the current ID, ask the user for it. Stop without changing state.

5. Create a detached one-shot wake-up before archiving.
   - Do not use a Codex heartbeat or cron automation. Heartbeats attach to the target thread. Codex cron accepts only limited repeating schedules. Neither reliably wakes an archived thread at an arbitrary exact time.
   - Run `scripts/schedule_snooze.py schedule --thread-id <current thread ID> --wake-at <resolved ISO-8601 instant with offset> --timezone <IANA timezone>`. If the user supplied a follow-up, append `--follow-up-prompt <verbatim follow-up prompt>`.
   - Request escalation for this command. It writes a per-user LaunchAgent and registers it with `launchctl`.
   - The helper schedules one native macOS calendar trigger. The trigger starts a short-lived `codex app-server --stdio` client with `multi_agent`, `multi_agent_mode`, and `collaboration_modes` disabled. Through App Server JSON-RPC, the helper unarchives the thread. It reads the current title and removes one leading `⏰ ` with `thread/name/set`. It starts any optional follow-up as a new turn. It then removes its own LaunchAgent.
   - Do not ask a resumed model turn to remove the title prefix. Dynamic Codex app tools are unavailable in `codex exec` mode. Use App Server `thread/read` and `thread/name/set` directly for title cleanup.
   - The helper also enables `RunAtLoad`. Its absolute-time guard exits harmlessly before the target time. If a reboot or login occurs after the target time, the helper catches up immediately.
   - Pass a wake instant no more than 366 days in the future. If the user asks for a farther target, explain that the native one-shot scheduler cannot safely encode the year. Ask for a nearer time. Do not approximate.
   - Before continuing, verify the helper's success output and resolved local wake time. If scheduling fails, report the error. Leave the thread unarchived.

6. Prefix the title and archive the same thread.
   - Read the current title for `<current thread ID>`.
   - If it does not already start with `⏰ `, call `set_thread_title` with `threadId=<current thread ID>` and title `⏰ <existing title>`.
   - Do not add a second clock prefix when the thread is snoozed again.
   - If renaming fails after the wake-up was created, run `scripts/schedule_snooze.py cancel --thread-id <current thread ID>` with escalation. Report the failure. Leave the thread unarchived.
   - Call `set_thread_archived` with `threadId=<current thread ID>` and `archived=true`.
   - If archiving fails after the wake-up was created, run `scripts/schedule_snooze.py cancel --thread-id <current thread ID>` with escalation. This prevents an unexpected wake-up. Report the failure.

7. Confirm briefly.
   - State the resolved local wake time and timezone, for example: `Snoozed until Thu, Jun 25 at 9:00 PM PDT.`
   - If the user supplied a follow-up, say that it is queued for the wake-up.
   - Unless the user asks, omit internal IDs and raw schedule syntax.

## Guardrails

- Never archive first and schedule later.
- Never create a recurring wake-up.
- Never use a Codex heartbeat or cron automation for a snooze that archives its target thread.
- Snooze only the thread with the active conversation/session ID.
- Never execute the optional follow-up before the wake time. Preserve it verbatim for the resumed turn.
- If the user names a timezone, resolve the time in that timezone. State that timezone in the confirmation. Do not reinterpret it.
