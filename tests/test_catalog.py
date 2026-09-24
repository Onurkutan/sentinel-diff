"""Tests for sentinel_diff.catalog – deduplication and scene pair selection.

All tests are network-free, using synthetic scene dicts to exercise the
selection logic in isolation.
"""

from __future__ import annotations

from sentinel_diff.catalog import (
    _extract_cloud_cover,
    dedup_scenes,
    select_scene_pair,
)


def _scene(item_id: str, dt: str, cloud: float) -> dict:
    """Build a minimal scene dict matching search_sentinel_scenes output."""
    return {
        "id": item_id,
        "datetime": dt,
        "cloud_cover": cloud,
        "assets": [],
        "item_obj": None,
    }


class TestDedup:
    """Deduplication keeps only the latest reprocessing per product key."""

    def test_keeps_latest_processing(self):
        scenes = [
            _scene(
                "S2B_MSIL2A_20230802T084609_R107_T35TPF_20230802T163932",
                "2023-08-02T08:46:09Z",
                1.5,
            ),
            _scene(
                "S2B_MSIL2A_20230802T084609_R107_T35TPF_20241025T040038",
                "2023-08-02T08:46:09Z",
                1.5,
            ),
        ]
        result = dedup_scenes(scenes)
        assert len(result) == 1
        assert "20241025T040038" in result[0]["id"]

    def test_keeps_distinct_products(self):
        scenes = [
            _scene(
                "S2B_MSIL2A_20230802T084609_R107_T35TPF_20230802T163932",
                "2023-08-02T08:46:09Z",
                1.5,
            ),
            _scene(
                "S2A_MSIL2A_20230812T084601_R007_T35TPF_20230812T120000",
                "2023-08-12T08:46:01Z",
                2.0,
            ),
        ]
        result = dedup_scenes(scenes)
        assert len(result) == 2


class TestSelectScenePair:
    """Pair selection prefers DOY proximity, then cloud cover tiebreaker."""

    def test_prefers_doy_proximity_over_lower_cloud(self):
        """A pair with DOY gap=0 and higher cloud is preferred over
        a pair with DOY gap=20 and lower cloud."""
        before = [
            _scene("S2B_MSIL2A_20210802T084609_R107_T35TPF_20210802T163932",
                   "2021-08-02T08:46:09Z", 5.0),  # DOY 214
        ]
        after = [
            # DOY 214 (gap=0), higher cloud
            _scene("S2A_MSIL2A_20230802T084601_R007_T35TPF_20230802T120000",
                   "2023-08-02T08:46:01Z", 8.0),
            # DOY 234 (gap=20), lower cloud
            _scene("S2A_MSIL2A_20230822T084601_R007_T35TPF_20230822T120000",
                   "2023-08-22T08:46:01Z", 0.5),
        ]
        _b, a = select_scene_pair(before, after)
        assert "20230802" in a["id"]

    def test_cloud_tiebreaker_on_equal_doy(self):
        """When DOY gap is equal, lower cloud sum wins."""
        before = [
            _scene("S2B_MSIL2A_20210815T084609_R107_T35TPF_20210815T163932",
                   "2021-08-15T08:46:09Z", 3.0),  # DOY 227
        ]
        after = [
            _scene("S2A_MSIL2A_20230815T084601_R007_T35TPF_20230815T120000",
                   "2023-08-15T08:46:01Z", 7.0),   # DOY 227, gap=0, sum=10
            _scene("S2A_MSIL2A_20230815T091601_R050_T35TPF_20230815T130000",
                   "2023-08-15T09:16:01Z", 1.0),   # DOY 227, gap=0, sum=4
        ]
        _b, a = select_scene_pair(before, after)
        assert a["cloud_cover"] == 1.0

    def test_doy_distance_wraps_around_new_year(self):
        """DOY 364 (30 Dec) is 3 days from DOY 2 (2 Jan), not 362 days.
        Without circular distance the March scene (gap 61) would win."""
        before = [
            _scene("S2B_MSIL2A_20211230T084609_R107_T35TPF_20211230T163932",
                   "2021-12-30T08:46:09Z", 1.0),  # DOY 364
        ]
        after = [
            _scene("S2A_MSIL2A_20230102T084601_R007_T35TPF_20230102T120000",
                   "2023-01-02T08:46:01Z", 1.0),   # DOY 2   -> circular gap 3
            _scene("S2A_MSIL2A_20230301T084601_R007_T35TPF_20230301T120000",
                   "2023-03-01T08:46:01Z", 1.0),   # DOY 60  -> gap 61
        ]
        _b, a = select_scene_pair(before, after)
        assert "20230102" in a["id"]


class TestCloudCoverExtraction:
    """Cloud cover of 0.0 must NOT be treated as 100.0."""

    def test_zero_cloud_is_zero(self):
        assert _extract_cloud_cover({"eo:cloud_cover": 0.0}) == 0.0

    def test_none_cloud_is_hundred(self):
        assert _extract_cloud_cover({}) == 100.0
        assert _extract_cloud_cover({"eo:cloud_cover": None}) == 100.0

    def test_normal_value_preserved(self):
        assert _extract_cloud_cover({"eo:cloud_cover": 3.14}) == 3.14
