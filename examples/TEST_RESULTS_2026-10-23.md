# End-to-end test — 2026-10-23 (synthetic recording)

A synthetic 120-second MKV was generated with two audio tracks and known loud bursts, so the detector's answers could be checked against ground truth:

- **Mic track:** loud bursts at 59–63s and 99–103s, quiet otherwise
- **Game track:** loud burst at 59–63s only

Expected: exactly 2 moments — the 60s moment ranked #1 (both tracks spiking), the 100s moment #2 (mic only).

## Result after fix: PASS

```
#1  00:01:01.000  score 109.6  [both tracks]  clip 00:00:46–00:01:31
#2  00:01:39.000  score  99.6  [mic only]     clip 00:01:24–00:02:00
```

10/10 unit tests pass (`python -m unittest discover -s tests -v`).

## What the first run caught (kept honest)

The first end-to-end run was **wrong**: a false moment at 0:03 in pure quiet, and the two real moments chain-merged into one. Two causes:

1. Percentile alone lies in flat recordings — tiny noise wiggles in quiet audio can sit at the 95th percentile. Fix: a peak must also be ≥3× the track's median loudness (`--min-ratio`).
2. The false peaks bridged the real peaks during merge-grouping. With the noise peaks gone, merging works as intended.

Full ranked output is in `example_markers.csv` in this folder.
