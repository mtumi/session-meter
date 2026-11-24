# session-meter

A Claude Code skill that measures what a piece of work costs on Claude's 5-hour usage meter, in percent of the session, by catching the exact moments the meter moves up a point.

## The problem

Anything that plans work against the meter, such as a daily job that has to stay under 70% of the session, needs to know what a unit of work costs in percent. The tools report tokens and dollars. The meter reports a whole number.

Nobody publishes how one becomes the other, the answer can differ by plan and by model, and it can change without notice. So the conversion has to be measured, and measured again when things change.

## What it does

- Measures how much work one point of your 5-hour session is worth, by running small test jobs and watching the live meter move up a point.
- Saves that figure, so Claude can tell you what a job will cost in percent of your session, alongside its usual estimate in tokens or time.
- Takes about 2 points of your meter and a few minutes.
- One Python script, standard library only.

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

**Does it use my meter?** Yes. That is the point. A run uses about 2 points: up to one point to reach the starting gun, then one point measured. It stops at a 3-point cap whatever happens.

**Can I leave other work running?** The clean mode wants nothing else running. The skill can pause your other Claude Code sessions for the run, if you say yes, and restart them afterwards (Mac and Linux). A passive mode adds up what other Claude Code sessions on the same computer logged, but it cannot see phone, web, voice or other computers, and it says how much it could account for.

**Will the numbers stay true?** Only for the plan and the date measured. Run it again when the plan or the rules change.

## How it works

You start from a quiet account and run small jobs, several at a time. Every reply from Claude carries the account's current 5-hour figure (the response header `anthropic-ratelimit-unified-5h-utilization`), so each job is also a fresh, live reading of the meter, at no extra cost.

When the meter first moves up a point, that is the starting gun: the work before it is thrown away, since the run started partway into a point. When it moves up the next point, that is the end. The work between the two is exactly one point.

A quick run therefore costs up to one point to reach the starting gun plus the one point measured: about 2 points. A spending cap (3 points by default, `--max-points`) stops the run wherever it is, for example if something else on the account is using the meter at the same time.

Repeating quick runs, rather than measuring more points in one run, shows whether the meter is steady. If runs of the same kind of work differ by more than about a quarter, something else was using the account, and the run is thrown out.

The run does not use `claude /usage`, which can be up to 5 minutes behind (see Learnings from testing).

The script also tests an easy case first: whether points simply follow the dollar cost that every headless run reports. If they do, one number per plan is all you need.

## Notes on use

### General

Run it whenever you want a figure, with nothing else using Claude on any device while it runs. Repeat it a few times to see whether the figure is steady.

### Time of day

Anthropic has said the 5-hour session can drain faster at busy times. In March 2026 it announced that on weekdays from 5am to 11am Pacific time (8am to 2pm Eastern, 1pm to 7pm UTC in winter) the session limit would drain faster, with the weekly limit unchanged.

Reports in May 2026 say it removed that peak-hour reduction for Claude Code on Pro and Max plans, but the same wording has been reported to remain for other products, and we could not find Anthropic's own current statement. So treat it as unknown for your plan.

The skill records the local time, the day and the time zone with every run. If you want the full picture, run it during the weekday window above and again overnight or on a weekend, and compare the cost per point.

If the two agree, the meter does not care about time of day for you. If they differ, quote both. Check Anthropic's help pages for the current rule.

## Changes

**v0.2.0, 2026-11-24**

- Reads the live meter from each reply instead of `claude /usage`, which can be up to 5 minutes behind.
- A quick run now costs about 2 points: the starting gun plus one point measured, with a hard cap of 3 (`--max-points`).
- Correction: the versions published on 2026-11-23 could spend 8 to 12 points on a quick run, not the 4 to 6 this page promised.
- Pauses every other Claude Code session during a run, with a Mac notification when they pause and resume. While a run is going, a new prompt is stopped and asked whether to discard the run or wait.
- The time estimate uses the last measured cost per point.
- Claude gives estimates in percent of the session alongside tokens or time, through a one-line CLAUDE.md rule offered after calibrating.
- `scripts/peak_run.sh` starts a run by hand, for peak-hour measurements.
- New section: Learnings from testing.

**v0.1.0, 2026-11-18**

- First release.

## Our testing

As of 2026-11-24, on a Max plan with Sonnet 5.5 jobs.

**Tested**

