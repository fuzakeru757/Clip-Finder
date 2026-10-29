"""Loudness analysis: per-second RMS per audio track -> ranked moments.

v0.2 scoring (replaces the v0.1 percentile + any-two-tracks bonus):
  score = best isolated-track dB above its median
        + 10 if 2+ distinct *isolated* tracks spike
        +  5 if a voice track AND the game track both spike
        + peak_percentile / 100 (tiebreaker only, max 1.0)

Why: on Mikey's real CS2 run, v0.1 scores saturated at 109.7-110.0 and
every moment hit tracks 1,2,3,4,6. His OBS layout (confirmed Oct 28, 2026)
explains it: Track 1 and Track 6 are both mixes (Discord+Game+Mic, and
that + Desktop), so a loud moment trivially hit 5 "tracks" that were
really 3 sources counted twice. Mix tracks are therefore excluded from
the distinct-track count and from the voice/game test. A moment that is
only loud on the game track scores lower than one where voices react
*and* the game spikes, even if both hit the same number of raw tracks.

Defaults assume Mikey's OBS layout, where MP4 files carry no track
titles and the tool labels tracks track1..track6 in file order:
  mix tracks:   track1, track6
  voice tracks: track2 (Discord), track3 (Mic)
  game track:   track4 (Gaming)
Override with --mix-tracks / --voice-tracks / --game-track for any
other layout (e.g. when titles survive, use the titles instead).

v0.3.1 (Oct 29, 2026): default max_group_span changed 90s -> 45s, after
inspect with --max-group-span 45 proved the 2:48 keeper becomes its own
moment (peak 2:48, score 33.7, clip 2:33-3:18) under that cap, while
under 90s it lost to the 3:23 peak 35s away.

v0.3 (Oct 29, 2026) adds two fixes proven necessary by inspect on the
real CS2 file:
  - Group span cap: merged groups are split when their span exceeds
    `max_group_span` (default 90s), so a loud session can no longer
    chain-merge into 4-6 minute mega-groups with a single peak. The
    confirmed keepers at 2:48 and 1:32:40 were inside groups spanning
    5s-268s and 5312s-5653s, whose peaks (3:23, 1:28:45) produced clips
    that did not cover the keeper seconds at all.
  - Non-zero baseline: a track whose median RMS is 0 (e.g. Mic, mostly
    silent / push-to-talk) is scored against the median of its non-zero
    seconds instead of 0, so its spikes get a real dB and can win a
    peak. At 1:32:40 Mic hit 9175 RMS at the 100th percentile yet
    scored 0.0 dB under v0.2. All-zero tracks still score 0.

The pure functions have no ffmpeg dependency and are unit-tested in
tests/test_analyze.py. Only `track_rms_per_second` shells out to ffmpeg.
"""
from __future__ import annotations

import math
import subprocess
import tempfile
import wave
from statistics import median
from array import array
from pathlib import Path

from .models import Moment

DEFAULT_MIX_LABELS = frozenset({"track1", "track6"})
DEFAULT_VOICE_LABELS = frozenset({"track2", "track3"})
DEFAULT_GAME_LABEL = "track4"
DISTINCT_ISOLATED_BONUS = 10.0
VOICE_AND_GAME_BONUS = 5.0
DEFAULT_MAX_GROUP_SPAN = 45.0


# ---------------------------------------------------------------- pure logic

def percentile_rank(values: list[float], value: float) -> float:
    """What percentile is `value` at within `values`? 0-100."""
    if not values:
        return 0.0
    below = sum(1 for v in values if v < value)
    equal = sum(1 for v in values if v == value)
    return 100.0 * (below + 0.5 * equal) / len(values)


def baseline_rms(rms: list[float]) -> float:
    """A track's normal level: its median, or if that is 0 (a mostly
    silent track like a push-to-talk mic), the median of its non-zero
    seconds. Returns 0.0 only for an all-zero track."""
    if not rms:
        return 0.0
    med = median(rms)
    if med > 0:
        return med
    nonzero = [v for v in rms if v > 0]
    return median(nonzero) if nonzero else 0.0


def baselines_by_track(rms_by_track: dict[str, list[float]]) -> dict[str, float]:
    return {label: baseline_rms(rms) for label, rms in rms_by_track.items()}


def db_above_median(peak_rms: float, median_rms: float) -> float:
    """How far a peak sits above its track's normal level, in dB (capped).

    `median_rms` is really the baseline from `baseline_rms` — kept under
    the old name so existing callers and tests need no change.
    """
    if peak_rms <= 0 or median_rms <= 0:
        return 0.0
    return min(60.0, 20.0 * math.log10(peak_rms / median_rms))


def _merge_events(
    events: list[tuple[float, str, float, float]],
    merge_gap: float,
    max_group_span: float,
) -> list[list[tuple[float, str, float, float]]]:
    """Merge events into groups, split on gap OR on span.

    Chaining on gap alone lets a loud session merge into one group
    spanning minutes (the CS2 keepers were inside 263s and 341s groups).
    Capping the span at `max_group_span` from the group's first event
    forces long loud stretches to produce several moments, each with
    its own peak.
    """
    groups: list[list[tuple[float, str, float, float]]] = []
    for ev in events:
        if (groups and ev[0] - groups[-1][-1][0] <= merge_gap
                and ev[0] - groups[-1][0][0] <= max_group_span):
            groups[-1].append(ev)
        else:
            groups.append([ev])
    return groups


