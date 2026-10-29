"""ffprobe wrapper: what is this recording, and what tracks does it have?"""
from __future__ import annotations

import json
import shutil
import subprocess

from .models import AudioTrack, RecordingInfo


def require_ffmpeg_tools() -> None:
    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool) is None:
            raise RuntimeError(
                f"{tool} not found on PATH. Install ffmpeg: https://ffmpeg.org/download.html"
            )


def probe_file(path: str) -> RecordingInfo:
    require_ffmpeg_tools()
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_format", "-show_streams",
        path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)

    duration = float(data.get("format", {}).get("duration", 0.0))
    video_codec = ""
    audio_tracks: list[AudioTrack] = []

    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video" and not video_codec:
            video_codec = stream.get("codec_name", "")
        elif stream.get("codec_type") == "audio":
            tags = stream.get("tags", {}) or {}
            audio_tracks.append(AudioTrack(
                index=int(stream["index"]),
                codec=stream.get("codec_name", ""),
                channels=int(stream.get("channels", 0)),
                title=tags.get("title", "") or tags.get("TITLE", ""),
            ))

    return RecordingInfo(
        path=path,
        duration_s=duration,
        video_codec=video_codec,
        audio_tracks=audio_tracks,
    )
