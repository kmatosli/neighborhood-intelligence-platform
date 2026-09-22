"""The ward-coverage measurement on synthetic polygons whose answers are known exactly."""

from __future__ import annotations

import geopandas as gpd
import pytest
from shapely.geometry import box

from bw_observatory.geography.ward_coverage import (
    MEASUREMENT_CRS,
    SQ_FT_PER_SQ_MI,
    measure_ward_coverage,
    symmetric_difference_sq_mi,
)

MILE = 5280.0  # feet


def _wards() -> gpd.GeoDataFrame:
    # Ward 20 is a 2 x 1 mile rectangle; ward 5 sits east of it.
    return gpd.GeoDataFrame(
        {"ward": ["20", "5"]},
        geometry=[box(0, 0, 2 * MILE, MILE), box(2 * MILE, 0, 3 * MILE, MILE)],
        crs=MEASUREMENT_CRS,
    )


def _areas() -> gpd.GeoDataFrame:
    # A: the west half of the ward exactly. B: 1x1 straddling the ward's east edge, half in.
    # C: a 1x1 square that also extends north, only a quarter of it inside the ward.
    # D: entirely outside.
    return gpd.GeoDataFrame(
        {"area_numbe": ["1", "2", "3", "4"], "community": ["A", "B", "C", "D"]},
        geometry=[
            box(0, 0, MILE, MILE),
            box(1.5 * MILE, 0, 2.5 * MILE, MILE),
            box(MILE, 0.5 * MILE, 1.5 * MILE, 1.5 * MILE),
            box(0, 2 * MILE, MILE, 3 * MILE),
        ],
        crs=MEASUREMENT_CRS,
    )


def test_shares_are_exact_for_known_rectangles() -> None:
    coverage = measure_ward_coverage(
        _wards(), _areas(), ward_id="20", id_field="area_numbe", name_field="community"
    )
    rows = coverage.rows.set_index("polygon_name")

    assert coverage.ward_sq_mi == pytest.approx(2.0)
    assert list(rows.index) == ["A", "B", "C"]  # D does not intersect; largest share first
    assert rows.loc["A", "intersection_sq_mi"] == pytest.approx(1.0)
    assert rows.loc["A", "share_of_ward_pct"] == pytest.approx(50.0)
    assert rows.loc["A", "share_of_polygon_in_ward_pct"] == pytest.approx(100.0)
    assert rows.loc["B", "share_of_ward_pct"] == pytest.approx(25.0)
    assert rows.loc["B", "share_of_polygon_in_ward_pct"] == pytest.approx(50.0)
    assert rows.loc["C", "intersection_sq_mi"] == pytest.approx(0.25)
    assert rows.loc["C", "share_of_polygon_in_ward_pct"] == pytest.approx(50.0)


def test_partitioning_layer_sums_to_one_hundred_percent() -> None:
    """A layer that tiles the ward accounts for exactly all of it — the coverage proof."""
    tiles = gpd.GeoDataFrame(
        {"area_numbe": ["1", "2", "3"], "community": ["L", "M", "R"]},
        geometry=[
            box(-MILE, -MILE, 0.5 * MILE, 2 * MILE),
            box(0.5 * MILE, -MILE, 1.2 * MILE, 2 * MILE),
            box(1.2 * MILE, -MILE, 5 * MILE, 2 * MILE),
        ],
        crs=MEASUREMENT_CRS,
    )
    coverage = measure_ward_coverage(
        _wards(), tiles, ward_id="20", id_field="area_numbe", name_field="community"
    )
    assert coverage.total_share_pct == pytest.approx(100.0)


def test_ward_ids_compare_without_leading_zeros() -> None:
    wards = _wards()
    wards["ward"] = ["020", "005"]
    coverage = measure_ward_coverage(
        wards, _areas(), ward_id="20", id_field="area_numbe", name_field="community"
    )
    assert coverage.ward_sq_mi == pytest.approx(2.0)


def test_symmetric_difference_of_identical_polygons_is_zero() -> None:
    a = box(0, 0, MILE, MILE)
    assert symmetric_difference_sq_mi(a, box(0, 0, MILE, MILE)) == 0.0
    assert symmetric_difference_sq_mi(a, box(0, 0, 2 * MILE, MILE)) == pytest.approx(
        MILE * MILE / SQ_FT_PER_SQ_MI
    )