def _peak_events(
    rms_by_track: dict[str, list[float]], threshold: float, min_ratio: float = 3.0
) -> list[tuple[float, str, float, float]]:
    """(second, track_label, percentile, rms) for every second over threshold.

    A second must clear BOTH gates:
    - percentile: it is among the loudest seconds of THIS recording/track, and
    - ratio: it is at least `min_ratio`x the track's median loudness.
    The ratio gate matters: in a near-flat recording, tiny noise wiggles in
    quiet sections can sit at the 95th percentile while being nowhere near
    a real moment. Percentile alone produces false peaks there.
    """
    events: list[tuple[float, str, float, float]] = []
    baselines = baselines_by_track(rms_by_track)
    for label, rms in rms_by_track.items():
        if not rms:
            continue
        baseline = baselines[label]
        for sec, value in enumerate(rms):
            pct = percentile_rank(rms, value)
            if pct >= threshold and value > 0 and value >= baseline * min_ratio:
                events.append((float(sec), label, pct, value))
    return sorted(events)


def find_moments(
    rms_by_track: dict[str, list[float]],
    duration_s: float,
    threshold: float = 90.0,
    merge_gap: float = 20.0,
    pre_roll: float = 15.0,
    post_roll: float = 30.0,
    top_n: int = 20,
    min_ratio: float = 3.0,
    mix_labels: frozenset[str] | None = None,
    voice_labels: frozenset[str] | None = None,
    game_label: str | None = None,
    max_group_span: float = DEFAULT_MAX_GROUP_SPAN,
) -> list[Moment]:
    """Detect, merge, expand, score and rank moments. Ranked order returned.

    v0.2 score is dB-scale (not the v0.1 0-110 scale): best isolated-track
    dB above baseline, plus bonuses for distinct isolated sources and for
    voice+game together. Mix tracks never count toward either bonus.
    v0.3: groups are span-capped (see _merge_events) and baselines are
    non-zero (see baseline_rms).
    """
    if mix_labels is None:
        mix_labels = DEFAULT_MIX_LABELS
    if voice_labels is None:
        voice_labels = DEFAULT_VOICE_LABELS
    if game_label is None:
        game_label = DEFAULT_GAME_LABEL

    medians = baselines_by_track(rms_by_track)
    events = _peak_events(rms_by_track, threshold, min_ratio=min_ratio)
    if not events:
        return []

    groups = _merge_events(events, merge_gap, max_group_span)

    moments: list[Moment] = []
    for group in groups:
        # Peak second = the event furthest above its own track's median.
        def event_db(ev: tuple[float, str, float, float]) -> float:
            return db_above_median(ev[3], medians.get(ev[1], 0.0))

        peak_event = max(group, key=event_db)
        peak_sec, _, peak_pct, _ = peak_event
        tracks_hit = sorted({label for _, label, _, _ in group})

        # Per-track best dB in this group.
        track_db: dict[str, float] = {}
        for sec, label, pct, value in group:
            track_db[label] = max(track_db.get(label, 0.0),
                                  db_above_median(value, medians.get(label, 0.0)))

        isolated = sorted(set(tracks_hit) - set(mix_labels))
        if isolated:
            best_db = max(track_db[t] for t in isolated)
        else:
            # Mix-only file (or a layout with no isolated tracks): fall back
            # to the best raw dB so the tool still returns moments.
            best_db = max(track_db.values()) if track_db else 0.0

        score = best_db
        if len(isolated) >= 2:
            score += DISTINCT_ISOLATED_BONUS
        if isolated and (set(isolated) & set(voice_labels)) and game_label in isolated:
            score += VOICE_AND_GAME_BONUS
        score += peak_pct / 100.0  # tiebreaker only

        moments.append(Moment(
            start_s=max(0.0, peak_sec - pre_roll),
            peak_s=peak_sec,
            end_s=min(duration_s, peak_sec + post_roll) if duration_s else peak_sec + post_roll,
            score=round(score, 1),
            tracks_hit=tracks_hit,
            peak_percentile=round(peak_pct, 1),
            db_above_median=round(best_db, 1),
            isolated_tracks_hit=isolated,
        ))

    moments.sort(key=lambda m: m.score, reverse=True)
    return moments[:top_n]


# ------------------------------------------------------------- inspect mode

