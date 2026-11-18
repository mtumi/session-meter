# session-meter

A Claude Code skill that measures what a piece of work costs on Claude's 5-hour usage meter, in percent of the session, by catching the exact moments the meter ticks over.

**[Read the full guide](docs/index.html)**: the problem, how the measurement works, how to run it, our test results, limits and troubleshooting. (The guide is still to be written.)

## In short

- The meter shows whole percents, and its weights are not published. Token counts do not tell you what a job will cost on it, and the rules can change at any time.
- Each time the meter ticks from N to N+1, the work done since the previous tick cost exactly one point. The skill runs small jobs, reads the meter after each, and divides the recorded work between ticks by the points.
- It runs in two tiers. A quick one, about 3 points of the meter, gives a cost per point for one kind of work. A standard one, about 8 to 12 points, separates input, rereading and output, and checks a second model.
- Everything is one Python script that uses only the standard library. No packages, no network calls of its own.

## The problem

Anything that plans work against the meter, such as a daily job that has to stay under 70% of the session, needs to know what a unit of work costs in percent. The tools report tokens and dollars. The meter reports a whole number. Nobody publishes how one becomes the other, the answer can differ by plan and by model, and it can change without notice. So the conversion has to be measured, and measured again when things change.

## How it works

You start from a quiet account and read the meter. You run one small job at a time, each sized to move the meter a fraction of a point, and read the meter twice after each, ten seconds apart, so a lagging display cannot fool you. When the number changes, you have found a tick. The work between one tick and the next is exactly one point. Finding the first tick costs up to a point, which is thrown away. Repeating an interval shows whether the meter is steady. If the intervals for the same kind of work differ by more than about a quarter, something else is using the account, and the run is thrown out.

The script also tests an easy case first: whether points simply follow the dollar cost that every headless run reports. If they do, one number per plan is all you need.

## Our strategy

Run the quick tier whenever you want a figure, and keep the account otherwise idle while you do. Save the standard tier for a time when nobody, on any device, is using Claude at all, such as overnight with scheduled tasks paused, and ideally run it twice, once at a busy weekday time and once off-peak (see Time of day). The standard tier is the one that needs the whole account to itself, because it takes the most meter and the longest clock time.

## Time of day

Anthropic has said the 5-hour session can drain faster at busy times. In March 2026 it announced that on weekdays from 5am to 11am Pacific time (8am to 2pm Eastern, 1pm to 7pm UTC in winter) the session limit would drain faster, with the weekly limit unchanged. Reports in May 2026 say it removed that peak-hour reduction for Claude Code on Pro and Max plans, but the same wording has been reported to remain for other products, and we could not find Anthropic's own current statement. So treat it as unknown for your plan. The skill records the local time, the day and the time zone with every run. If you want the full picture, run the standard tier twice: once during the weekday window above and once overnight or on a weekend, and compare the cost per point. If the two agree, the meter does not care about time of day for you. If they differ, quote both. Check Anthropic's help pages for the current rule.

## Our testing

Not run yet. This section will hold the dated results: the plan tested, the mode, the number of intervals, the cost per point for each kind of work, how steady it was, and what we could not tell. The method was checked on made-up data first, where it recovered the known cost per point to within a few percent.

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

3. **A way to read the meter.** In the Claude desktop app, Claude can read it for you. Anywhere else, you type the percent shown on your usage screen (or from the `/usage` command in Claude Code) when the script asks. Nothing else to install.

**Install the skill**

Copy this folder to `~/.claude/skills/session-meter`, or ask Claude Code to do it and to read the script to you first:

```bash
cp -R session-meter ~/.claude/skills/session-meter
```

Then ask Claude to run the session-meter skill.

## Questions

**Does it use my meter?** Yes. That is the point, and it is why the tiers exist. The quick tier uses about 3 points.

**Can I leave other work running?** The clean mode wants nothing else running. The skill can pause your other Claude Code sessions for the run, if you say yes, and restart them afterwards (Mac and Linux). A passive mode adds up what other Claude Code sessions on the same computer logged, but it cannot see phone, web, voice or other computers, and it says how much it could account for.

**Will the numbers stay true?** Only for the plan and the date measured. Run it again when the plan or the rules change.

## License and disclaimer

MIT; see [LICENSE](LICENSE). A personal project shared as is, not affiliated with Anthropic. It spends your own usage on purpose. You are responsible for what it spends.

Made by Michael Tuminello. If something doesn't work, open an issue on this repository.
