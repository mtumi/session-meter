# session-meter

A Claude Code skill that measures what a piece of work costs on Claude's 5-hour usage meter, in percent of the session, by catching the exact moments the meter moves up a point.

## In short

- The meter shows whole percents, and its weights are not published. Token counts do not tell you what a job will cost on it, and the rules can change at any time.
- Each time the meter moves from N to N+1, the work done since the previous move cost exactly one point. The skill runs small jobs, reads the live meter from each job's own reply, and divides the recorded work between moves by the points.
- It runs in two tiers. A quick one, about 2 points of the meter and never more than 3 unless you raise the cap, gives a cost per point for one kind of work. A standard one, about 8 to 12 points, separates input, rereading and output, and checks a second model.
- Everything is one Python script that uses only the standard library. No packages, no network calls of its own.

## The problem

Anything that plans work against the meter, such as a daily job that has to stay under 70% of the session, needs to know what a unit of work costs in percent. The tools report tokens and dollars. The meter reports a whole number. Nobody publishes how one becomes the other, the answer can differ by plan and by model, and it can change without notice. So the conversion has to be measured, and measured again when things change.

## How it works

You start from a quiet account and run small jobs, several at a time. Every reply from Claude carries the account's current 5-hour figure (the response header `anthropic-ratelimit-unified-5h-utilization`), so each job is also a fresh, live reading of the meter, at no extra cost. When the meter first moves up a point, that is the starting gun: the work before it is thrown away, since the run started partway into a point. When it moves up the next point, that is the end. The work between the two is exactly one point. A quick run therefore costs up to one point to reach the starting gun plus the one point measured: about 2 points. A spending cap (3 points by default, `--max-points`) stops the run wherever it is, for example if something else on the account is using the meter at the same time. Repeating quick runs, rather than measuring more points in one run, shows whether the meter is steady. If runs of the same kind of work differ by more than about a quarter, something else was using the account, and the run is thrown out.

Do not read the meter with `claude /usage` during a run. Claude Code saves that figure and refreshes it at most every 5 minutes (we checked in version 2.1.236), so polling it every few seconds shows the meter jumping several points at a time on a 5-minute beat. The live figure in each reply has no such delay.

The script also tests an easy case first: whether points simply follow the dollar cost that every headless run reports. If they do, one number per plan is all you need.

## Related tools

