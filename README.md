# Clip Finder — Gameplay Highlight Automation Tool

**v0.3.1** (Oct 29, 2026) — default span cap is now 45s (see below)

A Python CLI that finds the moments worth keeping in long gameplay recordings, so a 1+ hour marker hunt becomes a ranked list you review in DaVinci Resolve — for a constantly-loud CS2 session that list is Top 100, not Top 20 (see Real-footage validation below).

Built for a real workflow: 1TB+ of OBS recordings (MKV, separate mic / game / Discord audio tracks), edited in DaVinci Resolve 21.

## The problem

Every gaming video starts the same way: scrubbing a 52-minute, 96-minute, or 3-hour recording by hand, dropping markers, hoping you didn't miss the one clutch / scare / line that makes the video. That pass takes as long as the recording itself.

## What the MVP does

**Scan → Remux → Analyze → Export**

1. **Scan** — `ffprobe` reads each recording (duration, codecs, audio tracks) and logs it in a local SQLite catalog, so files are never re-processed or duplicated.
2. **Remux** — Lossless MKV → MP4 with `ffmpeg -map 0 -c copy`. No re-encoding, all audio tracks preserved. Optional AAC fallback for audio codecs Resolve imports silently.
3. **Analyze** — Per-second loudness (RMS) for each audio track, using only the Python standard library + ffmpeg:
   - Voice-track spikes = reactions, laughter, yelling
   - Game-track spikes = action, explosions, scares
   - **Both together = scored highest** — loud game audio alone is usually just a gunfight, loud game audio *plus* your friends losing it is a clip.
4. **Export** — For each recording:
   - `markers.csv` — ranked moments: timecode, start/end, score, which tracks spiked, peak loudness
   - `clips/` — optional trimmed MP4s for each moment (setup → moment → reaction)
   - `report.html` — a simple ranked list you can scan in a browser

Clips are expanded to keeper blocks by default: **15s before** the peak (setup) and **30s after** (reaction), with nearby peaks merged so one moment doesn't become five clips.

## Install

