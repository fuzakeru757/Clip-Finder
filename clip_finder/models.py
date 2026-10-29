"""Shared data types."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AudioTrack:
    index: int          # stream index in the file
    codec: str
    channels: int
    title: str = ""     # OBS track titles if present, e.g. "Mic", "Game"

    @property
    def label(self) -> str:
        return self.title or f"track{self.index}"


@dataclass
class RecordingInfo:
    path: str
    duration_s: float
    video_codec: str = ""
    audio_tracks: list[AudioTrack] = field(default_factory=list)


@dataclass
class Moment:
    """One ranked keeper block, expanded to setup -> moment -> reaction."""
    start_s: float      # includes pre-roll
    peak_s: float       # loudest second
    end_s: float        # includes post-roll
    score: float        # v0.2: dB-scale (best isolated dB + bonuses), higher = more likely a keeper
    tracks_hit: list[str] = field(default_factory=list)  # labels of spiking tracks
    peak_percentile: float = 0.0
    db_above_median: float = 0.0   # best isolated-track dB above its median
    isolated_tracks_hit: list[str] = field(default_factory=list)  # spiking tracks excluding mixes

    @property
    def duration_s(self) -> float:
        return self.end_s - self.start_s


def format_timecode(seconds: float) -> str:
    """1234.5 -> '00:20:34.500' (Resolve-friendly)."""
    seconds = max(0.0, seconds)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"
