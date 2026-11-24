#!/usr/bin/env python3
"""Claude Code UserPromptSubmit hook for session-meter.

While a meter check is in progress, any prompt you send is stopped before it reaches the model
(so it costs nothing) and answered with a choice:
  1  work now: end the check, mark it discarded, resume paused sessions; send your message again
  2  wait: the check keeps running; a notification says when it ends
After a check, the first prompt in a session that was paused gets a one-line note saying so.
Never blocks anything when no check is running, and never fails a prompt on its own error.
"""
import json
import os
import signal
import sys
import time
from datetime import datetime, timezone

CHECK = os.path.expanduser("~/.claude/session-meter-check.json")
LAST_CHECK = os.path.expanduser("~/.claude/session-meter-last-check.json")
STALE_WITHOUT_RUN = 20 * 60  # a pause with no run attached is treated as over after 20 minutes


def alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except (OSError, TypeError):
        return False


def age_seconds(iso):
    try:
        return time.time() - datetime.fromisoformat(iso).timestamp()
    except (TypeError, ValueError):
        return 1e9


def clock(iso):
    try:
        return datetime.fromisoformat(iso).astimezone().strftime("%-I:%M%p").lower()
    except (TypeError, ValueError):
        return "?"


def ancestors():
    import subprocess
    out = subprocess.run(["ps", "-axo", "pid=,ppid="], capture_output=True, text=True).stdout
    parent = {}
    for line in out.split("\n"):
        bits = line.split()
        if len(bits) == 2:
            parent[int(bits[0])] = int(bits[1])
    seen, pid = set(), os.getpid()
    while pid and pid not in seen:
        seen.add(pid)
        pid = parent.get(pid)
    return seen


def block(reason):
    print(json.dumps({"decision": "block", "reason": reason}))
    sys.exit(0)


def live_check():
    if not os.path.exists(CHECK):
        return None
    try:
        d = json.load(open(CHECK))
    except ValueError:
        return None
    pid = d.get("run_pid")
    if (pid and not alive(pid)) or (not pid and age_seconds(d.get("started")) > STALE_WITHOUT_RUN):
        try:
            os.remove(CHECK)  # left behind by a run that died; not in progress
        except OSError:
            pass
        return None
    return d


def main():
    try:
        prompt = (json.load(sys.stdin).get("prompt") or "").strip()
    except ValueError:
        prompt = ""
    d = live_check()
    if d:
        # Time left comes from the run itself: it writes its expected end ("eta") when it starts and
        # updates it at the starting gun. Before the run has started there is no estimate yet.
        # Same rounding as the run's own estimate line, so the two never disagree.
        def mins(key):
            return max(1, round(-age_seconds(d[key]) / 60.0)) if d.get(key) and -age_seconds(d[key]) > 0 else None
        typ, latest = mins("eta"), mins("eta_latest")
        if d.get("eta") is None:
            when = "starting up, estimate in a few seconds"
        elif typ is None and latest is None:
            when = "finishing now"
        elif latest and latest != typ:
            when = "about %d more minute(s), at most about %d" % (typ or 1, latest)
        else:
            when = "about %d more minute(s)" % (typ or latest)
        if prompt == "1":
            d["discarded"] = True
            json.dump(d, open(CHECK, "w"))
            for p in d.get("paused_pids", []):
                try:
                    os.kill(p, signal.SIGCONT)
                except OSError:
                    pass
            if d.get("run_pid"):
                try:
                    os.kill(d["run_pid"], signal.SIGTERM)
                except OSError:
                    pass
            block("Meter check stopped and marked discarded. Paused sessions are running again. "
                  "Send your message again.")
        if prompt == "2":
            block("OK, the check keeps running, %s. A notification says when it ends." % when)
        block("I'm running a meter check now (started %s, %s). Reply:\n"
              "1. Work now and discard this check in progress\n"
              "2. Wait until it's done" % (clock(d.get("started")), when))
    # No check running: tell a session that was paused, once, on its first prompt after the check.
    if os.path.exists(LAST_CHECK):
        try:
            last = json.load(open(LAST_CHECK))
        except ValueError:
            return
        if age_seconds(last.get("ended")) > 6 * 3600:
            return
        mine = ancestors() & set(last.get("paused_pids", []))
        if mine and not mine & set(last.get("told", [])):
            last["told"] = sorted(set(last.get("told", [])) | mine)
            json.dump(last, open(LAST_CHECK, "w"))
            print(json.dumps({"systemMessage": "This session was paused for a meter check from %s to %s%s. "
                              "Anything you typed during it is being handled now." % (
                                  clock(last.get("started")), clock(last.get("ended")),
                                  " (the check was discarded)" if last.get("discarded") else "")}))


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)  # never get in the way of a prompt because of a bug here
