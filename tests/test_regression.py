"""Regression tests on synthetic rasters.

Each test reproduces a defect found in the two pre-publication reviews and
asserts the fix. Where a defect was "the test could not tell", the test now
includes a negative control: the implementation is deliberately broken and
the test must fail.

Run:  python -m pytest tests -q        (or)   python tests/test_regression.py
"""
from __future__ import annotations

import csv
import json
import os
import sys
import tempfile

import numpy as np
import rasterio
from rasterio.transform import Affine, from_origin
from rasterio.warp import transform_bounds

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from slandu import change, fetch, forest, geo_util, water, zonal  # noqa: E402

PX = 1 / 4000  # Hansen-like 30 m lat/lon grid
UTM = "EPSG:32651"


def write_tif(path, arr, transform, crs="EPSG:4326", nodata=None):
    with rasterio.open(path, "w", driver="GTiff", height=arr.shape[0], width=arr.shape[1],
                       count=1, dtype=arr.dtype, crs=crs, transform=transform,
                       nodata=nodata) as ds:
        ds.write(arr, 1)


def read_csv(path):
    return list(csv.DictReader(open(path, encoding="utf-8-sig")))


def hansen_tile(d, lat_top, lon_left, size, loss_val=0, tc_val=80,
                version="GFC-2025-v1.13", name=None, loss_arr=None):
    tr = from_origin(lon_left, lat_top, PX, PX)
    name = name or geo_util.hansen_tile_name(lat_top, lon_left)
    loss = loss_arr if loss_arr is not None else np.full((size, size), loss_val, np.uint8)
    write_tif(os.path.join(d, f"Hansen_{version}_lossyear_{name}.tif"), loss, tr)
    write_tif(os.path.join(d, f"Hansen_{version}_treecover2000_{name}.tif"),
              np.full((size, size), tc_val, np.uint8), tr)
    write_tif(os.path.join(d, f"Hansen_{version}_datamask_{name}.tif"),
              np.full((size, size), 1, np.uint8), tr)
    return tr


# ================================================================ tile naming

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


def test_expected_area_strips_match_single_pass():
    aoi = geo_util.bbox_geom((120.001, 9.90, 120.30, 9.99))
    a = geo_util.expected_zone_area_ha([("z", aoi)], geo_util.bbox_of(aoi), strip_rows=7)
    b = geo_util.expected_zone_area_ha([("z", aoi)], geo_util.bbox_of(aoi), strip_rows=10_000)
    assert abs(a[0] - b[0]) < 1e-6


# ================================================================ zonal

def test_empty_zone_reports_zero_not_one():
    with tempfile.TemporaryDirectory() as d:
        tr = from_origin(10, 1, 0.001, 0.001)
        write_tif(os.path.join(d, "wc.tif"), np.zeros((50, 50), np.uint8), tr)
        out = os.path.join(d, "z.csv")
        zonal.write_zone_table([("z", geo_util.bbox_geom((10.01, 0.96, 10.02, 0.98)))],
                               [os.path.join(d, "wc.tif")], out)
        tot = [r for r in read_csv(out) if r["class_code"] == "TOTAL"][0]
        assert float(tot["area_ha"]) == 0.0 and tot["share_pct"] == ""


# ================================================================ forest

def test_forest_sums_across_two_tiles_and_keeps_full_year_axis():
    with tempfile.TemporaryDirectory() as d:
        hansen_tile(d, 10, 129.95, 200, loss_val=5, name="10N_129E")   # 129.95..130.00
        hansen_tile(d, 10, 130.00, 200, loss_val=5, name="10N_130E")   # 130.00..130.05
        aoi = geo_util.bbox_geom((129.98, 9.98, 130.02, 9.99))
        res = forest.analyse([("seam", aoi)], d, os.path.join(d, "out"), hotspot_from=2001)
        assert res["years"][0] == 2001 and res["years"][-1] == 2025
        annual = res["annual"][0]
        assert annual[4] > 0 and annual[5:].sum() == 0
        expected = geo_util.expected_zone_area_ha([("seam", aoi)], geo_util.bbox_of(aoi))[0]
        assert abs(res["canopy_2000"][0] - expected) / expected < 0.03
        assert res["coverage_pct"][0] > 97
        rows = read_csv(os.path.join(d, "out", "forest_loss_hotspots_from2001.csv"))
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


