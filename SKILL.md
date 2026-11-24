---
name: session-meter
description: Measure what a unit of work costs on Claude's 5-hour usage meter, by finding the exact moments the whole-percent display ticks over. Use when someone wants token counts translated into percent of the session, or when the meter's rules may have changed. Also use whenever sizing, planning or estimating any piece of work (a batch of jobs, agents, a long task, "is this a big job?"), so the answer is given in percent of the 5-hour session rather than tokens.
---

# Session meter

The usage meter shows whole percents and does not publish its weights, and the weights can change at any time. This skill measures them fresh. Each time the display ticks from N to N+1, the work done since the previous tick cost exactly one point.

Everything is done by `scripts/session_meter.py` (Python standard library only). Records go to `runs/<run>.jsonl`.

## Before starting
0. **Quiet the account (clean mode).** Ask the user in chat: "Pause your other Claude Code sessions while we measure? They pick up where they left off afterwards." On a yes, run `session_meter.py quiet pause --yes`. It pauses the other sessions that are busy right now and prints which ones. Idle sessions spend nothing, so they are left alone (`--all` pauses them too). Run `session_meter.py quiet resume` at the end, even if the run failed. They also restart by themselves after 90 minutes. Not available on Windows. In the Claude desktop app, also pause scheduled tasks that would fire during the run and turn the same ones back on afterwards. Phone, web, voice and other computers cannot be paused from here: ask the user to stop using them.
1. Choose the mode.
   - **Clean** (default): pause scheduled tasks, close other Claude sessions and apps on every device, and use nothing else on the account. Every token is then the measuring jobs' own.
   - **Passive**: leave other Claude Code work running and add up what every local session logged between ticks, with `transcripts`. It misses phone, web, voice, other computers and headless runs that keep no transcript, so it reports how much it could account for. If intervals for the same kind of work are not steady, switch to clean.
2. Check the reset time. Start at least two hours before it. Never span a reset.
3. Read the meter twice, about ten seconds apart. Proceed only if both match.
4. Note the plan, and whether extra usage is on.

## Procedure
The automatic way (new, not yet tested on the real meter): `session_meter.py run --run <name> --mix output-fast --model <full model id> --prompt-file workloads/output-fast.md --points 3 --workers 4`. The script runs jobs in parallel, reads the meter itself with `claude -p "/usage"`, prints a time estimate first and a progress line after every reading, then fits. Start it in the background and wait for it to finish; do not take turns while it runs, since this session's own turns spend meter. If `claude -p "/usage"` does not print a session percent, use the manual way below.

The manual way:
1. `session_meter.py init --run <name> --plan <plan> --paused` (add `--mode passive` for passive).
2. Record a reading: `session_meter.py read --run <name>` (type the percents shown), or pass `--five-hour N --weekly-all N --weekly-model N --reset <time>` when a tool supplies them. Record two readings ten seconds apart every time.
3. Run one small job, then read the meter twice. Repeat. Keep each job to about a tenth to a third of a point, so a tick is located within one job. Start rough, estimate the size of one point, then size jobs to fit.
   - Output-heavy: `session_meter.py job --run <name> --mix output-heavy --model <full model id> --prompt-file workloads/output-heavy.md`
   - Reread-heavy: add `--mix reread-heavy --prompt-file workloads/reread-heavy.md --filler-words 30000`
4. After the first tick, keep going until you have the planned number of full points (below).
5. `session_meter.py fit --run <name>`.

Run jobs one at a time. Name the model in full; the script refuses to trust a reply from a different model.

## Tiers
- **Quick, about 4 to 6 points:** one kind of work, one search for the first tick (up to one step of the meter, thrown away), then at least 3 points and never fewer than two steps. The display moves 1 point at a time on some accounts and 2 on others (2026-11-23, Max plan: always 2), so the quick tier costs about 4 points on the first kind and 6 on the second. The script finds the step size by itself. Gives one cost per point and a first steadiness check. Do this now.
- **Standard, about 8 to 12 points:** output-heavy, reread-heavy and a second model, plus a held-back job to check the fit. Schedule it for a time when nobody is using Claude at all.
- **Dollar-cost test:** the headless report includes a dollar cost. If points per dollar come out the same for every kind of work, one number per plan is enough and the quick tier is all you need.

## Stop rules
- Intervals for the same kind of work differ by more than about 25%: something else is using the account, or the meter is not linear. Stop, switch to clean, repeat.
- The percent drops at any point: a reset or aging-out. Discard the interval.
- A job failed or was retried: discard any interval that contains it.
- A reply came from a different model than the one asked for: discard that job.

## Report
Say the date, the plan, the mode, how many intervals, the cost of one point per kind of work, the steadiness, and what the numbers cannot tell (other devices, rule changes). Weights are true only for the date and plan measured.

## After calibrating: talk in percent of the session
Once `runs/calibration.json` exists, the user does not want token counts or dollars. For the rest of the conversation, and in later ones while the calibration is still current, state the cost of any planned work as a rough percent of the 5-hour session: "this will use about 6% of your 5-hour session". Get the number with `session_meter.py estimate --cost-usd <dollar figure from the job report or the plan>`, or by scaling from the measured cost per point. Say "about" and give a range when the estimate is loose. Mention tokens or dollars only if the user asks. Say the calibration date and plan when it matters, and recommend re-measuring if the plan or the rules may have changed.

**Make it stick.** This section only loads when the skill is in use. Tested 2026-11-23: with the skill installed, Claude answered in percent when asked about usage, but answered in tokens when asked "is this a big job?" So after saving a calibration, ask the user: "Add one line to your CLAUDE.md so Claude quotes costs in percent of the 5-hour session in every conversation?" On a yes, append this line to `~/.claude/CLAUDE.md` (create the file if it is missing), with the skill's real path:

```
When saying what planned work will cost or how big a job is, give it as a rough percent of the 5-hour session from the session-meter calibration (`python3 ~/.claude/skills/session-meter/scripts/session_meter.py estimate --cost-usd <dollars>`), not tokens or dollars unless asked.
```
