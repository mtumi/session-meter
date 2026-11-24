# Peak versus off-peak: running record

Same settings on every run, so the rows compare: `run --mix output-fast --model claude-sonnet-5-5 --prompt-file workloads/output-fast.md --workers 4 --plan Max`, other sessions quiet. From 2026-11-24 the run reads the live meter from each job's reply (one point measured after the starting gun); earlier rows read `claude /usage`, which is refreshed at most every 5 minutes, so they are averages over 5-minute jumps.
Peak means weekdays 8am to 2pm Eastern (Anthropic's March 2026 window). A lower dollar figure per point means the meter drains faster.
One row per run, appended by the run itself. No conclusion until there are at least 3 clean runs of each kind.

| Run | Local time (ET) | Kind | Dollars per point, each interval | Mean | Meter step | Clean? | Notes |
|---|---|---|---|---|---|---|---|
| e2e-2026-11-23 | Mon 6:13pm | off-peak | 1.33, 1.33, 1.33 (within 1%) | 1.33 | 2 | yes | |
| offpeak-2026-11-23 | Mon 11:13pm | off-peak | 4 intervals within 3% | 1.36 | 2 | yes | |
| peak-2026-11-24 | Tue 12:43pm | peak | 0.67 (one interval) | 0.67 | 4 | no | Several other sessions were active during it and none were paused (the busy check counts processor use only, so sessions waiting on a reply were missed). Also stopped early on a one-reading flicker (fixed 2026-11-24); no steadiness check. Leave out of averages. |
| live-headers-2026-11-24 | Tue 2:05pm | off-peak (just after the window) | 1.19, 1.36 | 1.28 | 1 | yes | Live reply readings, quiet account; hand-built load, not the run command. |
| quick-2026-11-24-1419 | Tue 2:19pm | off-peak (just after the window) | 1.18 | 1.18 | 1 | yes | First real run of the live-reading run command; 2 points used. |