def test_hotspots_rank_by_loss_not_cell_area():
    with tempfile.TemporaryDirectory() as d:
        size = 120
        loss = np.zeros((size, size), np.uint8)
        loss[0:36, 0:36] = 20          # first cell (generated first): fully lost
        loss[40:41, 40:41] = 20        # a second cell with one lost pixel
        loss[80:116, 80:116] = 20      # third cell: fully lost
        hansen_tile(d, 10, 120, size, loss_arr=loss)
        aoi = geo_util.bbox_geom((120.0, 10 - size * PX, 120 + size * PX, 10.0))
        forest.analyse([("a", aoi)], d, os.path.join(d, "out"), hotspot_from=2016)
        rows = read_csv(os.path.join(d, "out", "forest_loss_hotspots_from2016.csv"))
        losses = [float(r["loss_ha"]) for r in rows]
        assert losses == sorted(losses, reverse=True) and losses[0] > 50 and losses[-1] < 1


# ================================================================ water

def test_water_sums_two_tiles():
    with tempfile.TemporaryDirectory() as d:
        for lon, name in ((129.95, "129E_10N"), (130.00, "130E_10N")):
            write_tif(os.path.join(d, f"transitions_{name}_v1_5_2024.tif"),
                      np.full((200, 200), 2, np.uint8), from_origin(lon, 10, PX, PX))
        aoi = geo_util.bbox_geom((129.98, 9.98, 130.02, 9.99))
        water.transitions_by_zone([("seam", aoi)], d, os.path.join(d, "out"))
        rows = [r for r in read_csv(os.path.join(d, "out", "water_transitions.csv"))
                if r["transition_code"] == "2"]
        expected = geo_util.expected_zone_area_ha([("seam", aoi)], geo_util.bbox_of(aoi))[0]
        assert abs(float(rows[0]["area_ha"]) - expected) / expected < 0.03


def test_water_zone_without_water_is_still_listed():
    with tempfile.TemporaryDirectory() as d:
        write_tif(os.path.join(d, "transitions_120E_10N_v1_5_2024.tif"),
                  np.zeros((100, 100), np.uint8), from_origin(120, 10, PX, PX))
        aoi = geo_util.bbox_geom((120.005, 9.99, 120.02, 9.995))
        water.transitions_by_zone([("dry", aoi)], d, os.path.join(d, "out"))
        rows = read_csv(os.path.join(d, "out", "water_transitions.csv"))
        assert {r["zone"] for r in rows} == {"dry"}
        assert all(float(r["area_ha"]) == 0.0 for r in rows)
        assert float(rows[0]["tiles_coverage_pct"]) > 97


# ================================================================ fetch

def test_download_failure_is_not_cached():
    import subprocess as sp
    calls = []

    def fake_run(cmd, check=False):
        calls.append(cmd)
        dst = cmd[cmd.index("-o") + 1]
        open(dst, "wb").write(b"x" * 2055)             # truncated body
        return sp.CompletedProcess(cmd, 28)               # curl timeout
    with tempfile.TemporaryDirectory() as d:
        orig = fetch.subprocess.run
        fetch.subprocess.run = fake_run
        try:
            f1 = fetch.download([("a.tif", "http://x/a")], d)
            f2 = fetch.download([("a.tif", "http://x/a")], d)
        finally:
            fetch.subprocess.run = orig
        assert f1 == ["a.tif"] and f2 == ["a.tif"] and len(calls) == 2
        assert not os.path.exists(os.path.join(d, "a.tif"))
        assert not os.path.exists(os.path.join(d, "a.tif.part"))


