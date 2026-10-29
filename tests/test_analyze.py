"""Unit tests for the pure analysis logic — no ffmpeg needed.
Run: python -m unittest discover -s tests -v
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from clip_finder.analyze import baseline_rms, describe_timestamps, find_moments, percentile_rank
from clip_finder.cli import parse_timestamp
from clip_finder.models import format_timecode


def quiet(length: int, value: float = 10.0) -> list[float]:
    return [value] * length


class TestPercentile(unittest.TestCase):
    def test_median_is_50(self):
        self.assertAlmostEqual(percentile_rank([1, 2, 3, 4, 5], 3), 50.0)

    def test_max_is_high(self):
        self.assertGreater(percentile_rank([1, 2, 3, 4, 5], 5), 80.0)


class TestFindMoments(unittest.TestCase):
    def test_single_spike_becomes_one_moment(self):
        rms = {"mic": quiet(120)}
        rms["mic"][60] = 1000.0
        moments = find_moments(rms, duration_s=120, threshold=90)
        self.assertEqual(len(moments), 1)
        self.assertEqual(moments[0].peak_s, 60.0)
        # Expanded to a keeper block: 15s setup, 30s reaction
        self.assertEqual(moments[0].start_s, 45.0)
        self.assertEqual(moments[0].end_s, 90.0)

    def test_close_peaks_merge(self):
        rms = {"mic": quiet(180)}
        rms["mic"][60] = 1000.0
        rms["mic"][70] = 900.0  # 10s later, inside the 20s merge gap
        moments = find_moments(rms, duration_s=180, threshold=90)
        self.assertEqual(len(moments), 1)

    def test_far_peaks_stay_separate(self):
        rms = {"mic": quiet(300)}
        rms["mic"][30] = 1000.0
        rms["mic"][200] = 1000.0
        moments = find_moments(rms, duration_s=300, threshold=90)
        self.assertEqual(len(moments), 2)

    def test_both_tracks_score_higher(self):
        one_track = {"mic": quiet(120)}
        one_track["mic"][60] = 1000.0
        both = {"mic": quiet(120), "game": quiet(120)}
        both["mic"][60] = 1000.0
        both["game"][60] = 1000.0
        m1 = find_moments(one_track, duration_s=120, threshold=90)[0]
        m2 = find_moments(both, duration_s=120, threshold=90)[0]
        self.assertGreater(m2.score, m1.score)
        self.assertEqual(set(m2.tracks_hit), {"mic", "game"})

    def test_clamped_to_recording_bounds(self):
        rms = {"mic": quiet(60)}
        rms["mic"][2] = 1000.0
        m = find_moments(rms, duration_s=60, threshold=90)[0]
        self.assertEqual(m.start_s, 0.0)

    def test_flat_noisy_recording_finds_nothing(self):
        # Regression: near-flat loudness with tiny wiggles. Some wiggle seconds
        # sit at a high percentile, but none are 3x the median — no moments.
        rms = {"game": [10.0, 11.0, 9.0, 10.5, 9.5] * 24}
        moments = find_moments(rms, duration_s=120, threshold=90)
        self.assertEqual(moments, [])

    def test_quiet_recording_finds_nothing(self):
        moments = find_moments({"mic": quiet(60)}, duration_s=60, threshold=99.9)
        self.assertEqual(moments, [])


class TestV02Scoring(unittest.TestCase):
    """v0.2 (Oct 28, 2026): dB above median, mix tracks excluded, voice+game bonus."""

    def test_bigger_db_outranks_smaller_db(self):
        small = {"game": quiet(120)}
        small["game"][60] = 100.0  # 20 dB above a 10 median
        big = {"game": quiet(120)}
        big["game"][60] = 10000.0  # 60 dB above a 10 median
        m_small = find_moments(small, duration_s=120, threshold=90)[0]
        m_big = find_moments(big, duration_s=120, threshold=90)[0]
        self.assertGreater(m_big.score, m_small.score)
        self.assertAlmostEqual(m_big.db_above_median, 60.0)
        self.assertAlmostEqual(m_small.db_above_median, 20.0)

    def test_mix_tracks_do_not_count_toward_distinct_bonus(self):
        # Two raw tracks spike in both cases — but in the first, one is a mix.
        mix_case = {"track1": quiet(120), "track4": quiet(120)}
        mix_case["track1"][60] = 1000.0
        mix_case["track4"][60] = 1000.0
        isolated_case = {"track2": quiet(120), "track4": quiet(120)}
        isolated_case["track2"][60] = 1000.0
        isolated_case["track4"][60] = 1000.0
        m_mix = find_moments(mix_case, duration_s=120, threshold=90)[0]
        m_iso = find_moments(isolated_case, duration_s=120, threshold=90)[0]
        self.assertEqual(m_mix.isolated_tracks_hit, ["track4"])
        self.assertGreater(m_iso.score, m_mix.score)

    def test_keeper_beats_loud_only_even_when_loud_only_is_earlier(self):
        # Regression for the Oct 28 CS2 spot-check: #1 (2:48) and #9 (1:32:40)
        # are keepers, #4 (50:34) is just loud — and #4 hit the same raw
        # tracks as the keepers. v0.1 tied them all at 110 and sorted by time;
        # v0.2 must put the voice+game keeper first even if it comes later.
        rms = {f"track{i}": quiet(180) for i in range(1, 7)}
        # Loud-only at 30s: game + both mixes spike, voices stay quiet.
        for t in ("track1", "track4", "track6"):
            rms[t][30] = 1000.0
        # Keeper at 90s: game + Discord + Mic + both mixes spike.
        for t in ("track1", "track2", "track3", "track4", "track6"):
            rms[t][90] = 1000.0
        moments = find_moments(rms, duration_s=180, threshold=90)
        self.assertEqual(len(moments), 2)
        self.assertEqual(moments[0].peak_s, 90.0)
        self.assertEqual(moments[1].peak_s, 30.0)


class TestInspect(unittest.TestCase):
    def test_parse_timestamp(self):
        self.assertEqual(parse_timestamp("168"), 168.0)
        self.assertEqual(parse_timestamp("2:48"), 168.0)
        self.assertEqual(parse_timestamp("1:32:40"), 5560.0)

    def test_inspect_peak_second_is_covered_and_in_group(self):
        rms = {"mic": quiet(180), "game": quiet(180)}
        rms["mic"][60] = 1000.0
        rms["game"][60] = 1000.0
        res = describe_timestamps(rms, [60.0], duration_s=180, threshold=90)[0]
        self.assertTrue(res["per_track"]["mic"]["is_event"])
        self.assertAlmostEqual(res["per_track"]["mic"]["db"], 40.0)
        self.assertIsNotNone(res["covering_moment"])
        self.assertEqual(res["covering_moment"].peak_s, 60.0)
        self.assertIsNotNone(res["group"])
        self.assertEqual(res["group"]["peak_s"], 60.0)

    def test_inspect_quiet_second_has_no_group_or_covering(self):
        rms = {"mic": quiet(180), "game": quiet(180)}
        rms["mic"][60] = 1000.0
        rms["game"][60] = 1000.0
        res = describe_timestamps(rms, [30.0], duration_s=180, threshold=90)[0]
        self.assertFalse(res["per_track"]["mic"]["is_event"])
        self.assertIsNone(res["group"])
        self.assertIsNone(res["covering_moment"])
        # Nearest group peak is 30s away, local best is the 60s spike.
        self.assertEqual(res["nearest_group_peak"]["peak_s"], 60.0)
        self.assertEqual(res["local_best"]["second"], 60.0)

    def test_inspect_nonpeak_event_in_chained_group(self):
        # Events at 60 and 80 chain into one group (gap 20); the group's
        # dB-peak is 60, so inspecting 80 shows it inside that group
        # even though 80 is not the group's peak — the exact situation
        # suspected for the missing CS2 keepers.
        rms = {"mic": quiet(180), "game": quiet(180)}
        rms["mic"][60] = 1000.0
        rms["game"][60] = 1000.0
        rms["game"][80] = 1000.0
        res = describe_timestamps(rms, [80.0], duration_s=180, threshold=90)[0]
        self.assertTrue(res["per_track"]["game"]["is_event"])
        self.assertIsNotNone(res["group"])
        self.assertEqual(res["group"]["first_s"], 60.0)
        self.assertEqual(res["group"]["last_s"], 80.0)


class TestV03(unittest.TestCase):
    """v0.3 (Oct 29, 2026): span-capped groups + non-zero baseline."""

    def test_baseline_uses_nonzero_median_when_median_is_zero(self):
        # Mostly-silent Mic track: median 0, non-zero seconds at 100.
        self.assertEqual(baseline_rms([0.0] * 80 + [100.0] * 40), 100.0)
        self.assertEqual(baseline_rms([0.0] * 10), 0.0)
        self.assertEqual(baseline_rms([10.0, 20.0, 30.0]), 20.0)

    def test_mostly_silent_track_spike_scores_real_db(self):
        # Regression for CS2 inspect: Mic at 1:32:40 hit 9175 RMS at the
        # 100th percentile yet scored 0.0 dB under v0.2 (median 0).
        rms = {"mic": [0.0] * 120 + [100.0] * 59 + [10000.0]}
        # Spike at 179 (10000 vs non-zero baseline 100 -> 40 dB).
        moments = find_moments(rms, duration_s=180, threshold=90)
        self.assertEqual(len(moments), 1)
        self.assertEqual(moments[0].peak_s, 179.0)
        self.assertAlmostEqual(moments[0].db_above_median, 40.0)

    def test_inspect_median_zero_track_is_event(self):
        rms = {"mic": [0.0] * 120 + [100.0] * 59 + [10000.0]}
        res = describe_timestamps(rms, [179.0], duration_s=180, threshold=90)[0]
        self.assertTrue(res["per_track"]["mic"]["is_event"])
        self.assertAlmostEqual(res["per_track"]["mic"]["db"], 40.0)

    def test_long_loud_stretch_splits_into_multiple_moments(self):
        # Events every 10s from 10s to 300s: gap-chaining alone makes
        # ONE 290s mega-group. With the default 45s span cap (v0.3.1)
        # it must split into six groups (10-50, 60-100, 110-150,
        # 160-200, 210-250, 260-300).
        rms = {"game": quiet(400)}
        for s in range(10, 301, 10):
            rms["game"][s] = 1000.0
        moments = find_moments(rms, duration_s=400, threshold=90)
        self.assertEqual(len(moments), 6)
        self.assertEqual(sorted(m.peak_s for m in moments),
                         [10.0, 60.0, 110.0, 160.0, 210.0, 260.0])

    def test_90s_span_cap_gives_three_moments(self):
        # Same stretch under the old v0.3 default (90s) for reference:
        # three groups (10-100, 110-200, 210-300).
        rms = {"game": quiet(400)}
        for s in range(10, 301, 10):
            rms["game"][s] = 1000.0
        moments = find_moments(rms, duration_s=400, threshold=90, max_group_span=90.0)
        self.assertEqual(len(moments), 3)
        self.assertEqual(sorted(m.peak_s for m in moments), [10.0, 110.0, 210.0])

    def test_span_cap_is_overridable(self):
        rms = {"game": quiet(400)}
        for s in range(10, 301, 10):
            rms["game"][s] = 1000.0
        moments = find_moments(rms, duration_s=400, threshold=90, max_group_span=10000.0)
        self.assertEqual(len(moments), 1)


class TestTimecode(unittest.TestCase):
    def test_format(self):
        self.assertEqual(format_timecode(0), "00:00:00.000")
        self.assertEqual(format_timecode(3723.25), "01:02:03.250")


if __name__ == "__main__":
    unittest.main()
