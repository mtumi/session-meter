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
  run          measure automatically (parallel jobs, meter polled by the script, progress shown)
  estimate     turn a job's reported dollar cost into percent of the 5-hour session
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
# Shared with scripts/meter_guard.py (a prompt hook): CHECK exists while a check is in progress,
# LAST_CHECK records the latest one so a resumed session can be told it was paused.
CHECK = os.path.expanduser("~/.claude/session-meter-check.json")
STEP_FILE = os.path.expanduser("~/.claude/session-meter-step.json")  # points per display change, from the last run
LAST_CHECK = os.path.expanduser("~/.claude/session-meter-last-check.json")


def write_check(**fields):
    d = {}
    if os.path.exists(CHECK):
        try:
            d = json.load(open(CHECK))
        except ValueError:
            pass
    d.update(fields)
    json.dump(d, open(CHECK, "w"))
PATTERN = re.compile(r"claude-code/|/claude(\s|$)|^claude(\s|$)")


def notify(text):
    """Best-effort desktop notification (macOS only); never fails the run."""
    if sys.platform == "darwin":
        try:
            subprocess.run(["osascript", "-e", 'display notification %s with title "session-meter"' % json.dumps(text)],
                           capture_output=True, timeout=10)
        except Exception:
            pass


def ps_rows():
    out = subprocess.run(["ps", "-axo", "pid=,ppid=,time=,command="], capture_output=True, text=True).stdout
    rows = []
    for line in out.splitlines():
        bits = line.split(None, 3)
        if len(bits) == 4 and bits[0].isdigit() and bits[1].isdigit():
            try:
                rows.append({"pid": int(bits[0]), "ppid": int(bits[1]), "cpu": cpu_seconds(bits[2]), "cmd": bits[3]})
            except ValueError:
                pass
    return rows


def cpu_seconds(t):
    # ps "time" is [DD-][HH:]MM:SS[.hh]
    days = 0
    if "-" in t:
        d, t = t.split("-", 1)
        days = int(d)
    secs = 0.0
    for x in t.split(":"):
        secs = secs * 60 + float(x)
    return days * 86400 + secs


