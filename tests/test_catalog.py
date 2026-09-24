"""Tests for sentinel_diff.catalog – deduplication and scene pair selection.

All tests are network-free, using synthetic scene dicts to exercise the
selection logic in isolation.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import planetary_computer as pc
import pytest

import sentinel_diff.catalog as catalog_module
from sentinel_diff.catalog import (
    EARTHSEARCH_STAC_URL,
    PROVIDERS,
    _extract_cloud_cover,
    dedup_scenes,
    get_provider,
    search_sentinel_scenes,
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

    def test_earthsearch_keeps_latest_reprocessing(self):
        """Earth Search IDs: 4th segment is the reprocessing sequence; _1_ wins over _0_."""
        scenes = [
            _scene("S2B_35TPF_20230802_0_L2A", "2023-08-02T08:59:04Z", 0.3),
            _scene("S2B_35TPF_20230802_1_L2A", "2023-08-02T08:59:04Z", 0.3),
        ]
        result = dedup_scenes(scenes)
        assert len(result) == 1
        assert result[0]["id"] == "S2B_35TPF_20230802_1_L2A"

    def test_earthsearch_keeps_distinct_dates(self):
        scenes = [
            _scene("S2B_35TPF_20230802_0_L2A", "2023-08-02T08:59:04Z", 0.3),
            _scene("S2A_35TPF_20230820_0_L2A", "2023-08-20T09:09:01Z", 3.9),
        ]
        result = dedup_scenes(scenes)
        assert len(result) == 2

    def test_mixed_id_formats_dedup_independently(self):
        """ESA and Earth Search IDs in one list: each format dedups on its own key."""
        scenes = [
            _scene("S2B_MSIL2A_20230802T084609_R107_T35TPF_20230802T163932",
                   "2023-08-02T08:46:09Z", 1.5),
            _scene("S2B_MSIL2A_20230802T084609_R107_T35TPF_20241025T040038",
                   "2023-08-02T08:46:09Z", 1.5),
            _scene("S2B_35TPF_20230802_0_L2A", "2023-08-02T08:59:04Z", 0.3),
            _scene("S2B_35TPF_20230802_1_L2A", "2023-08-02T08:59:04Z", 0.3),
        ]
        result = dedup_scenes(scenes)
        ids = sorted(r["id"] for r in result)
        assert ids == [
            "S2B_35TPF_20230802_1_L2A",
            "S2B_MSIL2A_20230802T084609_R107_T35TPF_20241025T040038",
        ]


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


# ── Provider registry ────────────────────────────────────────────────────


class _FakeClient:
    """Stands in for pystac_client.Client: records .search kwargs and yields stub items."""

    def __init__(self, items):
        self._items = items
        self.search_kwargs = None

    def search(self, **kwargs):
        self.search_kwargs = kwargs
        items = self._items
        return SimpleNamespace(items=lambda: iter(items))


def _stub_item(item_id: str, asset_keys: list[str]):
    return SimpleNamespace(
        id=item_id,
        datetime=datetime(2023, 8, 2, 8, 59, 4, tzinfo=timezone.utc),
        properties={"eo:cloud_cover": 0.35},
        assets={k: SimpleNamespace(href=f"https://example.invalid/{k}.tif") for k in asset_keys},
    )


@pytest.fixture
def fake_client_open(monkeypatch):
    """Monkeypatch Client.open to record its arguments and return a _FakeClient."""
    calls: dict = {}

    def fake_open(url, modifier=None, **kwargs):
        calls["url"] = url
        calls["modifier"] = modifier
        client = _FakeClient(calls.get("items", []))
        calls["client"] = client
        return client

    monkeypatch.setattr(catalog_module.Client, "open", staticmethod(fake_open))
    return calls


class TestProviders:
    def test_registry_names(self):
        assert set(PROVIDERS) == {"pc", "earthsearch"}
        assert get_provider("EarthSearch").name == "earthsearch"
        with pytest.raises(ValueError, match="Unknown STAC provider"):
            get_provider("nope")

    def test_earthsearch_asset_map_is_canonical_to_provider(self):
        prov = get_provider("earthsearch")
        assert prov.asset_map == {"B03": "green", "B08": "nir", "B11": "swir16", "SCL": "scl"}
        assert prov.modifier is None
        assert prov.collection == "sentinel-2-l2a"

    def test_search_earthsearch_opens_url_without_modifier(self, fake_client_open):
        fake_client_open["items"] = [
            _stub_item("S2B_35TPF_20230802_0_L2A", ["green", "nir", "swir16", "scl"])
        ]
        scenes = search_sentinel_scenes(
            [28.87, 41.10, 28.96, 41.17], "2023-08-01/2023-08-31",
            max_cloud_cover=10, max_items=5, provider="earthsearch",
        )
        assert fake_client_open["url"] == EARTHSEARCH_STAC_URL
        assert fake_client_open["modifier"] is None
        assert fake_client_open["client"].search_kwargs["collections"] == ["sentinel-2-l2a"]
        assert len(scenes) == 1
        assert scenes[0]["provider"] == "earthsearch"
        assert scenes[0]["id"] == "S2B_35TPF_20230802_0_L2A"
        assert scenes[0]["cloud_cover"] == 0.35
        assert sorted(scenes[0]["assets"]) == ["green", "nir", "scl", "swir16"]

    def test_search_pc_default_uses_sign_inplace(self, fake_client_open):
        scenes = search_sentinel_scenes([28.87, 41.10, 28.96, 41.17], "2023-08-01/2023-08-31")
        assert fake_client_open["url"] == catalog_module.DEFAULT_STAC_URL
        assert fake_client_open["modifier"] is pc.sign_inplace
        assert scenes == []

    def test_stac_url_override_wins_over_provider(self, fake_client_open):
        search_sentinel_scenes(
            [0, 0, 1, 1], "2023-08-01/2023-08-31",
            stac_url="https://stac.example.invalid/v1", provider="earthsearch",
        )
        assert fake_client_open["url"] == "https://stac.example.invalid/v1"
        assert fake_client_open["modifier"] is None
