#!/usr/bin/env python3
"""session_meter.py: measure what a unit of work costs on Claude's 5-hour usage meter.

The meter shows whole percents. Each time it ticks from N to N+1, the work done since the
previous tick cost exactly one point. This script records the work (tokens and dollar cost
per job) and the meter readings, then divides the work between ticks by the points.

Subcommands (all write to one records file per run, runs/<run>.jsonl):
  quiet        pause other Claude Code sessions for the measurement, or restart them
  init         start a run and note the plan, versions and what else is running
  read         record one meter reading (type the numbers, or pass them as options)
  job          run one headless Claude job and record its tokens and cost
  transcripts  add up tokens that Claude Code logged on this machine between two times
  fit          find the ticks and report the cost of one point, with a steadiness check

Standard library only. Python 3.8 or newer.
"""
import argparse
import glob
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
RUNS = os.path.join(os.path.dirname(HERE), "runs")
CATS = ["input", "cache_write", "cache_read", "output"]


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_t(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def path_for(run):
    os.makedirs(RUNS, exist_ok=True)
    return os.path.join(RUNS, run + ".jsonl")


def append(run, rec):
    with open(path_for(run), "a") as f:
        f.write(json.dumps(rec) + "\n")


def load(run):
    out = []
    with open(path_for(run)) as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


# ── init ─────────────────────────────────────────────────────────────────────────────────────

def cmd_init(a):
    rec = {"type": "run", "t": now(), "run": a.run, "plan": a.plan, "tier": a.tier,
           "note": a.note, "scheduled_tasks_paused": a.paused,
           "claude_version": subprocess.run(["claude", "--version"], capture_output=True,
                                            text=True).stdout.strip(),
           "mode": a.mode}
    append(a.run, rec)
    print("run started:", path_for(a.run))


# ── read ─────────────────────────────────────────────────────────────────────────────────────

def ask_int(prompt):
    v = input(prompt).strip()
    return int(v) if v else None


def cmd_read(a):
    five = a.five_hour
    if five is None:
        five = ask_int("5-hour percent shown: ")
        a.weekly_all = a.weekly_all if a.weekly_all is not None else ask_int("weekly all-models percent (blank if unknown): ")
        a.weekly_model = a.weekly_model if a.weekly_model is not None else ask_int("weekly single-model percent (blank if unknown): ")
        a.reset = a.reset or input("reset time, ISO (blank if unknown): ").strip() or None
    rec = {"type": "meter", "t": now(), "five_hour": five, "weekly_all": a.weekly_all,
           "weekly_model": a.weekly_model, "reset": a.reset, "note": a.note}
    append(a.run, rec)
    print("recorded", five, "at", rec["t"])


# ── job ──────────────────────────────────────────────────────────────────────────────────────

def filler(words):
    # Deterministic text that is not worth compressing, used to make a long reread-heavy prompt.
    base = ("The harbour ledger lists cargo, weight and tide for each berth in order of arrival, "
            "and the clerk checks every line against the manifest before the gate opens. ")
    n = max(1, words // len(base.split()))
    return "\n".join("Entry %d: %s" % (i, base) for i in range(n))


def cmd_job(a):
    prompt = open(a.prompt_file).read() if a.prompt_file else a.prompt
    if a.filler_words:
        prompt = filler(a.filler_words) + "\n\n" + prompt
    cmd = ["claude", "-p", "--safe-mode", "--strict-mcp-config", "--tools", "",
           "--setting-sources", "", "--no-session-persistence", "--no-chrome",
           "--disable-slash-commands", "--model", a.model, "--output-format", "json"]
    t0 = now()
    t = time.time()
    p = subprocess.run(cmd, input=prompt, capture_output=True, text=True,
                       cwd=tempfile.gettempdir(), timeout=a.timeout)
    secs = round(time.time() - t, 1)
    rec = {"type": "job", "t_start": t0, "t_end": now(), "mix": a.mix, "model": a.model,
           "seconds": secs, "error": None}
    try:
        d = json.loads(p.stdout)
    except ValueError:
        rec["error"] = (p.stderr or p.stdout)[-300:]
        append(a.run, rec)
        print("JOB FAILED, discard any interval that contains it:", rec["error"])
        return 1
    u = d.get("usage") or {}
    mu = d.get("modelUsage") or {}
    rec.update({"input": u.get("input_tokens", 0),
                "cache_write": u.get("cache_creation_input_tokens", 0),
                "cache_read": u.get("cache_read_input_tokens", 0),
                "output": u.get("output_tokens", 0),
                "cost_usd": d.get("total_cost_usd"), "turns": d.get("num_turns"),
                "session_id": d.get("session_id"), "models": mu,
                "is_error": d.get("is_error")})
    answered = sorted(mu)
    if a.model not in answered:
        rec["error"] = "asked for %s, answered by %s" % (a.model, answered)
    # Sum every model's usage, since a small background model can appear only there.
    rec["all_models_total"] = sum(
        (m.get("inputTokens", 0) + m.get("outputTokens", 0) + m.get("cacheReadInputTokens", 0)
         + m.get("cacheCreationInputTokens", 0)) for m in mu.values())
    append(a.run, rec)
    print("job done: %s in/%s cacheW/%s cacheR/%s out, cost %s, %ss%s" % (
        rec["input"], rec["cache_write"], rec["cache_read"], rec["output"], rec["cost_usd"],
        secs, "  ERROR: " + rec["error"] if rec["error"] else ""))
    return 0


# ── transcripts (passive mode) ────────────────────────────────────────────────────────────────

def cmd_transcripts(a):
    lo, hi = parse_t(a.since), parse_t(a.until)
    seen, tot, by_model = set(), dict((c, 0) for c in CATS), {}
    files = glob.glob(os.path.expanduser("~/.claude/projects/**/*.jsonl"), recursive=True)
    for fp in files:
        try:
            f = open(fp)
        except OSError:
            continue
        with f:
            for line in f:
                if '"usage"' not in line:
                    continue
                try:
                    d = json.loads(line)
                    m = d.get("message") or {}
                    u = m.get("usage")
                    ts = d.get("timestamp")
                    if not u or not ts or m.get("model") == "<synthetic>":
                        continue
                    if not (lo <= parse_t(ts) <= hi):
                        continue
                    key = (m.get("id"), d.get("requestId"))
                    if key in seen and key != (None, None):
                        continue
                    seen.add(key)
                except (ValueError, TypeError):
                    continue
                tot["input"] += u.get("input_tokens", 0)
                tot["cache_write"] += u.get("cache_creation_input_tokens", 0)
                tot["cache_read"] += u.get("cache_read_input_tokens", 0)
                tot["output"] += u.get("output_tokens", 0)
                by_model[m.get("model")] = by_model.get(m.get("model"), 0) + 1
    print(json.dumps({"since": a.since, "until": a.until, "tokens": tot, "requests_by_model": by_model}))
    print("Only logged Claude Code sessions on this machine are counted. Phone, web, voice,\n"
          "other computers and headless runs that keep no transcript are not.", file=sys.stderr)



# ── quiet: pause other Claude Code sessions for the measurement ─────────────────────────────

import re
import signal

FROZEN = os.path.join(RUNS, "frozen.json")
PATTERN = re.compile(r"claude-code/|/claude(\s|$)|^claude(\s|$)")


def ps_rows():
    out = subprocess.run(["ps", "-axo", "pid=,ppid=,command="], capture_output=True, text=True).stdout
    rows = []
    for line in out.splitlines():
        bits = line.split(None, 2)
        if len(bits) == 3 and bits[0].isdigit() and bits[1].isdigit():
            rows.append({"pid": int(bits[0]), "ppid": int(bits[1]), "cmd": bits[2]})
    return rows


def other_sessions():
    rows = ps_rows()
    parent = dict((r["pid"], r["ppid"]) for r in rows)
    mine, pid = set(), os.getpid()
    while pid and pid not in mine:
        mine.add(pid)
        pid = parent.get(pid)
    return [r for r in rows if PATTERN.search(r["cmd"]) and r["pid"] not in mine
            and "disclaimer" not in r["cmd"] and "session_meter" not in r["cmd"]
            and "Claude.app/Contents/MacOS" not in r["cmd"]]


def folder_of(pid):
    out = subprocess.run(["lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"], capture_output=True, text=True).stdout
    for line in out.splitlines():
        if line.startswith("n"):
            return line[1:]
    return "folder unknown"


def cmd_quiet(a):
    if os.name == "nt":
        print("Pausing is not available on Windows. Close other Claude sessions yourself.")
        return 1
    if a.action == "resume":
        return do_resume()
    found = other_sessions()
    if not found:
        print("No other Claude Code sessions are running on this computer.")
        return 0
    if not a.yes:
        print("%d other Claude Code session(s) are running." % len(found))
        if input("Pause them while we measure? They pick up where they left off afterwards. [y/n] ").strip().lower() not in ("y", "yes"):
            print("Left running. Readings may include their usage.")
            return 0
    paused = []
    for r in found:
        try:
            os.kill(r["pid"], signal.SIGSTOP)
            paused.append({"pid": r["pid"], "folder": folder_of(r["pid"])})
        except OSError:
            pass
    os.makedirs(RUNS, exist_ok=True)
    json.dump({"t": now(), "paused": paused}, open(FROZEN, "w"))
    if paused:
        # Quiet backstop: they restart by themselves after 90 minutes if nobody runs 'quiet resume'.
        subprocess.Popen(["sh", "-c", "sleep 5400; kill -CONT %s 2>/dev/null" % " ".join(str(x["pid"]) for x in paused)],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    print("Paused %d session(s):" % len(paused))
    for x in paused:
        print("  %s  (process %d)" % (x["folder"], x["pid"]))
    print("To restart them now: session_meter.py quiet resume")
    return 0


def do_resume():
    if not os.path.exists(FROZEN):
        print("No sessions are paused.")
        return 0
    paused = json.load(open(FROZEN))["paused"]
    for x in paused:
        try:
            os.kill(x["pid"], signal.SIGCONT)
        except OSError:
            pass
    os.remove(FROZEN)
    print("Restarted %d session(s):" % len(paused))
    for x in paused:
        print("  " + x["folder"])
    return 0


# ── fit ──────────────────────────────────────────────────────────────────────────────────────

def metrics(job):
    m = dict((c, job.get(c, 0) or 0) for c in CATS)
    m["cost"] = job.get("cost_usd") or 0.0
    return m


def add(x, y):
    return dict((k, x.get(k, 0) + y.get(k, 0)) for k in set(x) | set(y))


def solve(rows, ys):
    # Least squares by the normal equations, plain Python, tiny ridge so it never divides by zero.
    n = len(rows[0])
    A = [[sum(r[i] * r[j] for r in rows) + (1e-9 if i == j else 0) for j in range(n)] for i in range(n)]
    b = [sum(r[i] * y for r, y in zip(rows, ys)) for i in range(n)]
    for i in range(n):
        piv = max(range(i, n), key=lambda k: abs(A[k][i]))
        A[i], A[piv], b[i], b[piv] = A[piv], A[i], b[piv], b[i]
        for k in range(i + 1, n):
            f = A[k][i] / A[i][i]
            for j in range(i, n):
                A[k][j] -= f * A[i][j]
            b[k] -= f * b[i]
    x = [0.0] * n
    for i in reversed(range(n)):
        x[i] = (b[i] - sum(A[i][j] * x[j] for j in range(i + 1, n))) / A[i][i]
    return x


def cmd_fit(a):
    recs = load(a.run)
    jobs = [r for r in recs if r["type"] == "job"]
    meters = sorted([r for r in recs if r["type"] == "meter" and r.get("five_hour") is not None],
                    key=lambda r: r["t"])
    # Keep a reading only when the next one, within 30 seconds, agrees (the display can lag).
    steady = []
    for i, r in enumerate(meters):
        nxt = [x for x in meters[i + 1:] if (parse_t(x["t"]) - parse_t(r["t"])).total_seconds() <= 30]
        if not nxt or nxt[0]["five_hour"] == r["five_hour"]:
            steady.append(r)
    problems = []
    for j in jobs:
        if j.get("error"):
            problems.append("job at %s had an error (%s); intervals containing it are unreliable" %
                            (j["t_end"], j["error"][:80]))
    for i in range(1, len(steady)):
        if steady[i]["five_hour"] < steady[i - 1]["five_hour"]:
            problems.append("the percent dropped at %s; a reset or an aging-out happened, do not span it" % steady[i]["t"])
    # Work done before each reading (jobs that ended before it).
    def work_before(t):
        tot = {}
        for j in jobs:
            if parse_t(j["t_end"]) <= parse_t(t):
                tot = add(tot, metrics(j))
        return tot
    def mixes_between(t1, t2):
        return sorted(set(j["mix"] for j in jobs
                          if parse_t(t1) < parse_t(j["t_end"]) <= parse_t(t2)))
    # Tick k is located between reading i-1 and reading i. Its position is the midpoint of the
    # work done between those two readings, and its uncertainty is half of that work.
    ticks = []
    for i in range(1, len(steady)):
        if steady[i]["five_hour"] > steady[i - 1]["five_hour"]:
            w0, w1 = work_before(steady[i - 1]["t"]), work_before(steady[i]["t"])
            keys = set(w0) | set(w1)
            ticks.append({"to": steady[i]["five_hour"],
                          "pos": dict((k, (w0.get(k, 0) + w1.get(k, 0)) / 2.0) for k in keys),
                          "half": dict((k, (w1.get(k, 0) - w0.get(k, 0)) / 2.0) for k in keys),
                          "t0": steady[i - 1]["t"], "t1": steady[i]["t"]})
    intervals = []
    for i in range(1, len(ticks)):
        pts = ticks[i]["to"] - ticks[i - 1]["to"]
        keys = set(ticks[i]["pos"]) | set(ticks[i - 1]["pos"])
        d = dict((k, ticks[i]["pos"].get(k, 0) - ticks[i - 1]["pos"].get(k, 0)) for k in keys)
        unc = dict((k, ticks[i]["half"].get(k, 0) + ticks[i - 1]["half"].get(k, 0)) for k in keys)
        mixes = mixes_between(ticks[i - 1]["t1"], ticks[i]["t0"])
        if pts != 1:
            problems.append("a jump of %d points at once (to %d); divided, but treat with care" % (pts, ticks[i]["to"]))
        intervals.append({"from": ticks[i - 1]["to"], "to": ticks[i]["to"], "points": pts,
                          "per_point": dict((k, v / pts) for k, v in d.items()),
                          "unc_per_point": dict((k, v / pts) for k, v in unc.items()),
                          "mix": "+".join(mixes) if mixes else "?"})
    print("Run %s: %d jobs, %d meter readings, %d ticks, %d full intervals" %
          (a.run, len(jobs), len(meters), len(ticks), len(intervals)))
    if not intervals:
        print("Need at least two ticks (two full points of work) to measure one interval.")
        for p in problems:
            print("WARNING:", p)
        return
    print("\nPer interval (cost of one meter point):")
    for iv in intervals:
        pp = iv["per_point"]
        print("  %d to %d  mix %-14s cost $%.3f (+/- %.3f)  in %d, cache-write %d, cache-read %d, out %d" % (
            iv["from"], iv["to"], iv["mix"], pp["cost"], iv["unc_per_point"]["cost"], pp["input"],
            pp["cache_write"], pp["cache_read"], pp["output"]))
    by_mix = {}
    for iv in intervals:
        by_mix.setdefault(iv["mix"], []).append(iv)
    print("\nPer mix (mean of its intervals), with steadiness check:")
    means = {}
    for mix, ivs in sorted(by_mix.items()):
        costs = [iv["per_point"]["cost"] for iv in ivs]
        mean = sum(costs) / len(costs)
        spread = (max(costs) - min(costs)) / mean if mean and len(costs) > 1 else None
        means[mix] = mean
        status = "single interval, no steadiness check yet" if spread is None else (
            "steady (spread %.0f%%)" % (spread * 100) if spread <= 0.25 else
            "NOT steady (spread %.0f%%): something else is using the account, or the meter is not linear" % (spread * 100))
        print("  %-14s %d interval(s), $%.3f per point, %s" % (mix, len(ivs), mean, status))
    real = [m for m in means if m != "?"]
    if len(real) >= 2:
        vals = [means[m] for m in real]
        spread = (max(vals) - min(vals)) / (sum(vals) / len(vals))
        print("\nDollar-cost test: cost per point differs by %.0f%% across mixes." % (spread * 100))
        print("  " + ("Points track the reported dollar cost closely. One number per plan may be enough."
                      if spread <= 0.15 else
                      "Points do NOT track the dollar cost. Weights differ by kind of work; use the solve below."))
    if len(intervals) >= 4 and len(by_mix) >= 2:
        rows = [[iv["per_point"][c] for c in CATS] for iv in intervals]
        try:
            w = solve(rows, [1.0] * len(intervals))
            print("\nWeights (points per million tokens) from a least squares solve over %d intervals:" % len(intervals))
            for c, x in zip(CATS, w):
                print("  %-12s %.4f" % (c, x * 1e6))
            print("  Fragile if the mixes were similar. Check it by predicting a held-back job.")
        except ZeroDivisionError:
            print("\nCould not solve the weights: the mixes were too alike.")
    for p in problems:
        print("WARNING:", p)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("init"); s.add_argument("--run", required=True)
    s.add_argument("--plan", default=None); s.add_argument("--tier", default=None)
    s.add_argument("--mode", choices=["clean", "passive"], default="clean")
    s.add_argument("--paused", action="store_true", help="scheduled tasks and other sessions are paused")
    s.add_argument("--note", default=None); s.set_defaults(f=cmd_init)
    s = sub.add_parser("read"); s.add_argument("--run", required=True)
    s.add_argument("--five-hour", type=int); s.add_argument("--weekly-all", type=int)
    s.add_argument("--weekly-model", type=int); s.add_argument("--reset"); s.add_argument("--note")
    s.set_defaults(f=cmd_read)
    s = sub.add_parser("job"); s.add_argument("--run", required=True)
    s.add_argument("--mix", required=True, help="label for the kind of work, e.g. output-heavy")
    s.add_argument("--model", required=True, help="full model id, e.g. claude-sonnet-5-5")
    s.add_argument("--prompt"); s.add_argument("--prompt-file")
    s.add_argument("--filler-words", type=int, default=0, help="prepend this many words of filler (reread-heavy work)")
    s.add_argument("--timeout", type=int, default=600); s.set_defaults(f=cmd_job)
    s = sub.add_parser("transcripts"); s.add_argument("--since", required=True)
    s.add_argument("--until", required=True); s.set_defaults(f=cmd_transcripts)
    s = sub.add_parser("quiet", help="pause other Claude Code sessions, or restart them")
    s.add_argument("action", choices=["pause", "resume"])
    s.add_argument("--yes", action="store_true", help="skip the question (ask the user in chat first)")
    s.set_defaults(f=cmd_quiet)
    s = sub.add_parser("fit"); s.add_argument("--run", required=True); s.set_defaults(f=cmd_fit)
    a = ap.parse_args()
    sys.exit(a.f(a) or 0)


if __name__ == "__main__":
    main()
