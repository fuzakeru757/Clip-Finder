# Clip Finder v0.2 test results — Oct 28, 2026

## What changed
Scoring replaced (v0.1: peak percentile + 10 if 2+ tracks hit, which
saturated at 109.7–110.0 on the real CS2 run). v0.2 score is dB-scale:
best isolated-track dB above its median, +10 for 2+ distinct isolated
tracks, +5 for voice + game together, + peak percentile/100 tiebreaker.
Mix tracks (default track1, track6 — Mikey's OBS layout) never count
toward the bonuses. New CLI flags: `--mix-tracks`, `--voice-tracks`,
`--game-track`. `markers.csv` gains `db_above_median` and
`isolated_tracks_hit` columns. Scores are NOT comparable to v0.1 scores.

## Unit tests: 13/13 pass (was 10/10)
New tests in `tests/test_analyze.py`:
- `test_bigger_db_outranks_smaller_db` — 60 dB peak outranks 20 dB peak.
- `test_mix_tracks_do_not_count_toward_distinct_bonus` — two raw tracks
  spike in both cases, but the mix+game case scores below the
  Discord+game case; `isolated_tracks_hit` is `["track4"]` for the mix case.
- `test_keeper_beats_loud_only_even_when_loud_only_is_earlier` — the
  Oct 28 CS2 spot-check regression: a game-only loud moment at 30s vs a
  voice+game keeper at 90s, both hitting the same raw mix tracks.
  v0.2 ranks the keeper #1, the loud-only moment #2.

## End-to-end synthetic (6-track, mimicking Mikey's OBS layout)
180s MP4, black video + 6 AAC tracks:
track1 mix, track2 Discord, track3 Mic, track4 Gaming, track5 Desktop
(silent), track6 mix. Loud-only burst at 30s (game + mixes), keeper
burst at 90s (game + Discord + Mic + mixes). Run with default flags:

```
#1  00:01:30.000  score 45.6  (29.6 dB)  [track2; track3; track4]  clip 00:01:15–00:02:00
#2  00:00:30.000  score 30.6  (29.6 dB)  [track4]                 clip 00:00:15–00:01:00
```

Same dB on both moments (same burst amplitude), but the keeper wins by
15 points exactly from the +10 distinct-isolated and +5 voice+game
bonuses, and the earlier loud-only moment drops to #2. Track 5 never
fired, matching the real CS2 run. Clips cut, markers.csv and report.html
written, zero errors.

## Still NOT verified
Whether v0.2 separates the real keepers (#1 at 2:48, #9 at 1:32:40)
from the real loud-only moment (#4 at 50:34) on Mikey's actual CS2 file.
That needs a re-run on his PC: `py -m clip_finder analyze
"Z:\fretb\Recordings\OBS_Recordings\cs2.mp4" --top 20 --cut-clips --report`
with the v0.2 code installed (defaults already match his OBS layout).
If #1/#9 outrank #4 in the new list, the fix works on real footage;
if not, the next discriminator is voice-vs-game ratio, not track count.
