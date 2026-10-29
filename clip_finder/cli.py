"""CLI: scan / remux / analyze.

Examples:
  python -m clip_finder scan "D:/Recordings/CS2"
  python -m clip_finder remux session.mkv
  python -m clip_finder analyze session.mp4 --top 20 --cut-clips --report
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .analyze import describe_timestamps, find_moments, track_rms_per_second
from .catalog import Catalog
from .export import cut_all_clips, write_markers_csv, write_report_html
from .models import format_timecode
from .probe import probe_file, require_ffmpeg_tools
from .remux import remux_file

VIDEO_EXTS = {".mkv", ".mp4", ".mov", ".m4v"}


def _iter_recordings(target: str) -> list[str]:
    p = Path(target)
    if p.is_file():
        return [str(p)]
    return sorted(str(f) for f in p.rglob("*") if f.suffix.lower() in VIDEO_EXTS)


def parse_timestamp(text: str) -> float:
    """'168', '2:48' and '1:32:40' all -> seconds (float)."""
    text = text.strip()
    if ":" in text:
        parts = [float(p) for p in text.split(":")]
        total = 0.0
        for part in parts:
            total = total * 60.0 + part
        return total
    return float(text)


def cmd_inspect(args: argparse.Namespace) -> int:
    info = probe_file(args.file)
    if not info.audio_tracks:
        print("No audio tracks found — nothing to inspect.", file=sys.stderr)
        return 1

    rms_by_track: dict[str, list] = {}
    for track in info.audio_tracks:
        print(f"Analyzing {track.label} ...")
        rms_by_track[track.label] = track_rms_per_second(args.file, track.index)

    timestamps = [parse_timestamp(t) for t in args.timestamps]
    results = describe_timestamps(
        rms_by_track, timestamps,
        duration_s=info.duration_s,
        threshold=args.percentile,
        merge_gap=args.merge_gap,
        min_ratio=args.min_ratio,
        window_s=args.window,
        max_group_span=args.max_group_span,
    )
    for res in results:
        t = res["timestamp_s"]
        print(f"\n== {format_timecode(t)} ({t:.0f}s) ==")
        print(f"  {'track':<10} {'rms':>8} {'median':>8} {'pct':>6} {'dB':>6} {'ratio':>6}  event?")
        for label, row in res["per_track"].items():
            print(f"  {label:<10} {row['rms']:>8} {row['median']:>8} {row['percentile']:>6} "
                  f"{row['db']:>6} {row['ratio']:>6}  {'YES' if row['is_event'] else '-'}")
        m = res["covering_moment"]
        if m is not None:
            print(f"  Covered by moment: peak {format_timecode(m.peak_s)}, score {m.score}, "
                  f"clip {format_timecode(m.start_s)}–{format_timecode(m.end_s)}")
        else:
            print("  Covered by moment: none — this second is in no moment's clip range.")
        g = res["group"]
        if g is not None:
            print(f"  Event group: events {g['first_s']:.0f}s–{g['last_s']:.0f}s, "
                  f"dB-peak {format_timecode(g['peak_s'])} ({g['peak_db']} dB), "
                  f"tracks {'; '.join(g['tracks'])}")
        elif res["nearest_group_peak"] is not None:
            n = res["nearest_group_peak"]
            print(f"  Event group: none at this second — nearest group peak "
                  f"{format_timecode(n['peak_s'])} ({n['distance_s']:.0f}s away).")
        lb = res["local_best"]
        if lb is not None:
            print(f"  Loudest second within ±{args.window:.0f}s: {format_timecode(lb['second'])} "
                  f"on {lb['track']} ({lb['db']} dB)")
    return 0


def cmd_scan(args: argparse.Namespace) -> int:
    files = _iter_recordings(args.target)
    if not files:
        print("No recordings found.")
        return 1
    with Catalog(args.catalog) as cat:
        for path in files:
            info = probe_file(path)
            cat.add_recording(info)
            tracks = ", ".join(f"{t.label} ({t.codec})" for t in info.audio_tracks) or "none"
            print(f"{path}\n  {info.duration_s/60:.1f} min · video {info.video_codec or '?'} · audio: {tracks}")
    print(f"\nCataloged {len(files)} recording(s) in {args.catalog}")
    return 0


def cmd_remux(args: argparse.Namespace) -> int:
    out = remux_file(args.file, aac_fallback=args.aac)
    print(f"Remuxed -> {out}")
    return 0


def cmd_analyze(args: argparse.Namespace) -> int:
    info = probe_file(args.file)
    if not info.audio_tracks:
        print("No audio tracks found — nothing to analyze.", file=sys.stderr)
        return 1

    rms_by_track: dict[str, list] = {}
    for track in info.audio_tracks:
        print(f"Analyzing {track.label} ...")
        rms_by_track[track.label] = track_rms_per_second(args.file, track.index)

    def _label_set(text: str | None) -> frozenset[str] | None:
        if text is None:
            return None
        return frozenset(s.strip() for s in text.split(",") if s.strip())

    moments = find_moments(
        rms_by_track,
        duration_s=info.duration_s,
        threshold=args.percentile,
        merge_gap=args.merge_gap,
        pre_roll=args.pre_roll,
        post_roll=args.post_roll,
        top_n=args.top,
        min_ratio=args.min_ratio,
        mix_labels=_label_set(args.mix_tracks),
        voice_labels=_label_set(args.voice_tracks),
        game_label=args.game_track,
        max_group_span=args.max_group_span,
    )
    if not moments:
        print("No moments cleared the threshold. Try a lower --percentile (e.g. 85).")
        return 0

    out_dir = Path(args.out) if args.out else Path(args.file).parent / "clip_finder_output"
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = write_markers_csv(moments, str(out_dir / "markers.csv"))
    print(f"\n{len(moments)} moment(s) -> {csv_path}")
    for rank, m in enumerate(moments, start=1):
        print(f"  #{rank}  {format_timecode(m.peak_s)}  score {m.score}  ({m.db_above_median} dB)  "
              f"[{'; '.join(m.isolated_tracks_hit) or '; '.join(m.tracks_hit)}]  clip {format_timecode(m.start_s)}–{format_timecode(m.end_s)}")

    if args.cut_clips:
        made = cut_all_clips(args.file, moments, str(out_dir / "clips"))
        print(f"Cut {len(made)} clip(s) into {out_dir / 'clips'}")
    if args.report:
        report = write_report_html(args.file, moments, str(out_dir / "report.html"))
        print(f"Report -> {report}")

    with Catalog(args.catalog) as cat:
        cat.add_recording(info)
        cat.add_moments(args.file, moments)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="clip_finder", description="Find the keepers in long gameplay recordings.")
    p.add_argument("--catalog", default="catalog.db", help="SQLite catalog path (default: catalog.db)")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("scan", help="Catalog recordings in a file/folder (no changes to files)")
    s.add_argument("target")
    s.set_defaults(func=cmd_scan)

    r = sub.add_parser("remux", help="Lossless MKV -> MP4, all audio tracks preserved")
    r.add_argument("file")
    r.add_argument("--aac", action="store_true", help="Re-encode audio to AAC (for codecs Resolve imports silently)")
    r.set_defaults(func=cmd_remux)

    a = sub.add_parser("analyze", help="Detect loudness moments and export markers")
    a.add_argument("file")
    a.add_argument("--top", type=int, default=20)
    a.add_argument("--percentile", type=float, default=90.0, help="Peak threshold percentile per track (default 90)")
    a.add_argument("--min-ratio", type=float, default=3.0, help="Peak must be at least this many x the track median loudness (default 3.0) — kills quiet-section noise peaks")
    a.add_argument("--mix-tracks", default="track1,track6", help="Comma-separated track labels that are mixes, excluded from distinct-track bonuses (default: track1,track6 — Mikey's OBS layout)")
    a.add_argument("--voice-tracks", default="track2,track3", help="Comma-separated voice track labels (default: track2,track3 — Discord, Mic)")
    a.add_argument("--game-track", default="track4", help="Game track label (default: track4)")
    a.add_argument("--max-group-span", type=float, default=45.0, help="Split a merged event group when its span exceeds this many seconds (default 45) — stops long loud stretches collapsing into one moment")
    a.add_argument("--merge-gap", type=float, default=20.0)
    a.add_argument("--pre-roll", type=float, default=15.0)
    a.add_argument("--post-roll", type=float, default=30.0)
    a.add_argument("--cut-clips", action="store_true")
    a.add_argument("--report", action="store_true")
    a.add_argument("--out", default=None, help="Output folder (default: <recording folder>/clip_finder_output)")
    a.set_defaults(func=cmd_analyze)

    i = sub.add_parser("inspect", help="Inspect exact seconds: per-track dB/percentile, covering moment, merged group")
    i.add_argument("file")
    i.add_argument("timestamps", nargs="+", help="Seconds ('168') or timecodes ('2:48', '1:32:40')")
    i.add_argument("--percentile", type=float, default=90.0)
    i.add_argument("--min-ratio", type=float, default=3.0)
    i.add_argument("--merge-gap", type=float, default=20.0)
    i.add_argument("--window", type=float, default=30.0, help="Local-best window in seconds (default 30)")
    i.add_argument("--max-group-span", type=float, default=45.0, help="Split a merged event group when its span exceeds this many seconds (default 45)")
    i.set_defaults(func=cmd_inspect)
    return p


def main(argv: list[str] | None = None) -> int:
    require_ffmpeg_tools()
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
