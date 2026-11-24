#!/bin/sh
# One peak-versus-off-peak measuring run, started by hand. Pauses every other Claude Code
# session until the run ends (a few minutes; the run prints its estimate) and resumes them, even if the run fails.
KIND=${1:-peak}
REPO=$(cd "$(dirname "$0")/.." && pwd)
RUN=$KIND-$(date +%Y-%m-%d-%H%M)
WORK=$(mktemp -d)/sm
cp -R "$REPO" "$WORK" && cd "$WORK" || exit 1
LOG="$REPO/runs/$RUN.log"
{
  echo "=== $RUN start $(date)"
  claude -p --setting-sources "" "/usage" | head -5
  python3 scripts/session_meter.py quiet pause --all --yes
  trap 'python3 scripts/session_meter.py quiet resume' EXIT
  python3 scripts/session_meter.py run --run "$RUN" --mix output-fast --model claude-sonnet-5-5 \
    --prompt-file workloads/output-fast.md --workers 4 --plan Max \
    --note "$KIND run, started by hand, all other sessions paused"
  echo "=== end $(date)"
  claude -p --setting-sources "" "/usage" | head -5
} 2>&1 | tee "$LOG"
cp "runs/$RUN.jsonl" "$REPO/runs/"
cp runs/calibration.json "$REPO/runs/calibration_$RUN.json"
echo "Done. Log: $LOG"