def test_download_scene_refuses_silent_tag_reuse():
    def fake_download(pairs, out_dir, **kw):
        for name, _ in pairs:
            open(os.path.join(out_dir, name), "wb").write(b"y" * 5000)
        return []
    with tempfile.TemporaryDirectory() as d:
        orig = fetch.download
        fetch.download = fake_download
        try:
            s1 = {"item": {"id": "old-scene"}, "assets": {"B04": "u", "B08": "u", "SCL": "u"}}
            s2 = {"item": {"id": "new-scene"}, "assets": {"B04": "u", "B08": "u", "SCL": "u"}}
            assert fetch.download_scene(s1, d, "early") == []
            assert json.load(open(os.path.join(d, "early_stac.json")))["id"] == "old-scene"
            try:
                fetch.download_scene(s2, d, "early")
            except SystemExit as e:
                assert "old-scene" in str(e)
            else:
                raise AssertionError("tag reuse with a different scene was not refused")
            assert json.load(open(os.path.join(d, "early_stac.json")))["id"] == "old-scene"
            fetch.download_scene(s2, d, "early", overwrite=True)
            assert json.load(open(os.path.join(d, "early_stac.json")))["id"] == "new-scene"
        finally:
            fetch.download = orig


# ================================================================ change

def render_scene(d, tag, origin, n, bare_rects, water_rect=None, dn_offset=0,
                 flag=None, baseline="05.11", meta_offset=None, sidecar=True, crs=UTM):
    """Render a scene from ground-truth rectangles given in map (UTM) coordinates.

    origin: (x_left, y_top). Pixel values are sampled at pixel centres, so two
    scenes with different origins hold the SAME ground pattern at DIFFERENT
    array indices. dn_offset=1000 encodes the +1000 DN convention.
    """
    UTM_ = crs
    x0, y0 = origin
    tr = from_origin(x0, y0, 10, 10)
    xs = x0 + (np.arange(n) + 0.5) * 10
    ys = y0 - (np.arange(n) + 0.5) * 10
    X, Y = np.meshgrid(xs, ys)
    red = np.full((n, n), 0.05, np.float32)
    nir = np.full((n, n), 0.30, np.float32)
    scl = np.full((n, n), 4, np.uint8)
    for (xa, xb, ya, yb) in bare_rects:
        m = (X >= xa) & (X < xb) & (Y >= ya) & (Y < yb)
        red[m], nir[m] = 0.20, 0.22
    if water_rect:
        xa, xb, ya, yb = water_rect
        m = (X >= xa) & (X < xb) & (Y >= ya) & (Y < yb)
        scl[m] = 6
        nir[m] = 0.02
    write_tif(os.path.join(d, f"{tag}_B04.tif"),
              np.round(red * 10000 + dn_offset).astype(np.uint16), tr, UTM_)
    write_tif(os.path.join(d, f"{tag}_B08.tif"),
              np.round(nir * 10000 + dn_offset).astype(np.uint16), tr, UTM_)
    write_tif(os.path.join(d, f"{tag}_SCL.tif"), scl[::2, ::2], tr * Affine.scale(2, 2), UTM_)
    if sidecar:
        props = {"s2:processing_baseline": baseline}
        if flag is not None:
            props["earthsearch:boa_offset_applied"] = flag
        off = meta_offset if meta_offset is not None else (-0.1 if dn_offset else 0)
        item = {"id": f"{tag}-scene", "properties": props,
                "assets": {"red": {"raster:bands": [{"scale": 0.0001, "offset": off}]},
                           "nir": {"raster:bands": [{"scale": 0.0001, "offset": off}]}}}
        json.dump(item, open(os.path.join(d, f"{tag}_stac.json"), "w"))
    return tr


def _ll_bbox(x0, x1, y0, y1, crs=UTM):
    return transform_bounds(crs, "EPSG:4326", x0, y0, x1, y1)


BARE = [(500400, 500600, 59400, 59600)]            # 200 m x 200 m block on the ground
WATER = (500000, 501200, 59900, 60000)             # a 100 m strip of water at the top


