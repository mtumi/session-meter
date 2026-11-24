# session-meter

A Claude Code skill that tells you what work costs in percent of your 5-hour session.

## The problem

Anything that plans work against the meter, such as a daily job that has to stay under 70% of the session, needs to know what a unit of work costs in percent. The tools report tokens and dollars. The meter reports a whole number.

Nobody publishes how one becomes the other, the answer can differ by plan and by model, and it can change without notice. So the conversion has to be measured, and measured again when things change.

## What it does

- Measures how much work one point of your 5-hour session is worth on the model you're using, by running small test jobs and watching the live meter move up a point. Each model gets its own figure, so run it once for each model you use.
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

**Does it use my meter?** Yes. That is the point. A run uses about 2 points: up to one point to reach the starting gun, then one point measured. Once 3 points are used it starts no new jobs; the few already running finish, a small fraction of a point.

**Can I leave other work running?** No, it will temporarily pause any running sessions and auto-resume them afterwards. If you want to interrupt it, you can, and it will just discard that test run.

**How reliable is the number?** Based on limited initial testing, runs on the same plan and kind of work have landed within about 15% of each other, so one run gives a fair figure and three or four give a solid one. It's quick to run, but Anthropic can change how usage is counted at any time, so you may want to schedule it to run regularly, and especially if a result seems off (see Notes on use).

## How it works

The skill runs small jobs, several at a time, with nothing else using the account. Every reply from Claude carries the live 5-hour figure in the header `anthropic-ratelimit-unified-5h-utilization`, so each job is also a meter reading. Jobs run on your active model unless you name another with `--model`, and the result is saved under that model. It doesn't use `claude /usage`, which can be up to 5 minutes behind (see Learnings from testing).

The first time the meter moves up a point is the starting gun; the work before it is thrown away, since the run started partway into a point. The next move is the end. The work in between is exactly one point.

So a run costs about 2 points: up to one to reach the starting gun, plus the one measured. A cap (3 points by default, `--max-points`) stops it early if something else on the account is spending.

Repeat runs to check the figure is steady. If runs of the same work differ by more than about a quarter, something else was using the account; throw that run out.

The script also checks whether points track the cost each job reports. If they do, one number per plan is enough.

## Notes on use

### General

Don't use Claude on your phone, the web, voice or another computer during a run. The skill can't pause those, and their use lands on the same meter.

Run it once for each model you use; a figure measured on one model doesn't apply to another. Rerun it after changing plan, after a Claude Code update, and whenever an estimate in percent seems off.

### Time of day

Anthropic has made the session drain faster on weekdays from 8am to 2pm Eastern (5am to 11am Pacific), and says that no longer applies to Claude Code on Pro and Max. To check your account, run it once in that window and once outside it, and compare.

## Changes

**v0.2.1, 2026-11-24**

- One kind of run: the "quick" and "standard" tiers are gone. To compare kinds of work, run once per kind.
- Runs on your active model by default, and keeps a separate figure for each model; estimates use the figure for the model doing the work.
- Passive mode is gone from the docs; a run always pauses your other sessions.
- The spending cap is described as it works: at 3 points no new jobs start, and the few already running finish.
- README reorganized: install near the top, shorter throughout, and a Learnings from testing section with a fourth lesson (ask for percent alongside tokens, not instead of them).

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

As of 2026-11-24, on a Max plan. The test jobs are short and output-heavy, on Sonnet 5.5: each about 960 output tokens, plus about 1,900 written to the cache and 3,300 read from it.

**Tested**

- **Live meter reading:** quiet account, 4 workers, 156 jobs. The meter moved one point at a time, every 43 and 50 jobs: about 41,000 and 48,000 output tokens per point (`runs/live-headers-2026-11-24.jsonl`).
- **Real run:** starting gun at 74%, stopped at 75%, 2 points used, about 42,000 output tokens per point (`runs/quick-2026-11-24-1419.jsonl`).
- **Run replayed on recorded replies:** found the same point as a count by hand.
- **Spending cap, and replies with no usage figure:** both stop the run as they should, on made-up readings.
- **Prompt guard:** on during the real run and cleared afterwards. Both replies, discarding a run and the time shown were checked against a simulated run.
- **Pausing other sessions:** 33 sessions paused and all resumed on 2026-11-18; a busy session paused and resumed during a run on 2026-11-23.
- **Per-point calculation:** recovered a known figure within a few percent, on made-up data.
- **Earlier runs read through `/usage`** (2026-11-18 by hand, 2026-11-23 automatic): about 47,000 to 49,000 output tokens per point on 2026-11-23, in line with the live figures. Their 2-point steps were the `/usage` delay.
- **Percent in estimates:** with the CLAUDE.md line, Claude gave percent for both a usage question and a "how long will this take" question.

**Not tested yet**

- Peak hours: no clean peak-hour run yet.
- `scripts/peak_run.sh`, the one-line start for a run by hand.
- Other models and kinds of work. Bigger models use more meter per token (Fable most, then Opus, Sonnet, Haiku), so a point is fewer tokens on Opus than on Sonnet; how many fewer isn't measured. Nor is work that mostly rereads a long context.
- Running jobs one at a time. Every run so far ran 4 at once; the same work done one after another might use the meter differently.
- Other plans, Windows, Linux.

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
