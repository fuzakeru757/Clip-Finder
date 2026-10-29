"""Outputs for Resolve: markers.csv, trimmed clips, report.html."""
from __future__ import annotations

import csv
import html
import subprocess
from pathlib import Path

from .models import Moment, format_timecode


def write_markers_csv(moments: list[Moment], out_path: str) -> str:
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["rank", "peak_timecode", "start_timecode", "end_timecode",
                    "peak_s", "start_s", "end_s", "score", "db_above_median",
                    "peak_percentile", "tracks_hit", "isolated_tracks_hit"])
        for rank, m in enumerate(moments, start=1):
            w.writerow([rank, format_timecode(m.peak_s), format_timecode(m.start_s),
                        format_timecode(m.end_s), f"{m.peak_s:.1f}", f"{m.start_s:.1f}",
                        f"{m.end_s:.1f}", m.score, m.db_above_median, m.peak_percentile,
                        ";".join(m.tracks_hit), ";".join(m.isolated_tracks_hit)])
    return out_path


def cut_clip(media_path: str, moment: Moment, out_path: str) -> str:
    """Trim one moment. Re-encodes audio to AAC so Resolve always hears it;
    video is stream-copied where possible is NOT safe with -ss accuracy,
    so this uses accurate seek + copy for speed (keyframe caveat documented in README roadmap)."""
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-ss", f"{moment.start_s:.2f}",
        "-i", media_path,
        "-t", f"{moment.duration_s:.2f}",
        "-map", "0", "-c", "copy",
        out_path,
    ]
    subprocess.run(cmd, check=True)
    return out_path


def cut_all_clips(media_path: str, moments: list[Moment], clips_dir: str) -> list[str]:
    Path(clips_dir).mkdir(parents=True, exist_ok=True)
    stem = Path(media_path).stem
    made = []
    for rank, m in enumerate(moments, start=1):
        out = str(Path(clips_dir) / f"{rank:02d}_{stem}_{int(m.peak_s)}s_score{int(m.score)}.mp4")
        made.append(cut_clip(media_path, m, out))
    return made


def write_report_html(media_path: str, moments: list[Moment], out_path: str) -> str:
    rows = "\n".join(
        f"<tr><td>{i}</td><td>{format_timecode(m.peak_s)}</td>"
        f"<td>{format_timecode(m.start_s)} – {format_timecode(m.end_s)}</td>"
        f"<td>{m.score} ({m.db_above_median} dB)</td>"
        f"<td>{html.escape('; '.join(m.isolated_tracks_hit) or '; '.join(m.tracks_hit))}</td></tr>"
        for i, m in enumerate(moments, start=1)
    )
    doc = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>Clip Finder — {html.escape(Path(media_path).name)}</title>
<style>body{{font-family:system-ui,sans-serif;margin:2rem}}table{{border-collapse:collapse}}
td,th{{border:1px solid #999;padding:.4rem .7rem}}</style></head>
<body><h1>Clip Finder moments</h1><p>{html.escape(media_path)} — {len(moments)} moments, ranked by score.</p>
<table><tr><th>#</th><th>Peak</th><th>Clip range</th><th>Score</th><th>Isolated tracks</th></tr>
{rows}</table></body></html>"""
    Path(out_path).write_text(doc, encoding="utf-8")
    return out_path