def other_sessions(busy_only=True):
    rows = ps_rows()
    parent = dict((r["pid"], r["ppid"]) for r in rows)
    mine, pid = set(), os.getpid()
    while pid and pid not in mine:
        mine.add(pid)
        pid = parent.get(pid)
    found = [r for r in rows if PATTERN.search(r["cmd"]) and r["pid"] not in mine
             and "disclaimer" not in r["cmd"] and "session_meter" not in r["cmd"]
             and "Claude.app/Contents/MacOS" not in r["cmd"]]
    if not busy_only:
        return found
    # An idle session spends nothing, so only the ones using the processor now are worth pausing.
    time.sleep(4)
    after = dict((r["pid"], r["cpu"]) for r in ps_rows())
    return [r for r in found if after.get(r["pid"], r["cpu"]) - r["cpu"] >= 0.2]


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
    found = other_sessions(busy_only=not a.all)
    if not found:
        print("No other Claude Code sessions are busy right now." if not a.all else "No other Claude Code sessions are running.")
        return 0
    if not a.yes:
        print("%d other Claude Code session(s) %s." % (len(found), "are running" if a.all else "are busy right now"))
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
    write_check(started=now(), paused_pids=[x["pid"] for x in paused])
    if paused:
        # Quiet backstop: they restart by themselves after 90 minutes if nobody runs 'quiet resume'.
        subprocess.Popen(["sh", "-c", "sleep 5400; kill -CONT %s 2>/dev/null" % " ".join(str(x["pid"]) for x in paused)],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    notify("Paused %d Claude Code session(s) for a meter check. They resume by themselves when it ends "
           "(about 15 minutes). Anything you type in them waits until then." % len(paused))
    print("Paused %d session(s):" % len(paused))
    for x in paused:
        print("  %s  (process %d)" % (x["folder"], x["pid"]))
    print("To restart them now: session_meter.py quiet resume")
    return 0


def finish_check(paused=None, discarded=False):
    """Clear the in-progress marker and record the check for meter_guard.py."""
    d = {}
    if os.path.exists(CHECK):
        try:
            d = json.load(open(CHECK))
        except ValueError:
            pass
        os.remove(CHECK)
    if os.path.exists(LAST_CHECK) and not d and not paused:
        return  # nothing new to record (a second resume after a discard)
    rec = {"started": d.get("started"), "ended": now(), "run": d.get("run"),
           "paused_pids": paused if paused is not None else d.get("paused_pids", []),
           "discarded": discarded or d.get("discarded", False), "told": []}
    json.dump(rec, open(LAST_CHECK, "w"))


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
    finish_check(paused=[x["pid"] for x in paused])
    notify("Meter check over. %d paused Claude Code session(s) are running again." % len(paused))
    print("Restarted %d session(s):" % len(paused))
    for x in paused:
        print("  " + x["folder"])
    return 0



def cmd_estimate(a):
    path = os.path.join(RUNS, "calibration.json")
    if not os.path.exists(path):
        print("No calibration yet. Run the quick tier and 'fit' first.")
        return 1
    c = json.load(open(path))
    pts = a.cost_usd * c["points_per_usd"]
    print("About %.1f%% of the 5-hour session (rough; measured %s on %s, %d intervals)." % (
        pts, c["date"], c.get("plan") or "unknown plan", c["intervals"]))
    return 0



# ── run: the automatic measurement ───────────────────────────────────────────────────────────

import threading
import re as _re

POLL_CMD = ["claude", "-p", "--safe-mode", "--strict-mcp-config", "--setting-sources", "",
            "--no-session-persistence", "--no-chrome", "/usage"]


def poll_meter():
    """Read the meter with 'claude -p /usage': no model call, a few seconds. Returns dict or None."""
    t0 = time.time()
    p = subprocess.run(POLL_CMD, capture_output=True, text=True, cwd=tempfile.gettempdir(), timeout=60)
    t1 = time.time()
    m = _re.search(r"Current session:\s*(\d+)% used", p.stdout)
    if not m:
        return None
    w = _re.search(r"Current week \(all models\):\s*(\d+)% used", p.stdout)
    f = _re.search(r"Current week \((?!all)[^)]*\):\s*(\d+)% used", p.stdout)
    mid = datetime.fromtimestamp((t0 + t1) / 2, timezone.utc).isoformat(timespec="seconds")
    return {"t": mid, "poll_seconds": round(t1 - t0, 1), "five_hour": int(m.group(1)),
            "weekly_all": int(w.group(1)) if w else None, "weekly_model": int(f.group(1)) if f else None}


def one_job(a):
    """Run one headless job and return its record (same shape as the 'job' command)."""
    prompt = open(a.prompt_file).read() if a.prompt_file else a.prompt
    if a.filler_words:
        prompt = filler(a.filler_words) + "\n\n" + prompt
    cmd = ["claude", "-p", "--safe-mode", "--strict-mcp-config", "--tools", "", "--setting-sources", "",
           "--no-session-persistence", "--no-chrome", "--disable-slash-commands", "--model", a.model,
           "--output-format", "json"]
    t0 = now()
    p = subprocess.run(cmd, input=prompt, capture_output=True, text=True, cwd=tempfile.gettempdir(), timeout=600)
    rec = {"type": "job", "t_start": t0, "t_end": now(), "mix": a.mix, "model": a.model, "error": None}
    try:
        d = json.loads(p.stdout)
    except ValueError:
        rec["error"] = (p.stderr or p.stdout)[-200:] or "no output"
        return rec
    u = d.get("usage") or {}
    mu = d.get("modelUsage") or {}
    rec.update({"input": u.get("input_tokens", 0), "cache_write": u.get("cache_creation_input_tokens", 0),
                "cache_read": u.get("cache_read_input_tokens", 0), "output": u.get("output_tokens", 0),
                "cost_usd": d.get("total_cost_usd"), "models": mu, "is_error": d.get("is_error")})
    if a.model not in mu:
        rec["error"] = "asked for %s, answered by %s" % (a.model, sorted(mu))
    return rec


def cmd_run(a):
    lock = threading.Lock()
    stop = threading.Event()
    state = {"readings": [], "jobs": [], "ticks": 0, "last": None, "cost_since_tick": 0.0, "tick_costs": [],
             "t_first_tick": None, "errors": 0}
    append(a.run, {"type": "run", "t": now(), "run": a.run, "plan": a.plan, "mode": "auto",
                   "workers": a.workers, "note": a.note,
                   "claude_version": subprocess.run(["claude", "--version"], capture_output=True, text=True).stdout.strip(),
                   "local_time": datetime.now().astimezone().isoformat(timespec="seconds")})
    print("Measuring. First a quick pilot to estimate the time.", flush=True)
    r0 = poll_meter()
    if not r0:
        print("Could not read the meter with 'claude -p /usage'. Use the manual 'read' and 'job' commands instead.")
        return 1
    append(a.run, dict(r0, type="meter", note="start"))
    state["last"] = r0["five_hour"]
    tp = time.time()
    pj = one_job(a)
    append(a.run, pj)
    jsecs = max(1.0, time.time() - tp)
    jcost = pj.get("cost_usd") or 0.0
    if pj.get("error") or not jcost:
        print("Pilot job failed:", pj.get("error"))
        return 1
    est_cost_pt = a.expect_usd_per_point
    secs_per_point = est_cost_pt / (a.workers * jcost / jsecs)
    total_min = min(a.max_points, 2 * (a.steps + 1)) * secs_per_point / 60.0
    known_step = None
    try:
        known_step = json.load(open(STEP_FILE)).get("step")
    except (OSError, ValueError):
        pass
    if known_step and known_step * (a.steps + 1) > a.max_points:
        print("On this account the meter moves %d points at a time, so a run of %d step(s) can cost up to %d points, "
              "over the %d-point cap. Raise --max-points to at least %d if you accept that, or measure by hand."
              % (known_step, a.steps, known_step * (a.steps + 1), a.max_points, known_step * (a.steps + 1)), flush=True)
        return 1
    if r0["five_hour"] + a.max_points > 100:
        print("The session is at %d%%, too close to its limit for a run that may spend up to %d points. "
              "Try after the reset." % (r0["five_hour"], a.max_points), flush=True)
        return 1
    print("Pilot: one job takes %.0fs and reports $%.3f; a poll takes %.0fs." % (jsecs, jcost, r0["poll_seconds"]), flush=True)
    print("Plan: %d workers. First find where the meter changes (this costs up to one step of the meter and is "
          "not measured), then measure %d full step(s)%s. Spending cap: %d points of the 5-hour session; the run "
          "stops there whatever happens." % (a.workers, a.steps,
                                            (" and at least %d points" % a.points) if a.points else "", a.max_points), flush=True)
    print("Estimated time: about %.0f minutes (at an assumed $%.2f per point; this sharpens after the first step)." % (
        total_min, est_cost_pt), flush=True)
    t_start = time.time()
    # Mark the check as in progress (meter_guard.py answers new prompts with a choice while this exists).
    write_check(run_pid=os.getpid(), run=a.run, started=now())
    discarded = {"yes": False}

    def on_term(signum, frame):
        discarded["yes"] = True
        raise SystemExit(3)
    signal.signal(signal.SIGTERM, on_term)

    def worker(delay):
        time.sleep(delay)
        while not stop.is_set():
            rec = one_job(a)
            with lock:
                append(a.run, rec)
                state["jobs"].append(rec)
                if rec.get("error"):
                    state["errors"] += 1
                else:
                    state["cost_since_tick"] += rec.get("cost_usd") or 0.0

    threads = [threading.Thread(target=worker, args=(i * 5,), daemon=True) for i in range(a.workers)]
    for t in threads:
        t.start()
    # Count points, not ticks: on some accounts the display moves more than one point at a time
    # (2026-11-23, Max plan: every change was 2 points). The first change sets the step size.
    rate = a.workers * jcost / jsecs
    state["first"] = None
    state["step"] = None
    state["target"] = None
    try:
        while state["target"] is None or state["last"] - state["first"] < state["target"]:
            r = poll_meter()
            if r is None:
                continue
            with lock:
                append(a.run, dict(r, type="meter", note="auto"))
                # A change counts only once the next reading agrees. The display can flicker for one
                # reading (2026-11-24 peak run: 49, 50, 49), which used to stop the run as a "reset".
                if r["five_hour"] == state["last"]:
                    state["pending"] = None
                elif state.get("pending") != r["five_hour"]:
                    state["pending"] = r["five_hour"]
                    continue
                else:
                    state["pending"] = None
                if r["five_hour"] < state["last"]:
                    print("The meter dropped (a reset?). Stopping; discard this run.", flush=True)
                    break
                spent = r["five_hour"] - r0["five_hour"]
                if r["five_hour"] > state["last"]:
                    jump = r["five_hour"] - state["last"]
                    if state["first"] is None and known_step and spent + known_step * a.steps > a.max_points:
                        state["first"] = r["five_hour"]
                        print("Finding the starting line cost %d points; measuring a %d-point step now would pass the "
                              "%d-point cap. Stopping; nothing measured." % (spent, known_step * a.steps, a.max_points), flush=True)
                        break
                    if state["first"] is None:
                        # The first change is not a full step (the run starts partway into one, and a
                        # fresh session can jump several points at once), so it does not set the step size.
                        state["first"] = r["five_hour"]
                        print("  first tick found: meter now %d%%" % r["five_hour"], flush=True)
                    else:
                        if state["step"] is None:
                            state["step"] = jump
                            try:
                                json.dump({"step": jump, "t": now(), "run": a.run}, open(STEP_FILE, "w"))
                            except OSError:
                                pass
                            # Measure --steps full steps after the first change (default 1: repeat runs, not
                            # extra steps, check steadiness), and at least --points points if asked.
                            state["target"] = max(a.points or 0, a.steps * jump)
                            if jump > 1:
                                print("  The meter moves %d points at a time on this account. Measuring %d points "
                                      "(%d step%s) in all." % (jump, state["target"], -(-state["target"] // jump), "" if -(-state["target"] // jump) == 1 else "s"), flush=True)
                        state["tick_costs"].append(state["cost_since_tick"] / jump)
                        print("  step found: meter now %d%%, %d of %d points measured" % (
                            r["five_hour"], r["five_hour"] - state["first"], state["target"]), flush=True)
                    state["last"] = r["five_hour"]
                    state["cost_since_tick"] = 0.0
                    if spent >= a.max_points and not (state["target"] and state["last"] - state["first"] >= state["target"]):
                        print("Spending cap reached: %d points used (cap %d). Stopping with what was measured."
                              % (spent, a.max_points), flush=True)
                        break
                per_pt = (sum(state["tick_costs"]) / len(state["tick_costs"])) if state["tick_costs"] else est_cost_pt
                per_pt = per_pt or est_cost_pt
                if state["first"] is None:
                    done, left_pts = 0, a.steps + 1
                else:
                    done = state["last"] - state["first"]
                    left_pts = (state["target"] or a.steps) - done - min(float(state["step"] or 1), state["cost_since_tick"] / per_pt)
                mins = max(0.0, left_pts * per_pt / rate / 60.0)
                print("  meter %d%%, points measured %d of %s, about $%.2f toward the next step, about %.0f min left%s" % (
                    r["five_hour"], done, state["target"] if state["target"] else "?",
                    state["cost_since_tick"], mins,
                    ("  [%d job error(s)]" % state["errors"]) if state["errors"] else ""), flush=True)
            if time.time() - t_start > a.max_minutes * 60:
                print("Time limit reached; stopping.", flush=True)
                break
    finally:
        stop.set()
        print("Stopping jobs (letting in-flight ones finish)...", flush=True)
        for t in threads:
            t.join(timeout=120)
        if discarded["yes"]:
            append(a.run, {"type": "discarded", "t": now(), "note": "discarded from the prompt guard (chose to work instead)"})
            print("Check discarded from the prompt guard. Do not use this run.", flush=True)
        try:
            pending_resume = bool(json.load(open(CHECK)).get("paused_pids"))
        except (OSError, ValueError):
            pending_resume = False
        if not pending_resume:  # nothing paused: clear the marker now; otherwise 'quiet resume' does it
            finish_check(paused=[], discarded=discarded["yes"])
    print("\nFitting.", flush=True)
    class F: pass
    f = F(); f.run = a.run
    cmd_fit(f)
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
    # Drop a reading only if it is a one-off blip (differs from both neighbours, which agree).
    steady = []
    for i, r in enumerate(meters):
        if 0 < i < len(meters) - 1 and r["five_hour"] != meters[i - 1]["five_hour"] \
                and meters[i - 1]["five_hour"] == meters[i + 1]["five_hour"]:
            continue
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
        intervals.append({"from": ticks[i - 1]["to"], "to": ticks[i]["to"], "points": pts,
                          "per_point": dict((k, v / pts) for k, v in d.items()),
                          "unc_per_point": dict((k, v / pts) for k, v in unc.items()),
                          "mix": "+".join(mixes) if mixes else "?"})
    print("Run %s: %d jobs, %d meter readings, %d ticks, %d full intervals" %
          (a.run, len(jobs), len(meters), len(ticks), len(intervals)))
    # The display can move more than one point at a time. If every step is the same size, that is
    # the meter's step, and dividing each step evenly is sound. Mixed sizes may mean a missed reading.
    sizes = sorted(set(iv["points"] for iv in intervals))
    if len(sizes) == 1 and sizes[0] > 1:
        print("The meter moved %d points at a time throughout; each step is divided evenly into points." % sizes[0])
    elif len(sizes) > 1:
        problems.append("the meter moved by different amounts (%s points); a reading may have been missed, "
                        "treat the larger steps with care" % ", ".join(str(x) for x in sizes))
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
    overall = sum(iv["per_point"]["cost"] for iv in intervals) / len(intervals)
    if overall > 0:
        plan = next((r.get("plan") for r in recs if r["type"] == "run" and r.get("plan")), None)
        cal = {"date": datetime.now().astimezone().strftime("%Y-%m-%d"), "plan": plan, "run": a.run, "intervals": len(intervals),
               "cost_usd_per_point": round(overall, 4), "points_per_usd": round(1.0 / overall, 3),
               "by_mix": dict((m, round(v, 4)) for m, v in means.items()),
               "note": "Cost is the dollar figure the headless run reports. Not corrected for the measuring session's own turns."}
        json.dump(cal, open(os.path.join(RUNS, "calibration.json"), "w"), indent=1)
        print("\nSaved runs/calibration.json: about %.1f%% of the 5-hour session per dollar of reported cost." % (1.0 / overall))
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
    s.add_argument("--all", action="store_true", help="also pause idle sessions (not normally needed)")
    s.set_defaults(f=cmd_quiet)
    s = sub.add_parser("run", help="measure automatically: jobs in parallel, meter polled, progress and time estimate")
    s.add_argument("--run", required=True); s.add_argument("--mix", required=True)
    s.add_argument("--model", required=True, help="full model id")
    s.add_argument("--prompt"); s.add_argument("--prompt-file"); s.add_argument("--filler-words", type=int, default=0)
    s.add_argument("--steps", type=int, default=1, help="full steps of the meter to measure after the first change (default 1)")
    s.add_argument("--max-points", type=int, default=6, help="spending cap in points of the 5-hour session (default 6)")
    s.add_argument("--points", type=int, default=None, help="optional: measure at least this many points (raises the cost)")
    s.add_argument("--workers", type=int, default=4, help="jobs at once")
    s.add_argument("--expect-usd-per-point", type=float, default=0.8, help="rough guess, only for the time estimate")
    s.add_argument("--max-minutes", type=int, default=60); s.add_argument("--plan"); s.add_argument("--note")
    s.set_defaults(f=cmd_run)
    s = sub.add_parser("estimate", help="turn a dollar figure from a job report into percent of the 5-hour session")
    s.add_argument("--cost-usd", type=float, required=True); s.set_defaults(f=cmd_estimate)
    s = sub.add_parser("fit"); s.add_argument("--run", required=True); s.set_defaults(f=cmd_fit)
    a = ap.parse_args()
    sys.exit(a.f(a) or 0)


if __name__ == "__main__":
    main()