def _run(d, **kw):
    inner = _ll_bbox(500050, 501150, 58850, 59950)  # inside both scenes, off the water strip
    return change.bare_change(d, "a", "b", inner, os.path.join(d, "out"), stride=1,
                              min_cluster_ha=0.5, **kw)


def test_change_coregisters_shifted_grids_zero_change_with_negative_control():
    with tempfile.TemporaryDirectory() as d:
        render_scene(d, "a", (500000, 60000), 120, BARE, WATER, flag=False, baseline="02.13")
        render_scene(d, "b", (500030, 59970), 120, BARE, WATER, flag=True)   # grid shifted 3 px
        row = _run(d)["rows"][0]
        assert row["new_bare_ha"] == 0.0 and row["no_longer_bare_ha"] == 0.0, row
        assert row["in_both_scenes_pct"] > 99 and row["common_valid_pct"] > 90

        # negative control: a reader that ignores georeferencing must NOT pass
        def naive(path, crs, tr, shape, resampling=None, dtype=np.float32):
            with rasterio.open(path) as ds:
                a = ds.read(1, out_shape=shape).astype(dtype)
            return a
        orig = change.read_on_grid
        change.read_on_grid = naive
        try:
            bad = _run(d)["rows"][0]
        finally:
            change.read_on_grid = orig
        assert bad["new_bare_ha"] > 0.5 and bad["no_longer_bare_ha"] > 0.5, bad


def test_change_detects_a_real_change_of_known_size():
    with tempfile.TemporaryDirectory() as d:
        render_scene(d, "a", (500000, 60000), 120, BARE, WATER, flag=False, baseline="02.13")
        extra = BARE + [(500800, 500900, 59000, 59100)]   # +100 m x 100 m = 1.0 ha
        render_scene(d, "b", (500030, 59970), 120, extra, WATER, flag=True)
        row = _run(d)["rows"][0]
        assert abs(row["new_bare_ha"] - 1.0) < 0.05 and row["no_longer_bare_ha"] == 0.0, row


def test_change_normalises_mixed_offset_encodings():
    with tempfile.TemporaryDirectory() as d:
        # A: pixels already corrected, stale raster:bands offset, flag true
        render_scene(d, "a", (500000, 60000), 120, BARE, WATER, dn_offset=0, flag=True,
                     meta_offset=-0.1)
        # B: raw +1000 DN, flag false, baseline 05 -> offset must be applied
        render_scene(d, "b", (500000, 60000), 120, BARE, WATER, dn_offset=1000, flag=False)
        row = _run(d)["rows"][0]
        assert row["new_bare_ha"] == 0.0 and row["no_longer_bare_ha"] == 0.0, row


def test_change_stops_when_correction_state_is_unknown_or_ambiguous():
    with tempfile.TemporaryDirectory() as d:
        render_scene(d, "a", (500000, 60000), 120, BARE, WATER, flag=True)
        render_scene(d, "b", (500000, 60000), 120, BARE, WATER, dn_offset=1000, sidecar=False)
        try:
            _run(d)
        except SystemExit as e:
            assert "cannot be determined" in str(e)
        else:
            raise AssertionError("missing sidecar did not stop the run")
        # ambiguous: no flag, baseline 05, raster:bands offset -0.1
        render_scene(d, "b", (500000, 60000), 120, BARE, WATER, dn_offset=1000, flag=None,
                     baseline="05.11", meta_offset=-0.1)
        try:
            _run(d)
        except SystemExit as e:
            assert "cannot be determined" in str(e)
        else:
            raise AssertionError("ambiguous metadata did not stop the run")
        # per-scene override resolves it
        row = _run(d, offset_mode_b="apply")["rows"][0]
        assert row["new_bare_ha"] == 0.0, row


