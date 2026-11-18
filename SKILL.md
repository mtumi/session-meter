---
name: session-meter
description: Measure what a unit of work costs on Claude's 5-hour usage meter, by finding the exact moments the whole-percent display ticks over. Use when someone wants token counts translated into percent of the session, or when the meter's rules may have changed.
---

# Session meter

The usage meter shows whole percents and does not publish its weights, and the weights can change at any time. This skill measures them fresh. Each time the display ticks from N to N+1, the work done since the previous tick cost exactly one point.

Everything is done by `scripts/session_meter.py` (Python standard library only). Records go to `runs/<run>.jsonl`.

## Before starting
0. **Quiet the account (clean mode).** Ask the user in chat: "Pause your other Claude Code sessions while we measure? They pick up where they left off afterwards." On a yes, run `session_meter.py quiet pause --yes`. It pauses every other session on this computer and prints which ones. Run `session_meter.py quiet resume` at the end, even if the run failed. They also restart by themselves after 90 minutes. Not available on Windows. In the Claude desktop app, also pause scheduled tasks that would fire during the run and turn the same ones back on afterwards. Phone, web, voice and other computers cannot be paused from here: ask the user to stop using them.
1. Choose the mode.
   - **Clean** (default): pause scheduled tasks, close other Claude sessions and apps on every device, and use nothing else on the account. Every token is then the measuring jobs' own.
   - **Passive**: leave other Claude Code work running and add up what every local session logged between ticks, with `transcripts`. It misses phone, web, voice, other computers and headless runs that keep no transcript, so it reports how much it could account for. If intervals for the same kind of work are not steady, switch to clean.
2. Check the reset time. Start at least two hours before it. Never span a reset.
3. Read the meter twice, about ten seconds apart. Proceed only if both match.
4. Note the plan, and whether extra usage is on.

## Procedure
1. `session_meter.py init --run <name> --plan <plan> --paused` (add `--mode passive` for passive).
2. Record a reading: `session_meter.py read --run <name>` (type the percents shown), or pass `--five-hour N --weekly-all N --weekly-model N --reset <time>` when a tool supplies them. Record two readings ten seconds apart every time.
3. Run one small job, then read the meter twice. Repeat. Keep each job to about a tenth to a third of a point, so a tick is located within one job. Start rough, estimate the size of one point, then size jobs to fit.
   - Output-heavy: `session_meter.py job --run <name> --mix output-heavy --model <full model id> --prompt-file workloads/output-heavy.md`
   - Reread-heavy: add `--mix reread-heavy --prompt-file workloads/reread-heavy.md --filler-words 30000`
4. After the first tick, keep going until you have the planned number of full points (below).
5. `session_meter.py fit --run <name>`.

Run jobs one at a time. Name the model in full; the script refuses to trust a reply from a different model.

## Tiers
- **Quick, about 3 points:** one kind of work, one search for the first tick (up to 1 point, thrown away), two full points. Gives one cost per point and a first steadiness check. Do this now.
- **Standard, about 8 to 12 points:** output-heavy, reread-heavy and a second model, plus a held-back job to check the fit. Schedule it for a time when nobody is using Claude at all.
- **Dollar-cost test:** the headless report includes a dollar cost. If points per dollar come out the same for every kind of work, one number per plan is enough and the quick tier is all you need.

## Stop rules
- Intervals for the same kind of work differ by more than about 25%: something else is using the account, or the meter is not linear. Stop, switch to clean, repeat.
- The percent drops at any point: a reset or aging-out. Discard the interval.
- A job failed or was retried: discard any interval that contains it.
- A reply came from a different model than the one asked for: discard that job.

## Report
Say the date, the plan, the mode, how many intervals, the cost of one point per kind of work, the steadiness, and what the numbers cannot tell (other devices, rule changes). Weights are true only for the date and plan measured.
