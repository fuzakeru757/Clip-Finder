# Clip Finder v0.3 test results — Oct 29, 2026

## What changed
- Group span cap: `--max-group-span` (default 90s). A merged event
  group splits when its span from first event exceeds 90s, in addition
  to the existing 20s gap split. Stops loud sessions chain-merging
  into 4–6 minute mega-groups with a single peak.
- Non-zero baseline: `baseline_rms` = track median, or median of
  non-zero seconds if the median is 0. Used for the ratio gate, dB,
  and inspect. All-zero tracks still baseline 0 and score 0.
- Inspect `is_event` aligned with `_peak_events` (removed the extra
  median > 0 check that hid median-zero tracks in inspect output).

## Unit tests: 22/22 pass (was 17/17)
New in `tests/test_analyze.py` (TestV03):
- Baseline: mostly-zero track baselines to its non-zero median.
- Mostly-silent spike: 10000 RMS spike on a track that is zero 120/180
  seconds scores 40.0 dB (baseline 100), not 0.0 dB.
- Inspect median-zero: that spike shows as an event at 40.0 dB.
- Mega-group split: events every 10s from 10s to 300s produce 3 moments
  (peaks 10, 110, 210) with the default 90s cap, and 1 moment with
  `--max-group-span 10000` (cap disabled).

## End-to-end synthetic (dense loud stretch, 360s)
6-track file: Discord/Game/mixes bursting every 15s from 30s to 300s,
Mic bursting once at 168s, Desktop silent. Under v0.2 this would be
one 270s mega-group. Under v0.3, `analyze --top 20` returns 3 moments:
- #1 peak 60s, score 45.6 (29.6 dB), isolated track2;track4
- #2 peak 135s, score 45.6 (29.6 dB), isolated track2;track3;track4
- #3 peak 255s, score 45.6 (29.6 dB), isolated track2;track4
`inspect mega.mp4 2:48` shows the Mic spike at 168s as an event at
29.6 dB, inside the 135s–225s group. (Its group peak is 135s, not 168s,
because every burst in this synthetic has identical amplitude — in
real audio the loudest second in a sub-group wins, which is the point
of splitting: the keeper no longer competes with peaks minutes away.)

## Still NOT verified
Whether 2:48 and 1:32:40 surface as moments on the real CS2 file.
Run from the v0.3 project folder:
`py -m clip_finder analyze "Z:\fretb\Recordings\OBS_Recordings\cs2.mp4" --top 50`
and check whether those timestamps appear, and with what scores.
