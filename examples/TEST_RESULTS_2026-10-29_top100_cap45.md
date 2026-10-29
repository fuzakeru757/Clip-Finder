# Test results — Top 100, cap 45s, real CS2 footage (Oct 29, 2026)

## Run

File: 96.3-minute CS2 session, `cs2.mp4` (6 AAC tracks), already MP4 so no remux.

Command (run on the PC install of v0.3, with the cap passed as a flag):

```
py -m clip_finder analyze "Z:\fretb\Recordings\OBS_Recordings\cs2.mp4" --top 100 --max-group-span 45
py -m clip_finder analyze "Z:\fretb\Recordings\OBS_Recordings\cs2.mp4" --top 100 --max-group-span 45 --cut-clips --report
```

The code shipped here is v0.3.1, whose only change from v0.3 is making
45s the default `--max-group-span`. For this run the two are equivalent:
same grouping logic, same flag value, same output.

## Result — both confirmed keepers recovered

The list was full at 100, so the file has at least 100 moments total.

- **#86 — 00:02:48, score 33.7 (17.7 dB), tracks 2/3/4, clip 00:02:33–00:03:18.**
  Exactly as `inspect --max-group-span 45` had predicted: under a 45s cap
  2:48 is its own group's peak (group 149s–192s), where under the 90s cap
  it lost to the 3:23 peak at 22.2 dB.
- **#36 — 01:32:20, score 37.6 (21.6 dB), tracks 2/3/4, clip 01:32:05–01:32:50.**
  This clip covers the second confirmed keeper at 1:32:40, 20s after the peak,
  inside the post-roll.
- **#1 — 00:50:34, score 40.0 (24.0 dB).** Still the loud-only moment from
  the original spot-check. Ranking is loud-first, not keeper-first.

The `--cut-clips --report` run reproduced the identical Top 100 list,
cut 100 clips into `clip_finder_output/clips`, and rebuilt `report.html`
with no errors.

## What this proves, and what it does not

Proves: with a 45s group-span cap, neither keeper is swallowed by a
mega-group anymore, and both are findable in a Top 100 list for a
constantly-loud session. The 2:48 keeper only scores 33.7, so a Top 50
cutoff (36.7 in the earlier cap-45 run) truncates it — Top 100 is the
working size for this kind of footage.

Does not prove: keeper-first ranking. A loudness score cannot separate
these keepers from gunfights in this session (see README, Honest limit).
Review the list in time order, not rank order. Transcription/tagging
(V2 roadmap) is the planned discriminator for content, not volume.

## History on this file, for context

- v0.1 Top 20: keepers at #1 (2:48) and #9 (1:32:40) only because all
  scores tied at 110.0 and ties stayed chronological — not because the
  ranking found them.
- v0.2 Top 50: 41 moments total, neither keeper present at all.
- v0.3 Top 50, cap 90s: 1:32:40 recovered, 2:48 still missing.
- v0.3 Top 100, cap 45s: both recovered (this run).