def describe_timestamps(
    rms_by_track: dict[str, list[float]],
    timestamps: list[float],
    duration_s: float = 0.0,
    threshold: float = 90.0,
    merge_gap: float = 20.0,
    min_ratio: float = 3.0,
    window_s: float = 30.0,
    mix_labels: frozenset[str] | None = None,
    voice_labels: frozenset[str] | None = None,
    game_label: str | None = None,
    max_group_span: float = DEFAULT_MAX_GROUP_SPAN,
) -> list[dict]:
    """Inspect exact seconds instead of guessing about them.

    For each timestamp, return:
    - per-track: RMS, median, percentile, dB above median, ratio to median,
      and whether that second clears the peak gates (is an event);
    - covering_moment: the find_moments moment whose clip range contains
      the timestamp, if any (peak, score, range);
    - group: the merged event group containing an event at that second,
      if any (first/last event second, dB-peak second), else the nearest
      group's dB-peak and its distance in seconds;
    - local_best: the loudest (highest dB) second within +/- window_s,
      across all tracks, so you can see whether the keeper second is
      near a peak without being the peak itself.

    This exists because v0.2's diagnostic (Oct 29, 2026) showed the two
    confirmed CS2 keepers (2:48, 1:32:40) absent from all 41 moments —
    the question is no longer "how do they rank?" but "why are they not
    picked as peaks at all?" This answers that from the RMS data.
    """
    medians = baselines_by_track(rms_by_track)
    events = _peak_events(rms_by_track, threshold, min_ratio=min_ratio)
    groups = _merge_events(events, merge_gap, max_group_span)

    moments = find_moments(
        rms_by_track, duration_s, threshold=threshold, merge_gap=merge_gap,
        min_ratio=min_ratio, top_n=10000,
        mix_labels=mix_labels, voice_labels=voice_labels, game_label=game_label,
        max_group_span=max_group_span,
    )

    results: list[dict] = []
    for t in timestamps:
        sec = int(t)
        per_track: dict[str, dict] = {}
        for label, rms in rms_by_track.items():
            if sec >= len(rms):
                continue
            value = rms[sec]
            med = medians.get(label, 0.0)
            pct = percentile_rank(rms, value)
            per_track[label] = {
                "rms": round(value, 1),
                "median": round(med, 1),
                "percentile": round(pct, 1),
                "db": round(db_above_median(value, med), 1),
                "ratio": round(value / med, 2) if med > 0 else 0.0,
                # Same gates as _peak_events (v0.3 fix: the old med > 0
                # check here hid median-zero tracks that the detector
                # itself counted as events).
                "is_event": bool(value > 0 and pct >= threshold
                                 and value >= med * min_ratio),
            }

        covering = None
        for m in moments:
            if m.start_s <= t <= m.end_s:
                covering = m
                break

        group_info: dict | None = None
        nearest: dict | None = None
        for group in groups:
            group_secs = [ev[0] for ev in group]
            peak_ev = max(group, key=lambda ev: db_above_median(ev[3], medians.get(ev[1], 0.0)))
            if sec in group_secs or float(sec) in group_secs:
                group_info = {
                    "first_s": min(group_secs), "last_s": max(group_secs),
                    "peak_s": peak_ev[0],
                    "peak_db": round(db_above_median(peak_ev[3], medians.get(peak_ev[1], 0.0)), 1),
                    "tracks": sorted({ev[1] for ev in group}),
                }
                break
            dist = abs(peak_ev[0] - t)
            if nearest is None or dist < nearest["distance_s"]:
                nearest = {"peak_s": peak_ev[0], "distance_s": dist}

        # Loudest second within +/- window_s, across all tracks.
        local_best: dict | None = None
        for label, rms in rms_by_track.items():
            med = medians.get(label, 0.0)
            lo = max(0, sec - int(window_s))
            hi = min(len(rms), sec + int(window_s) + 1)
            for s in range(lo, hi):
                db = db_above_median(rms[s], med)
                if local_best is None or db > local_best["db"]:
                    local_best = {"second": float(s), "track": label, "db": round(db, 1)}

        results.append({
            "timestamp_s": t,
            "per_track": per_track,
            "covering_moment": covering,
            "group": group_info,
            "nearest_group_peak": nearest,
            "local_best": local_best,
        })
    return results


# ------------------------------------------------------------- ffmpeg / audio

def _rms_from_wav(wav_path: str) -> list[float]:
    """Per-second RMS from a mono 16-bit WAV, standard library only."""
    with wave.open(wav_path, "rb") as wf:
        rate = wf.getframerate()
        frames = wf.readframes(wf.getnframes())
    samples = array("h")
    samples.frombytes(frames)
    rms: list[float] = []
    per_second = rate  # samples per second (mono)
    for start in range(0, len(samples), per_second):
        chunk = samples[start:start + per_second]
        if not chunk:
            break
        mean_sq = sum(int(s) * int(s) for s in chunk) / len(chunk)
        rms.append(mean_sq ** 0.5)
    return rms


def track_rms_per_second(media_path: str, stream_index: int) -> list[float]:
    """Decode ONE audio stream to a temp WAV via ffmpeg, return per-second RMS."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-i", media_path,
            "-map", f"0:{stream_index}",
            "-ac", "1", "-ar", "16000",
            "-c:a", "pcm_s16le",
            tmp_path,
        ]
        subprocess.run(cmd, check=True)
        return _rms_from_wav(tmp_path)
    finally:
        Path(tmp_path).unlink(missing_ok=True)
