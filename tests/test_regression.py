"""Regression tests on synthetic rasters. Each test reproduces a defect found in
the pre-publication review and asserts the fix.

Run:  python -m pytest tests -q        (or)   python tests/test_regression.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile

import numpy as np
import rasterio
from rasterio.transform import from_origin

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from slandu import change, forest, geo_util, water, zonal  # noqa: E402

PX = 1 / 4000  # Hansen-like 30 m lat/lon grid


def write_tif(path, arr, transform, crs="EPSG:4326", nodata=None):
    with rasterio.open(path, "w", driver="GTiff", height=arr.shape[0], width=arr.shape[1],
                       count=1, dtype=arr.dtype, crs=crs, transform=transform,
                       nodata=nodata) as ds:
        ds.write(arr, 1)


def hansen_tile(d, lat_top, lon_left, size, loss_val=0, tc_val=80, version="GFC-2025-v1.13",
                name=None):
    tr = from_origin(lon_left, lat_top, PX, PX)
    name = name or geo_util.hansen_tile_name(lat_top, lon_left)
    write_tif(os.path.join(d, f"Hansen_{version}_lossyear_{name}.tif"),
              np.full((size, size), loss_val, np.uint8), tr)
    write_tif(os.path.join(d, f"Hansen_{version}_treecover2000_{name}.tif"),
              np.full((size, size), tc_val, np.uint8), tr)
    write_tif(os.path.join(d, f"Hansen_{version}_datamask_{name}.tif"),
              np.full((size, size), 1, np.uint8), tr)
    return tr


# ---------------------------------------------------------------- tile naming

def test_jrc_tile_names_are_not_zero_padded():
    assert geo_util.jrc_tile_name(10, 0) == "0E_10N"
    assert geo_util.jrc_tile_name(10, 10) == "10E_10N"
    assert geo_util.jrc_tile_name(10, 120) == "120E_10N"
    assert geo_util.jrc_tile_name(0, 120) == "120E_0N"
    assert geo_util.jrc_tile_name(-10, -10) == "10W_10S"


def test_hansen_tile_names_are_zero_padded():
    assert geo_util.hansen_tile_name(10, 120) == "10N_120E"
    assert geo_util.hansen_tile_name(0, 0) == "00N_000E"
    assert geo_util.hansen_tile_name(-10, -10) == "10S_010W"


def test_esri_tiles_span_all_bands_and_zones():
    tiles = geo_util.esri_tiles((138.0, 31.0, 139.0, 41.0))
    assert {"54R", "54S", "54T"} <= set(tiles)
    assert geo_util.esri_tile(119.4, -5.14) == "50M"


def test_zone_raster_holds_more_than_255_zones():
    tr = from_origin(0, 1, 0.0005, 0.0005)
    geoms = [(geo_util.bbox_geom((i * 0.003, 0.0, i * 0.003 + 0.002, 1.0)), i + 1)
             for i in range(300)]
    ids = geo_util.rasterize_zones(geoms, tr, (100, 1800))
    assert ids.dtype == np.uint16 and ids.max() == 300


# ---------------------------------------------------------------- zonal

def test_empty_zone_reports_zero_not_one():
    with tempfile.TemporaryDirectory() as d:
        tr = from_origin(10, 1, 0.001, 0.001)
        write_tif(os.path.join(d, "wc.tif"), np.zeros((50, 50), np.uint8), tr)  # all nodata(0)
        out = os.path.join(d, "z.csv")
        zonal.write_zone_table([("z", geo_util.bbox_geom((10.01, 0.96, 10.02, 0.98)))],
                               [os.path.join(d, "wc.tif")], out)
        rows = list(__import__("csv").DictReader(open(out, encoding="utf-8-sig")))
        tot = [r for r in rows if r["class_code"] == "TOTAL"][0]
        assert float(tot["area_ha"]) == 0.0 and tot["share_pct"] == ""


# ---------------------------------------------------------------- forest

def test_forest_sums_across_two_tiles_and_keeps_full_year_axis():
    with tempfile.TemporaryDirectory() as d:
        # two adjacent 10-degree tiles at the equator, tiny (200 px) for speed
        hansen_tile(d, 10, 129.95, 200, loss_val=5, name="10N_129E")   # 129.95..130.00
        hansen_tile(d, 10, 130.00, 200, loss_val=5, name="10N_130E")   # 130.00..130.05
        # AOI straddling the 130E seam: 129.99 .. 130.01
        aoi = geo_util.bbox_geom((129.98, 9.98, 130.02, 9.99))
        res = forest.analyse([("seam", aoi)], d, os.path.join(d, "out"), hotspot_from=2001)
        years = res["years"]
        assert years[0] == 2001 and years[-1] == 2025          # from version, not from data
        annual = res["annual"][0]
        assert annual[4] > 0 and annual[5:].sum() == 0          # all loss in 2005, zeros kept
        expected = geo_util.expected_zone_area_ha([("seam", aoi)], geo_util.bbox_of(aoi))[0]
        assert abs(res["canopy_2000"][0] - expected) / expected < 0.03   # both tiles counted
        assert res["coverage_pct"][0] > 97
        # hotspot cells must not include loss outside the AOI
        rows = list(__import__("csv").DictReader(
            open(os.path.join(d, "out", "forest_loss_hotspots_from2001.csv"), encoding="utf-8-sig")))
        total_hot = sum(float(r["loss_ha"]) for r in rows)
        assert abs(total_hot - annual.sum()) / annual.sum() < 0.01


def test_forest_with_no_loss_has_clean_output():
    with tempfile.TemporaryDirectory() as d:
        hansen_tile(d, 10, 120, 100, loss_val=0)
        aoi = geo_util.bbox_geom((120.005, 9.99, 120.02, 9.995))
        res = forest.analyse([("quiet", aoi)], d, os.path.join(d, "out"))
        assert len(res["years"]) == 25 and res["annual"].sum() == 0
        s = open(os.path.join(d, "out", "forest_loss_summary.csv"), encoding="utf-8-sig").read()
        assert "nan" not in s and "loss_2001_2025_ha" in s


# ---------------------------------------------------------------- water

def test_water_sums_two_tiles():
    with tempfile.TemporaryDirectory() as d:
        for lon, name in ((129.95, "129E_10N"), (130.00, "130E_10N")):
            tr = from_origin(lon, 10, PX, PX)
            write_tif(os.path.join(d, f"transitions_{name}_v1_5_2024.tif"),
                      np.full((200, 200), 2, np.uint8), tr)   # new permanent everywhere
        aoi = geo_util.bbox_geom((129.98, 9.98, 130.02, 9.99))
        water.transitions_by_zone([("seam", aoi)], d, os.path.join(d, "out"))
        rows = list(__import__("csv").DictReader(
            open(os.path.join(d, "out", "water_transitions.csv"), encoding="utf-8-sig")))
        got = float(rows[0]["area_ha"])
        expected = geo_util.expected_zone_area_ha([("seam", aoi)], geo_util.bbox_of(aoi))[0]
        assert abs(got - expected) / expected < 0.03


# ---------------------------------------------------------------- change

def s2_scene(d, tag, tr, red, nir, scl, shift_px=0, dn_offset=0, flag=None, baseline="05.11"):
    """Write B04/B08/SCL (+sidecar). shift_px moves the grid origin; dn_offset
    encodes the same reflectance with a +1000 DN offset (baseline >= 04.00 style)."""
    tr2 = tr * __import__("rasterio").transform.Affine.translation(shift_px, 0)
    crs = "EPSG:32651"
    write_tif(os.path.join(d, f"{tag}_B04.tif"), (red * 10000 + dn_offset).astype(np.uint16), tr2, crs)
    write_tif(os.path.join(d, f"{tag}_B08.tif"), (nir * 10000 + dn_offset).astype(np.uint16), tr2, crs)
    scl_tr = tr2 * __import__("rasterio").transform.Affine.scale(2, 2)
    write_tif(os.path.join(d, f"{tag}_SCL.tif"), scl[::2, ::2].astype(np.uint8), scl_tr, crs)
    item = {"properties": {"earthsearch:boa_offset_applied": flag,
                           "s2:processing_baseline": baseline},
            "assets": {"red": {"raster:bands": [{"scale": 0.0001,
                                                  "offset": -0.1 if dn_offset else 0}]}}}
    json.dump(item, open(os.path.join(d, f"{tag}_stac.json"), "w"))


def _bbox_of_utm(tr, shape):
    from rasterio.warp import transform_bounds
    left, top = tr.c, tr.f
    right, bottom = left + tr.a * shape[1], top + tr.e * shape[0]
    return transform_bounds("EPSG:32651", "EPSG:4326", left, bottom, right, top)


def test_change_coregisters_shifted_grid_and_ignores_stale_offset_metadata():
    with tempfile.TemporaryDirectory() as d:
        n = 120
        tr = from_origin(500000, 60000, 10, 10)
        red = np.full((n, n), 0.05, np.float32)
        nir = np.full((n, n), 0.30, np.float32)          # vegetated everywhere
        red[40:60, 40:60], nir[40:60, 40:60] = 0.20, 0.22  # one bare block, both dates
        scl = np.full((n, n), 4, np.uint8)
        scl[:10, :] = 6                                   # a strip of water for the sanity check
        nir[:10, :] = 0.02
        # date A: pre-offset era, plain DN; date B: same ground, grid shifted 1 px,
        # encoded with +1000 DN offset already applied (flag True)
        s2_scene(d, "a", tr, red, nir, scl, shift_px=0, dn_offset=0, flag=False, baseline="02.13")
        s2_scene(d, "b", tr, red, nir, scl, shift_px=1, dn_offset=0, flag=True, baseline="05.11")
        bbox = _bbox_of_utm(tr, (n, n))
        bbox = (bbox[0] + 0.0005, bbox[1] + 0.0005, bbox[2] - 0.0005, bbox[3] - 0.0005)
        res = change.bare_change(d, "a", "b", bbox, os.path.join(d, "out"), stride=1,
                                 min_cluster_ha=0.5)
        row = res["rows"][0]
        assert row["new_bare_ha"] <= 0.3, row       # only the 1-px seam can differ
        assert row["no_longer_bare_ha"] <= 0.3, row
        assert row["common_valid_pct"] > 80


def test_change_refuses_double_offset():
    with tempfile.TemporaryDirectory() as d:
        n = 60
        tr = from_origin(500000, 60000, 10, 10)
        red = np.full((n, n), 0.05, np.float32); nir = np.full((n, n), 0.30, np.float32)
        scl = np.full((n, n), 4, np.uint8); scl[:10, :] = 6; nir[:10, :] = 0.02
        s2_scene(d, "a", tr, red, nir, scl, flag=True)
        s2_scene(d, "b", tr, red, nir, scl, flag=True)
        bbox = _bbox_of_utm(tr, (n, n))
        try:
            change.bare_change(d, "a", "b", bbox, os.path.join(d, "out"), stride=1,
                               offset_mode="apply")
        except SystemExit as e:
            assert "NEGATIVE" in str(e)
        else:
            raise AssertionError("double offset was not detected")


def test_change_uses_polygon_not_bbox():
    with tempfile.TemporaryDirectory() as d:
        n = 100
        tr = from_origin(500000, 60000, 10, 10)
        red = np.full((n, n), 0.05, np.float32); nir = np.full((n, n), 0.30, np.float32)
        scl = np.full((n, n), 4, np.uint8)
        red_b, nir_b = red.copy(), nir.copy()
        red_b[:, :], nir_b[:, :] = 0.20, 0.22              # date B bare everywhere
        s2_scene(d, "a", tr, red, nir, scl, flag=False, baseline="02.13")
        s2_scene(d, "b", tr, red_b, nir_b, scl, flag=False, baseline="02.13")
        bbox = _bbox_of_utm(tr, (n, n))
        # triangle covering half the bbox
        tri = {"type": "Polygon", "coordinates": [[[bbox[0], bbox[1]], [bbox[2], bbox[1]],
                                                    [bbox[0], bbox[3]], [bbox[0], bbox[1]]]]}
        res = change.bare_change(d, "a", "b", bbox, os.path.join(d, "out"), stride=1,
                                 zones=[("tri", tri)])
        row = res["rows"][0]
        full = n * n * 100 / 10_000
        assert 0.4 * full < row["new_bare_ha"] < 0.6 * full, row


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("PASS", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, "->", repr(e))
    sys.exit(1 if fails else 0)
