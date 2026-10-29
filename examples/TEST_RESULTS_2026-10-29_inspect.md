# Clip Finder v0.2.1 — inspect mode test results, Oct 29, 2026

## Why it exists
Oct 29 diagnostic: `analyze --top 50` on the real CS2 file found only
41 moments total, and neither confirmed keeper (2:48, 1:32:40) appeared
in any of them. Ranking was no longer the question; detection was.
Inspect mode prints, for any timestamp, the per-track numbers that
decide whether that second is a peak at all.

## What it does
`python -m clip_finder inspect <file> <timestamp> [...]`
Timestamps accept seconds (`168`), `m:ss` (`2:48`) or `h:mm:ss`
(`1:32:40`). Per timestamp it reports: per-track RMS / median /
percentile / dB above median / ratio / event-or-not; the moment whose
clip range covers it, if any; the merged event group it belongs to
(first/last event second, dB-peak, tracks) or the nearest group's peak
and distance; and the loudest second within ±30s.

## Unit tests: 17/17 pass (was 13/13)
New in `tests/test_analyze.py`: timestamp parsing (168 / 2:48 /
1:32:40), a peak second covered by its moment and in its group, a
quiet second with no group and no covering moment, and a non-peak event
inside a chained group (events at 60s and 80s chain; inspecting 80s
shows it in the group whose peak is 60s).

## End-to-end synthetic (6-track OBS layout, 120s)
`inspect obs6.mp4 1:30 0:30 1:00`:
- 1:30 (keeper): tracks 1,2,3,4,6 all events at 29.6 dB, ratio 30.1x;
  track 5 quiet; covered by moment peak 1:30, score 45.6; group 90s–90s.
- 0:30 (loud-only): tracks 1,4,6 events at 29.6 dB; Discord/Mic quiet
  (0.0 dB, not events); covered by moment peak 0:30, score 30.6.
- 1:00 (quiet): no track is an event; no event group; nearest group
  peak 0:30, 30s away. (It is inside the 0:30 moment's clip range
  because clips extend 30s past the peak — covering is by clip range,
  not by event.)

## Next step for the real file
Run from the v0.2.1 project folder:
`py -m clip_finder inspect "Z:\fretb\Recordings\OBS_Recordings\cs2.mp4" 2:48 1:32:40`
and paste the output back. That will show, for each keeper second,
whether it clears the gates on any track, and whether it sits inside a
merged group whose peak moved elsewhere.