def test_change_water_check_stops_on_implausible_scaling():
    with tempfile.TemporaryDirectory() as d:
        render_scene(d, "a", (500000, 60000), 120, BARE, WATER, flag=True)
        render_scene(d, "b", (500000, 60000), 120, BARE, WATER, flag=True)
        try:
            _run(d, offset_mode_b="apply")      # subtract 0.1 from already-corrected pixels
        except SystemExit as e:
            assert "verification" in str(e)
        else:
            raise AssertionError("implausible water reflectance did not stop the run")


def test_change_window_covers_the_whole_aoi():
    """At 37 N, 200 km off the central meridian, a lat/lon rectangle is rotated
    ~1.2 degrees in UTM; a window built from two bbox corners clips ~4 % of it."""
    crs = "EPSG:32654"
    x0, y0 = 300000, 4100000
    with tempfile.TemporaryDirectory() as d:
        n = 400                                              # 4 km scene
        water = (x0, x0 + 4000, y0 - 100, y0)
        render_scene(d, "a", (x0, y0), n, [], water, flag=False, baseline="02.13", crs=crs)
        render_scene(d, "b", (x0, y0), n, [], water, flag=True, crs=crs)
        bbox = _ll_bbox(x0 + 400, x0 + 3600, y0 - 3600, y0 - 400, crs)
        res = change.bare_change(d, "a", "b", bbox, os.path.join(d, "out"), stride=1)
        row = res["rows"][0]
        expected = geo_util.expected_zone_area_ha([("z", geo_util.bbox_geom(bbox))], bbox)[0]
        assert abs(row["zone_area_ha"] - expected) / expected < 0.01, (row, expected)
        assert row["in_both_scenes_pct"] > 99.5

        # negative control: a two-corner window must fail this test
        def two_corner(src, dst, *b, **kw):
            xs, ys = change.warp_transform(src, dst, [b[0], b[2]], [b[3], b[1]])
            return min(xs), min(ys), max(xs), max(ys)
        orig = change.transform_bounds
        change.transform_bounds = two_corner
        try:
            bad = change.bare_change(d, "a", "b", bbox, os.path.join(d, "out"), stride=1)["rows"][0]
        finally:
            change.transform_bounds = orig
        assert bad["zone_area_ha"] < 0.98 * expected, (bad, expected)


def test_change_reports_partial_scene_coverage_and_refuses_when_too_small():
    with tempfile.TemporaryDirectory() as d:
        render_scene(d, "a", (500000, 60000), 100, [], WATER, flag=False, baseline="02.13")
        render_scene(d, "b", (500000, 60000), 100, [], WATER, flag=True)
        big = _ll_bbox(500000, 501500, 58500, 60000)          # 1.5 km box, scene is 1 km
        try:
            change.bare_change(d, "a", "b", big, os.path.join(d, "out"), stride=1,
                               min_coverage_pct=50)
        except SystemExit as e:
            assert "footprint" in str(e)
        else:
            raise AssertionError("AOI mostly outside the scenes was not refused")
        res = change.bare_change(d, "a", "b", big, os.path.join(d, "out"), stride=1,
                                 min_coverage_pct=30)
        row = res["rows"][0]
        assert 40 < row["in_both_scenes_pct"] < 50 and row["common_valid_pct"] < row["in_both_scenes_pct"] + 0.1


def test_change_uses_polygon_not_bbox():
    with tempfile.TemporaryDirectory() as d:
        n = 100
        render_scene(d, "a", (500000, 60000), n, [], None, flag=False, baseline="02.13")
        render_scene(d, "b", (500000, 60000), n, [(500000, 501000, 59000, 60000)], None, flag=True)
        bbox = _ll_bbox(500000, 501000, 59000, 60000)
        tri = {"type": "Polygon", "coordinates": [[[bbox[0], bbox[1]], [bbox[2], bbox[1]],
                                                    [bbox[0], bbox[3]], [bbox[0], bbox[1]]]]}
        res = change.bare_change(d, "a", "b", bbox, os.path.join(d, "out"), stride=1,
                                 zones=[("tri", tri)], offset_mode="applied")
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