Requirements: Python 3.10+, [ffmpeg](https://ffmpeg.org/download.html) (ffmpeg + ffprobe on your PATH). No Python packages required for the MVP.

```bash
git clone <this-repo>
cd clip-automation-tool
python -m clip_finder --help
```

V2 (optional, not required for MVP): `pip install -r requirements.txt` for Whisper transcription.

## Usage

```bash
# 1. See what's in a folder (does not modify anything)
python -m clip_finder scan "D:/Recordings/CS2"

# 2. Remux MKVs to MP4 next to the originals (originals untouched)
python -m clip_finder remux "D:/Recordings/CS2/session.mkv"

# 3. Find the moments in one file
python -m clip_finder analyze "D:/Recordings/CS2/session.mp4" --top 20

# 4. Same, but also cut the trimmed clips and build the HTML report
python -m clip_finder analyze "D:/Recordings/CS2/session.mp4" --top 20 --cut-clips --report

# Tune it per game: CS2 is loud constantly, horror games are quiet until a scare
python -m clip_finder analyze "content-warning.mp4" --percentile 95 --pre-roll 20 --post-roll 40
```

Output lands in a `clip_finder_output/` folder next to the recording (override with `--out`).

## How scoring works (v0.2)

For each second, loudness is converted to a percentile within that recording + track (so a quiet game and a loud game are judged against themselves, not an absolute volume).

- A second is a **peak** only if it clears *both* gates on a track: the percentile threshold (default 90th) **and** at least 3× that track's median loudness (`--min-ratio`). The ratio gate exists because percentile alone lies in flat recordings — tiny noise wiggles in a quiet section can sit at the 95th percentile without being anywhere near a real moment. (Found the hard way: the first end-to-end test on synthetic audio produced a false "moment" at 0:03 in pure quiet, and chain-merged the two real ones.)
- Peaks within `merge_gap` seconds (default 20s) merge into one moment.
- **Score (v0.2, dB-scale — not comparable to v0.1's 0–110 scores)** = best *isolated* track's dB above its median (`20·log10(peak / median)`, capped at 60 dB), +10 if 2+ distinct isolated tracks spike, +5 if a voice track and the game track both spike, + peak percentile / 100 as a tiebreaker only.

### Why mixes are excluded

On the first real run (CS2, Oct 23, 2026), v0.1 scores saturated at 109.7–110.0 and nearly every moment hit tracks 1, 2, 3, 4 and 6. Mikey's OBS layout (confirmed by screenshot, Oct 28, 2026) explains it: Track 1 = Discord + Gaming + Mic, Track 6 = that + Desktop Audio — both are mixes, so one loud moment counted as 5 "tracks" when it was really 3 sources counted twice. v0.2 therefore excludes mix tracks from the distinct-track count and the voice/game test. Defaults assume that layout (MP4 files carry no track titles, so tracks are labelled track1–track6 in file order):

| OBS track | Contents | v0.2 role |
|---|---|---|
| 1 | Discord + Gaming + Mic | mix — excluded |
| 2 | Discord only | voice |
| 3 | Mic only | voice |
| 4 | Gaming only | game |
| 5 | Desktop Audio only | isolated (silent in the CS2 session, so it never fired) |
| 6 | Desktop + Discord + Gaming + Mic | mix — excluded |

Override for any other layout: `--mix-tracks`, `--voice-tracks`, `--game-track` (use track titles when they survive, e.g. in MKV).

## v0.3 — segmentation + median-zero baseline (Oct 29, 2026)

Inspect on the real CS2 file proved two things, and v0.3 fixes both:

1. **Mega-groups:** the keepers sat inside event groups spanning 5s–268s
   and 5312s–5653s, because gap-chaining never breaks in a loud session.
   Groups are now split when their span exceeds `--max-group-span`
   (default 45s since v0.3.1 — roughly a clip's length — after inspect
   proved the 2:48 keeper becomes its own moment at 45s but loses to a
   peak 35s away at 90s), so a long loud stretch produces several
   moments, each with its own peak, instead of one.
2. **Median-zero tracks:** Mic's median RMS was 0.0 (mostly silent /
   push-to-talk), so its spikes scored 0.0 dB under v0.2 — at 1:32:40 Mic
   hit 9175 RMS at the 100th percentile and scored nothing. A track's
   baseline is now its median, or the median of its non-zero seconds if
   the median is 0. All-zero tracks (e.g. silent Desktop) still score 0.
   Inspect's event flag was also aligned with the detector's gates
   (it had an extra median > 0 check that hid median-zero events).

Both fixes are synthetic-verified (see
`examples/TEST_RESULTS_2026-10-29_v03.md`) and have now also been
proven on real footage — see Real-footage validation below.

## Inspect mode (v0.2.1)

When a known moment goes missing, don't guess — inspect it:

```
python -m clip_finder inspect session.mp4 2:48 1:32:40
```

For each timestamp (seconds, `m:ss`, or `h:mm:ss`), it prints per-track
RMS, median, percentile, dB above median, ratio to median, and whether
that second clears the peak gates; which moment's clip range covers it,
if any; which merged event group it belongs to (or the nearest group's
peak and distance); and the loudest second within ±30s. This was built
because the Oct 29, 2026 diagnostic showed the two confirmed CS2 keepers
absent from all 41 v0.2 moments — the question had become "why are they
not picked as peaks at all?", and only the per-second data at 168s and
5560s can answer that.

### Honest limit, confirmed by spot-check

Spot-checking the CS2 Top 20 (Oct 28, 2026): #1 (2:48) and #9 (1:32:40) are keepers, #4 (50:34) is just loud — and #4 hit the *same* raw tracks as the keepers, so track-count alone cannot separate them. v0.2's dB + voice/game bonuses prove the mechanism on synthetic audio (a voice+game keeper outranks an earlier game-only loud moment), but on the real CS2 file they do **not** separate the keepers from the loud-only moment: in the verified Top 100 run below, 50:34 is still #1 at 40.0, while the keepers sit at #86 and #36. This tool is a keeper *finder*, not a keeper *ranker* — review the list in time order, not rank order.

## Real-footage validation (Oct 29, 2026)

Test file: a 96.3-minute CS2 session (`cs2.mp4`, 6 AAC tracks), run on v0.3 with `--max-group-span 45` — equivalent to v0.3.1's new default, which is what ships here. Full output in `examples/TEST_RESULTS_2026-10-29_top100_cap45.md`.

- v0.2, Top 50: only 41 moments total, and **neither** confirmed keeper appeared at all — they were swallowed by mega-groups, not just low-ranked.
- v0.3, Top 50, cap 90s: keeper at 1:32:40 recovered (moment at 1:32:20, clip covering it); keeper at 2:48 still missing.
- v0.3, Top 100, cap 45s: **both keepers recovered.** #86 at 2:48, score 33.7 (17.7 dB), clip 2:33–3:18 — exactly as `inspect --max-group-span 45` had predicted. #36 at 1:32:20, score 37.6, clip 1:32:05–1:32:50, covering 1:32:40.
- Same Top 100 list reproduced with `--cut-clips --report`: 100 clips cut, `report.html` rebuilt, no errors.
- Ranking remains loud-first: #1 is the loud-only 50:34 at 40.0. Keeper-ness in this session is content, not volume, so no loudness score will rank the keepers first — that's what V2 transcription/tagging is for.
- Working recipe for a loud session: `analyze <file> --top 100 --max-group-span 45 --cut-clips --report` (on v0.3.1, the `--max-group-span 45` flag is optional — it's the default).

## Project structure

```
clip_finder/
  cli.py       — argparse CLI: scan / remux / analyze
  probe.py     — ffprobe wrapper: duration, codecs, audio tracks
  remux.py     — ffmpeg lossless remux (+ AAC fallback)
  analyze.py   — per-second RMS, peak detection, merging, scoring (pure logic, unit-tested)
  catalog.py   — SQLite catalog of recordings + moments (no duplicates across a 1TB library)
  export.py    — markers.csv, trimmed clips, report.html
tests/
  test_analyze.py — peak merging, expansion, and scoring tests
```

## Roadmap

- **V2 — Transcription & tagging:** faster-whisper on the voice track only; searchable transcripts; auto-tags (`funny`, `clutch`, `fail`, `scare`, `quote`) and a keyword boost (e.g. someone says "clip that").
- **V2 — Resolve timeline export:** EDL/XML with only the keepers, in session order, ready to import into a Resolve timeline.
- **V3 — UI:** drag-in-a-folder interface with sensitivity / clip-length sliders; thumbnail at each peak frame.
- **Stretch — Video signals:** killfeed / on-screen event detection for specific games (e.g. CS2).

## Testing it honestly

The best test case is a session you've *already* marker-hunted by hand. Run the tool, then ask one question: **did its list contain your gut Top 3?** (For a constantly-loud session, use Top 100 — a keeper at 17.7 dB will not crack a Top 20 of 24 dB gunfights.) If yes, the thresholds work for that game. If it buried one, lower the percentile or check whether that moment was quiet-but-funny — those are exactly what V2 transcription is for.

## Resume bullet (MVP validated on real footage, Oct 29, 2026)

> Built a Python CLI that automates highlight detection in 1TB+ of gameplay recordings — lossless MKV→MP4 remuxing via ffmpeg, multi-track audio peak analysis with a combined voice+game scoring model, a SQLite recording catalog, and ranked marker/clip export for DaVinci Resolve.

## License / status

Personal project, MVP stage. Recordings and generated clips are never uploaded anywhere — everything runs locally.
