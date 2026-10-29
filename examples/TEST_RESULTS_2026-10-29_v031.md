# Clip Finder v0.3.1 test results — Oct 29, 2026

## What changed (one line)
Default `--max-group-span` changed from 90s to 45s in both `analyze`
and `inspect`. No scoring change. The flag still overrides it.

## Why
Real-file proof, not a guess: under the 90s cap, inspect at 2:48
showed a group of 149s–239s whose peak was 3:23 (22.2 dB), 35s after
the keeper. Under `--max-group-span 45`, inspect at 2:48 showed a
group of 149s–192s whose peak IS 2:48 (17.7 dB), covered by a moment
with clip 2:33–3:18 — exactly the original v0.1 keeper clip — at
score 33.7. The keeper's score is 33.7 (not ~18.7 as first estimated)
because a moment's tracks are the union across its group, so it still
earns the +10 distinct and +5 voice+game bonuses. That is only 3.0
points below the cap-45 Top 50 cutoff (36.7), so it exists as a
moment just outside Top 50 — use `--top 100` (or more) to include it,
rather than expecting it in a Top 50 list.

## Unit tests: 23/23 pass (was 22/22)
The mega-group test was updated for the new default (events every
10s, 10s–300s → 6 moments, peaks 10/60/110/160/210/260) and a
reference test for the old 90s cap was kept (→ 3 moments, peaks
10/110/210). No other test changed.

## Still to verify on real footage
Run `analyze --top 100` (no flag needed now) and confirm 2:48
appears in markers.csv, and that 1:32:40 is still covered by its
1:32:20 moment.
