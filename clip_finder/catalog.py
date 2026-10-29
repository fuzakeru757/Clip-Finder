"""SQLite catalog: every recording seen + every moment found.
Keeps a 1TB library from being re-processed and gives the project a
real database story (same pattern as any data pipeline)."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from .models import Moment, RecordingInfo

SCHEMA = """
CREATE TABLE IF NOT EXISTS recordings (
    id INTEGER PRIMARY KEY,
    path TEXT UNIQUE NOT NULL,
    duration_s REAL,
    video_codec TEXT,
    audio_track_count INTEGER,
    first_seen TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS moments (
    id INTEGER PRIMARY KEY,
    recording_path TEXT NOT NULL,
    start_s REAL, peak_s REAL, end_s REAL,
    score REAL, tracks_hit TEXT, peak_percentile REAL,
    created TEXT DEFAULT (datetime('now'))
);
"""


class Catalog:
    def __init__(self, db_path: str = "catalog.db"):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.executescript(SCHEMA)

    def add_recording(self, info: RecordingInfo) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO recordings (path, duration_s, video_codec, audio_track_count)"
            " VALUES (?, ?, ?, ?)",
            (info.path, info.duration_s, info.video_codec, len(info.audio_tracks)),
        )
        self.conn.commit()

    def has_recording(self, path: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM recordings WHERE path = ?", (path,)
        ).fetchone()
        return row is not None

    def add_moments(self, recording_path: str, moments: list[Moment]) -> None:
        self.conn.executemany(
            "INSERT INTO moments (recording_path, start_s, peak_s, end_s, score, tracks_hit, peak_percentile)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (recording_path, m.start_s, m.peak_s, m.end_s, m.score,
                 ",".join(m.tracks_hit), m.peak_percentile)
                for m in moments
            ],
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "Catalog":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
