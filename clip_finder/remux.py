"""Lossless MKV -> MP4 remux. Container swap only, never a re-encode
(except the optional AAC audio fallback for codecs Resolve imports silently)."""
from __future__ import annotations

import subprocess
from pathlib import Path


def remux_file(src: str, dst: str | None = None, aac_fallback: bool = False) -> str:
    src_path = Path(src)
    out_path = Path(dst) if dst else src_path.with_suffix(".mp4")
    if out_path.exists():
        raise FileExistsError(f"Refusing to overwrite existing file: {out_path}")

    audio_args = ["-c:a", "aac"] if aac_fallback else ["-c:a", "copy"]
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-i", str(src_path),
        "-map", "0",            # every stream: video + ALL audio tracks
        "-c:v", "copy",
        *audio_args,
        str(out_path),
    ]
    subprocess.run(cmd, check=True)
    return str(out_path)
