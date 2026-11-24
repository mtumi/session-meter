---
name: session-meter
description: Measure what a unit of work costs on Claude's 5-hour usage meter, by finding the exact moments the live meter moves up a point. Use when someone wants token counts translated into percent of the session, or when the meter's rules may have changed. Also use whenever sizing, planning or estimating any piece of work (a batch of jobs, agents, a long task, "is this a big job?"), so the answer is given in percent of the 5-hour session rather than tokens.
---

# Session meter

The usage meter shows whole percents and does not publish its weights, and the weights can change at any time. This skill measures them fresh. Each time the meter moves from N to N+1, the work done since the previous move cost exactly one point. Every reply from Claude carries the live figure, so each measuring job is also a meter reading. Never measure with `claude /usage`: Claude Code saves that figure and refreshes it at most every 5 minutes, which makes the meter look as if it jumps several points at a time.

Everything is done by `scripts/session_meter.py` (Python standard library only). Records go to `runs/<run>.jsonl`.

## Before starting
0. **Quiet the account (clean mode).** Ask the user in chat: "Pause your other Claude Code sessions while we measure? They pick up where they left off afterwards." On a yes, run `session_meter.py quiet pause --all --yes`. It pauses every other Claude Code session and prints which ones. Use `--all`: without it only sessions using the processor right now are paused, and a session waiting on a reply from Claude uses almost none while still spending meter. Run `session_meter.py quiet resume` at the end, even if the run failed. They also restart by themselves after 90 minutes. Not available on Windows. In the Claude desktop app, also pause scheduled tasks that would fire during the run and turn the same ones back on afterwards. Phone, web, voice and other computers cannot be paused from here: ask the user to stop using them.
1. Choose the mode.
   - **Clean** (default): pause scheduled tasks, close other Claude sessions and apps on every device, and use nothing else on the account. Every token is then the measuring jobs' own.
   - **Passive**: leave other Claude Code work running and add up what every local session logged between ticks, with `transcripts`. It misses phone, web, voice, other computers and headless runs that keep no transcript, so it reports how much it could account for. If intervals for the same kind of work are not steady, switch to clean.
2. Check the reset time. Start at least two hours before it. Never span a reset.
3. Check the session is below about 95%, so a 3-point run fits.
4. Note the plan, and whether extra usage is on.

## Procedure
The automatic way (run on the real meter 2026-11-23): `session_meter.py run --run <name> --mix output-fast --model <full model id> --prompt-file workloads/output-fast.md --workers 4`. The script runs jobs in parallel and reads the live meter from each job's reply. The first move of the meter is the starting gun; it measures from there to the next point (`--points`, default 1) and stops at a spending cap of 3 points (`--max-points`). It prints a time estimate first and a line at each move, then fits. Start it in the background and wait for it to finish; do not take turns while it runs, since this session's own turns spend meter. If the replies carry no usage figure (off a Claude subscription), it says so before spending; use the manual way below.

The manual way:
1. `session_meter.py init --run <name> --plan <plan> --paused` (add `--mode passive` for passive).
2. Record a reading: `session_meter.py read --run <name>` (type the percent shown), or pass `--five-hour N --weekly-all N --weekly-model N --reset <time>` when a tool supplies them. Take the figure from the claude.ai usage page, not `claude /usage`, which can be up to 5 minutes old.
3. Run one small job, then read the meter twice. Repeat. Keep each job to about a tenth to a third of a point, so a tick is located within one job. Start rough, estimate the size of one point, then size jobs to fit.
   - Output-heavy: `session_meter.py job --run <name> --mix output-heavy --model <full model id> --prompt-file workloads/output-heavy.md`
   - Reread-heavy: add `--mix reread-heavy --prompt-file workloads/reread-heavy.md --filler-words 30000`
4. After the first move (the starting gun), keep going until the meter has moved one more point.
5. `session_meter.py fit --run <name>`.

Run jobs one at a time. Name the model in full; the script refuses to trust a reply from a different model.

## What a run measures
- **One run, about 2 points, never more than 3:** one kind of work; up to one point to reach the starting gun (thrown away), then one point measured. The spending cap (3 by default) stops the run wherever it is. Steadiness comes from repeating runs, not from more points in one run.
- **Other kinds of work:** run once per kind, with its own `--mix` and `--prompt-file` (reread-heavy: `workloads/reread-heavy.md` with `--filler-words 30000`; another model: `--model`).
- **Dollar-cost test:** the headless report includes a dollar cost. If points per dollar come out the same for every kind of work, one number per plan is enough.

## Stop rules
- Intervals for the same kind of work differ by more than about 25%: something else is using the account, or the meter is not linear. Stop, switch to clean, repeat.
- The percent drops at any point: a reset or aging-out. Discard the interval.
- A job failed or was retried: discard any interval that contains it.
- A reply came from a different model than the one asked for: discard that job.

## Report
Say the date, the plan, the mode, how many intervals, the cost of one point per kind of work, the steadiness, and what the numbers cannot tell (other devices, rule changes). Weights are true only for the date and plan measured.

## After calibrating: talk in percent of the session
Once `runs/calibration.json` exists, whenever you estimate how big or costly a piece of work is (in tokens, time, dollars or number of calls), also give it as a rough percent of the 5-hour session, for the rest of the conversation and in later ones while the calibration is still current: "this will use about 6% of your 5-hour session". Get the number with `session_meter.py estimate --cost-usd <dollar figure from the job report or the plan>`, or by scaling from the measured cost per point. Say "about" and give a range when the estimate is loose. Say the calibration date and plan when it matters, and recommend re-measuring if the plan or the rules may have changed.

**Make it stick.** This section only loads when the skill is in use. Tested 2026-11-23: with the skill installed, Claude answered in percent when asked about usage, but answered in tokens when asked "is this a big job?" The line below adds to Claude's usual estimate rather than replacing it, so it rides on a habit Claude already has instead of fighting it. After saving a calibration, ask the user: "Add one line to your CLAUDE.md so Claude also gives every cost estimate in percent of the 5-hour session, in every conversation?" On a yes, append this line to `~/.claude/CLAUDE.md` (create the file if it is missing), with the skill's real path:

```
Whenever you estimate how big or costly a piece of work is (in tokens, time, dollars or number of calls), also give a rough percent of the 5-hour session, from the latest session-meter calibration (`python3 ~/.claude/skills/session-meter/scripts/session_meter.py estimate --cost-usd <dollars>`, or by scaling from its measured work per point). Say the calibration date, and say it is rough when the work differs from what was measured.
```