- **Live meter reading:** quiet account, 4 workers, 156 jobs. The meter moved one point at a time; $1.19 and $1.36 of reported cost per point (`runs/live-headers-2026-11-24.jsonl`).
- **Quick run, real:** starting gun at 74%, stopped at 75%, 2 points used, $1.18 per point (`runs/quick-2026-11-24-1419.jsonl`).
- **Quick run, replayed on recorded replies:** $1.16 per point, matching a count by hand.
- **Spending cap, and replies with no usage figure:** both stop the run as they should, on made-up readings.
- **Prompt guard:** both replies, discarding a run, and the time shown, against a simulated run. Not yet during a real run.
- **Cost calculation:** recovered a known cost per point within a few percent, on made-up data.
- **Earlier runs read through `/usage`** (2026-11-18 by hand, 2026-11-23 automatic): $1.33 per point on 2026-11-23, in line with the live figures. Their 2-point steps were the `/usage` delay.
- **Percent in estimates:** with the CLAUDE.md line, Claude gave percent for both a usage question and a "how long will this take" question.

**Not tested yet**

- Peak hours: no clean peak-hour run yet.
- Pausing every session (`quiet pause --all`) and `scripts/peak_run.sh` on a real run.
- Other kinds of work (heavy rereading, a second model) and passive mode.
- Whether jobs run at the same time are weighed differently from one at a time.
- Other plans, other models, Windows, Linux.

A phone, the web app, voice and other computers use the same meter and can't be told apart from the run's own use. Don't use them during a run.

## Learnings from testing

Checked on a Max plan with Claude Code 2.1.236 in November 2026. None of it is documented by Anthropic, so it can change; each check takes a minute to rerun.

**1. Where the live meter figure is.** Every reply to a subscription account carries the account's usage in response headers. The one that matters is `anthropic-ratelimit-unified-5h-utilization`: the 5-hour session as a fraction, so `"0.69"` means 69%. Its neighbours are `-5h-reset` (reset time, in seconds since 1970), `-5h-status`, and the same for the weekly limit (`-7d-`).

Claude Code prints the headers when `ANTHROPIC_LOG` is set to `debug`. To see it (this spends a tiny amount of meter):

```bash
echo "Say OK." | ANTHROPIC_LOG=debug claude -p --model haiku | grep -o 'unified-5h-utilization[^,]*'
```

When you parse it: the debug log shares standard output with the reply, so with `--output-format json` the result is the last line that starts with `{`. A reply can print the header more than once; take the highest. With several jobs running, replies finish out of order, so keep the highest figure seen so far.

**2. Don't use `claude /usage` for this.** It shows a figure Claude Code saves in `~/.claude.json` (`cachedUsageUtilization`, with the fetch time in `fetchedAtMs`), refreshes at most every 5 minutes (300,000 milliseconds in the code), and will show a saved figure up to an hour old. Asked every 2 to 3 seconds, its fetch time stayed fixed for 5 minutes 32 seconds, then the figure jumped from 63% to 64%. Polled fast, it makes the meter look as if it jumps several points at a time on a 5-minute beat.

To check your version, watch `fetchedAtMs` while asking `/usage` repeatedly.

Other routes fall short too: the endpoint behind `/usage` (`/api/oauth/usage`) is widely reported to refuse frequent requests (HTTP 429); the `rate_limit_event` lines in `--output-format stream-json` carry the status but not the percent; and the status line's `rate_limits` field is reported to update only on that session's own replies.

**3. The meter moves one point at a time.** Read live on a quiet account, it went 68% to 69% to 70% to 71%, 2 minutes 16 seconds and 2 minutes 33 seconds apart at a steady load. There is no fixed clock and no multi-point step. Jumps of 2 or more points mean a delayed reader or something else on the account spending.

**4. Ask for percent alongside tokens, not instead of them.** With only the skill installed, Claude answered in percent when asked about usage, but fell back to tokens when asked whether a job was big. Talking in tokens is probably deeply ingrained, so an instruction to replace it loses some of the time.

The fix was to ask for percent of the session alongside any estimate in tokens or time. That doesn't fight the old habit, and it turns the old habit into the trigger: whenever Claude reaches for tokens, the percent comes with it. Retested, both kinds of question gave percent.

## Related tools

[ccmeter](https://github.com/iteebz/ccmeter) uses the same tick idea, but passively. It runs in the background, checks the usage percent every 2 minutes, matches each tick against Claude Code's local logs, and after a few days of normal use reports a budget in dollars. It costs nothing extra.

session-meter does the measurement on demand, in one sitting, with a controlled workload and your other sessions paused. That costs about 2 points, and afterwards Claude talks in percent of the 5-hour session.

Because you choose when it runs, you can also measure the busy weekday window and off-peak separately with the same work, and see whether time of day changes the figure (see Time of day).

If you can wait a few days and would rather not spend the points, ccmeter is the cheaper route.

## License and disclaimer

MIT; see [LICENSE](LICENSE). A personal project shared as is, not affiliated with Anthropic. It spends your own usage on purpose. You are responsible for what it spends.

Made by Michael Tuminello. If something doesn't work, open an issue on this repository.