[ccmeter](https://github.com/iteebz/ccmeter) uses the same tick idea, but passively. It runs in the background, checks the usage percent every 2 minutes, matches each tick against Claude Code's local logs, and after a few days of normal use reports a budget in dollars. It costs nothing extra. session-meter does the measurement on demand, in one sitting, with a controlled workload and your other sessions paused. That costs about 2 to 4 points, and afterwards Claude talks in percent of the 5-hour session. Because you choose when it runs, you can also measure the busy weekday window and off-peak separately with the same work, and see whether time of day changes the figure (see Time of day). If you can wait a few days and would rather not spend the points, ccmeter is the cheaper route.

## Our strategy

Run the quick tier whenever you want a figure, and keep the account otherwise idle while you do. Save the standard tier for a time when nobody, on any device, is using Claude at all, such as overnight with scheduled tasks paused, and ideally run it twice, once at a busy weekday time and once off-peak (see Time of day). The standard tier is the one that needs the whole account to itself, because it takes the most meter and the longest clock time.

## Time of day

Anthropic has said the 5-hour session can drain faster at busy times. In March 2026 it announced that on weekdays from 5am to 11am Pacific time (8am to 2pm Eastern, 1pm to 7pm UTC in winter) the session limit would drain faster, with the weekly limit unchanged. Reports in May 2026 say it removed that peak-hour reduction for Claude Code on Pro and Max plans, but the same wording has been reported to remain for other products, and we could not find Anthropic's own current statement. So treat it as unknown for your plan. The skill records the local time, the day and the time zone with every run. If you want the full picture, run the standard tier twice: once during the weekday window above and once overnight or on a weekend, and compare the cost per point. If the two agree, the meter does not care about time of day for you. If they differ, quote both. Check Anthropic's help pages for the current rule.

## Our testing

This is an early release. What has and has not been checked, as of 2026-11-24:

- **Checked on made-up data:** the fitting logic recovered a known cost per point to within a few percent, and its steadiness and dollar-cost checks fired when they should.
- **One real run, by hand:** on a Max plan, 34 output-heavy jobs on Sonnet 5.5 with other sessions paused, three ticks of the meter (25% to 28%), two full points. On average, one point of the 5-hour session took about 42,000 output tokens of these jobs, plus about 21,000 tokens written to the cache and 36,000 read from it, and the two points were 16% apart. That count leaves out the measuring session's own turns, which reread a long context each time and may have been close to the same size as the jobs, so a point is at least this much work and possibly up to twice as much. The record is in `runs/quick-2026-11-18.jsonl`.
- **Automatic run, 2026-11-23:** the automatic `run` command, with `quiet pause` and `quiet resume`, on a Max plan with Sonnet 5.5 jobs and the measuring session idle. 400 jobs, no errors; one busy session paused and restarted. Three intervals of $1.33 of reported cost per point, within 1% of each other. That is about 1.7 times the hand run's figure, which fits the hand run counting the measuring session's own turns. The meter appeared to move 2 points at a time, exactly every 5 minutes. That turned out to be the 5-minute saved figure behind `claude /usage`, not the meter (see the next item). The cost per point still holds, because it is averaged over many 5-minute stretches.
- **How the meter really moves, 2026-11-24:** while `claude /usage` was asked for the figure every 2 to 3 seconds, the saved copy in Claude Code's settings file kept the same fetch time for 5 minutes 32 seconds, then jumped from 63% to 64%; Claude Code's code limits that refresh to once every 300,000 milliseconds. Every reply, by contrast, carries the live figure. Reading it from each job's reply on a quiet account (4 workers, 156 jobs, 8 minutes, just after 2pm Eastern on a weekday), the meter moved one point at a time, 68% to 71%, 2 minutes 16 seconds and 2 minutes 33 seconds apart, at $1.19 and $1.36 of reported cost per point. That agrees with the earlier off-peak runs. The record is in `runs/live-headers-2026-11-24.jsonl`.
- **The new automatic run, 2026-11-24:** replaying those recorded replies through it, the run found the starting gun at 69%, stopped at 70% after 2 points in all, and reported $1.16 per point, matching a count by hand. Checked on made-up readings: when the meter jumps 2 points at once (other usage on the account) it stops at the 3-point cap; when a reply carries no usage figure it says so and stops before spending. First real run the same afternoon (`runs/quick-2026-11-24-1419.jsonl`, quiet account, 4 workers, 52 jobs): starting gun at 74%, stopped at 75%, 2 points used in all, $1.18 of reported cost per point, in line with the readings above.
- **Spending, corrected 2026-11-24:** the published versions from 2026-11-23 measured at least 3 points and two meter changes after the first one, so a quick run really spent 8 to 12 points, not the 4 to 6 this page promised then. The current run measures one point after the starting gun and stops at a 3-point cap.
- **Pausing other sessions, 2026-11-24:** a peak-hour run spent while other sessions were working was not paused, because the busy check only counts processor use, and a session waiting on a reply from Claude uses almost none. The skill now pauses every session (`quiet pause --all`), with a notification when it pauses and resumes them.
- **Not yet measured:** whether the meter weighs simultaneous jobs differently from one at a time (run the same work with 1 worker and with 8 and compare), and whether peak hours cost more per point (only off-peak runs so far are clean).
- **Not tested:** other plans, other models, Windows, Linux.
- **Talking in percent, 2026-11-23:** with only the skill installed, Claude answered in percent when asked how much usage a batch would take, but in tokens when asked whether a job was big. The skill now triggers on any job sizing and, after calibrating, offers to add one line to your CLAUDE.md so it holds in every conversation. The line asks Claude to give percent alongside its usual estimate in tokens or time, rather than instead of it, so it works with Claude's habits instead of against them.

A phone, the web app, voice and other computers draw on the same meter and cannot be separated from the readings. Do not use them during a run.

## Install

**What you need**

1. **Claude Code**, with the `claude` command working in your terminal. Check with:

```bash
claude --version
```

If it is not found, install it from Anthropic's setup page (docs.claude.com, search "Claude Code setup"), then sign in once by running `claude`.

2. **Python 3.8 or newer.** The script uses only Python's built-in library, so there is nothing else to install. Check with:

```bash
python3 --version
```

If it is missing or older, install it:
- **Mac:** `xcode-select --install` (installs Apple's Command Line Tools, which include Python 3), or `brew install python` if you use Homebrew.
- **Windows:** `winget install Python.Python.3.12`, or download it from python.org and tick "Add Python to PATH". On Windows the command may be `python` instead of `python3`.
- **Linux:** `sudo apt install python3` (Debian and Ubuntu) or `sudo dnf install python3` (Fedora).

3. **A Claude subscription (Pro, Max or similar).** The automatic run reads the meter from the usage figure each reply carries, which comes with subscription sign-in. Nothing else to install. For the manual way, you type the percent from the claude.ai usage page when the script asks.

**Install the skill**

Copy this folder to `~/.claude/skills/session-meter`, or ask Claude Code to do it and to read the script to you first:

```bash
cp -R session-meter ~/.claude/skills/session-meter
```

Then ask Claude to run the session-meter skill.

## Questions

**Does it use my meter?** Yes. That is the point, and it is why the tiers exist. The quick tier uses about 2 points: up to one point to reach the starting gun, then one point measured. It stops at a 3-point cap whatever happens.

**Can I leave other work running?** The clean mode wants nothing else running. The skill can pause your other Claude Code sessions for the run, if you say yes, and restart them afterwards (Mac and Linux). A passive mode adds up what other Claude Code sessions on the same computer logged, but it cannot see phone, web, voice or other computers, and it says how much it could account for.

**Will the numbers stay true?** Only for the plan and the date measured. Run it again when the plan or the rules change.

## Changes

- **2026-11-18:** first release.
- **2026-11-23:** the automatic run counts points of the meter rather than ticks, since some meters move 2 points at a time. The skill now triggers on any job sizing, and after calibrating it offers a one-line CLAUDE.md rule so Claude keeps talking in percent.
- **2026-11-24:** the step size comes from the meter's second change, not its first, which is never a full step. Calibration dates use local time.
- **2026-11-24:** a meter change counts only when the next reading agrees, so a one-reading flicker no longer stops a run.
- **2026-11-24:** while a measurement runs, a new prompt in another session is stopped and asks whether to discard the measurement or wait. You get a Mac notification when sessions are paused and resumed. `scripts/peak_run.sh` starts a run that pauses every other session, and `runs/PEAK_VS_OFFPEAK.md` keeps a running comparison of peak and off-peak runs.
- **2026-11-24:** `scripts/peak_run.sh` finds its own folder, so it runs on any computer.
- **2026-11-24:** correction. Since 2026-11-23 a quick run could spend 8 to 12 points, not the 4 to 6 this page promised, because it measured at least 3 points and two meter changes after the first change.
- **2026-11-24:** what testing showed, and what changed because of it. `claude /usage` returns a figure Claude Code saves and refreshes at most every 5 minutes. Read every few seconds, it made the meter look as if it moved 2 points at a time on a 5-minute beat, and the 2026-11-23 "counts points, not ticks" and "step size from the second change" changes were built on that. The live figure in each reply moves one point at a time. So the automatic run now reads the meter from each job's own reply and no longer polls `/usage`; it measures from the first move (the starting gun) to the next point and stops at a 3-point cap (`--max-points`). A quick run now costs about 2 points. Cost-per-point figures from earlier runs still hold, since the saved figure only delays the number.
- **2026-11-24:** what testing showed: the busy-session check misses sessions waiting on a reply from Claude, so a run could be spent alongside them. The skill now pauses every other session (`quiet pause --all`).
- **2026-11-24:** the CLAUDE.md rule now asks for percent alongside Claude's usual estimate in tokens or time, rather than instead of it.

## License and disclaimer

MIT; see [LICENSE](LICENSE). A personal project shared as is, not affiliated with Anthropic. It spends your own usage on purpose. You are responsible for what it spends.

Made by Michael Tuminello. If something doesn't work, open an issue on this repository.
