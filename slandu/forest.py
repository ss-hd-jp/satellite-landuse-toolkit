"""Hansen Global Forest Change: annual tree-cover loss by zone, plus hotspots.

Terminology matters here. Hansen `loss` is a stand-replacement disturbance of
vegetation taller than 5 m; it is NOT netted against regrowth. This module
therefore never reports "remaining forest" - it reports
"area with tree cover > threshold in 2000 where no loss has been detected".

The provider also warns that "definitive area estimation should not be made
using pixel counts from the forest loss layers" and that sensor and algorithm
changes make intervals not strictly comparable. What comes out of here is a
map-pixel tally, not a statistical area estimate.
"""
from __future__ import annotations

import csv
import glob
import os
import re

import numpy as np
import rasterio

from .geo_util import (HANSEN_TILE_RE, HANSEN_VERSION_RE, expected_zone_area_ha,
                       rasterize_zones, row_area_m2, sum_area_ha, window_for_bbox,
                       zones_bbox)

FIRST_YEAR = 2001  # lossyear == 1


def _tiles(data_dir: str) -> tuple[str, int, dict[str, dict[str, str]]]:
    """Group Hansen layers by tile id. Returns (version, end year, {tile: {layer: path}})."""
    paths = glob.glob(os.path.join(data_dir, "Hansen_*_*.tif"))
    if not paths:
        raise SystemExit(f"no Hansen rasters in {data_dir} (run `slandu fetch --download`)")
    versions, tiles = set(), {}
    for p in paths:
        base = os.path.basename(p)
        mv, mt = HANSEN_VERSION_RE.search(base), HANSEN_TILE_RE.search(base)
        if not (mv and mt):
            continue
        versions.add(mv.group(1))
        layer = re.sub(r"^Hansen_" + re.escape(mv.group(1)) + "_", "", base)
        layer = layer[: layer.index("_" + mt.group(1))]
        tiles.setdefault(mt.group(1), {})[layer] = p
    if len(versions) != 1:
        raise SystemExit(f"mixed Hansen versions in {data_dir}: {sorted(versions)} - keep one")
    version = versions.pop()
    end_year = int(HANSEN_VERSION_RE.search(version).group(2))
    for t, layers in tiles.items():
        missing = {"treecover2000", "lossyear", "datamask"} - set(layers)
        if missing:
            raise SystemExit(f"tile {t} is missing layers {sorted(missing)}")
    return version, end_year, tiles


def analyse(zones, data_dir: str, out_dir: str, threshold: int = 30,
            last_year: int | None = None, hotspot_from: int | None = None) -> dict:
    """Annual loss per zone + summary CSV. `zones` is [(name, geometry), ...].

    Every tile that intersects the AOI is read and summed. Coverage of the AOI
    by the available tiles is reported against an independent lat/lon
    rasterization of the zones; a value well below 99 % usually means a tile
    is missing, but a small zone can also lose a fraction of a percent to
    grid/boundary effects, so read the warning together with the tile list.
    """
    version, data_end, tiles = _tiles(data_dir)
    last_year = last_year or data_end
    if last_year > data_end:
        raise SystemExit(f"{version} ends in {data_end}; cannot report to {last_year}")
    years = list(range(FIRST_YEAR, last_year + 1))
    n_years = len(years)
    last_idx = last_year - FIRST_YEAR + 1          # lossyear value of the final year

    names = [n for n, _ in zones]
    bbox = zones_bbox(zones)
    annual = np.zeros((len(zones), n_years))
    base = np.zeros(len(zones))
    covered = np.zeros(len(zones))
    sens = {thr: [0.0, 0.0] for thr in sorted({10, threshold, 50})}
    hotspot_rows: list[list] = []
    used_tiles = []

    for tile, layers in sorted(tiles.items()):
        with rasterio.open(layers["lossyear"]) as dl:
            win = window_for_bbox(dl, bbox)
            if win is None:
                continue
            tr = dl.window_transform(win)
            loss = dl.read(1, window=win)
        with rasterio.open(layers["treecover2000"]) as dt:
            tc = dt.read(1, window=win)
        with rasterio.open(layers["datamask"]) as dd:
            dm = dd.read(1, window=win)
        used_tiles.append(tile)

        ha = row_area_m2(tr.f, -tr.e, loss.shape[0], tr.a) / 10_000.0
        zone_ids = rasterize_zones([(g, i + 1) for i, (_, g) in enumerate(zones)],
                                   tr, loss.shape)
        in_period = (loss >= 1) & (loss <= last_idx)
        canopy = (dm == 1) & (tc > threshold)

        for r in range(loss.shape[0]):
            zr = zone_ids[r]
            if not zr.any():
                continue
            for i in range(len(zones)):
                m = zr == i + 1
                if not m.any():
                    continue
                covered[i] += m.sum() * ha[r]
                cm = m & canopy[r]
                base[i] += cm.sum() * ha[r]
                lz = loss[r][cm & in_period[r]]
                if lz.size:
                    annual[i] += np.bincount(lz - 1, minlength=n_years)[:n_years] * ha[r]

        aoi = zone_ids > 0
        for thr in sens:
            cm = aoi & (dm == 1) & (tc > thr)
            sens[thr][0] += sum_area_ha(cm, ha)
            sens[thr][1] += sum_area_ha(cm & in_period, ha)

        if hotspot_from is not None:
            hotspot_rows += _hotspots(loss, canopy & aoi, zone_ids, names, tr, ha,
                                      hotspot_from, last_idx)

    if not used_tiles:
        raise SystemExit("no Hansen tile intersects the AOI")

    expected = expected_zone_area_ha(zones, bbox)
    coverage = np.where(expected > 0, 100 * covered / np.maximum(expected, 1e-9), 0.0)

    os.makedirs(out_dir, exist_ok=True)
    p = os.path.join(out_dir, "forest_loss_annual.csv")
    with open(p, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["year"] + names)
        for j, y in enumerate(years):
            w.writerow([y] + [f"{annual[i][j]:.1f}" for i in range(len(zones))])
    print("wrote", p)

    p = os.path.join(out_dir, "forest_loss_summary.csv")
    with open(p, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["zone", "tiles_coverage_pct", f"canopy_gt{threshold}pct_2000_ha",
                    f"loss_{FIRST_YEAR}_{last_year}_ha", "loss_pct_of_2000",
                    "no_loss_detected_ha", "annual_mean_first10_ha",
                    "annual_mean_last10_ha", "data_version"])
        for i, name in enumerate(names):
            tot = annual[i].sum()
            w.writerow([name, f"{coverage[i]:.1f}", f"{base[i]:.1f}", f"{tot:.1f}",
                        f"{100 * tot / base[i]:.2f}" if base[i] else "",
                        f"{base[i] - tot:.1f}",
                        f"{annual[i][:10].mean():.1f}" if n_years >= 10 else "",
                        f"{annual[i][-10:].mean():.1f}" if n_years >= 10 else "",
                        version])
            if coverage[i] < 99:
                print(f"  WARNING: {name}: available tiles cover {coverage[i]:.1f}% of the zone "
                      f"(missing tiles, or grid/boundary effects on a very small zone)")
    print("wrote", p, "(note: 'no_loss_detected' is NOT remaining forest)")

    p = os.path.join(out_dir, "forest_loss_threshold_sensitivity.csv")
    with open(p, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["threshold_pct", "canopy_2000_ha", f"loss_{FIRST_YEAR}_{last_year}_ha",
                    "loss_pct"])
        for thr, (b, l) in sens.items():
            w.writerow([thr, f"{b:.1f}", f"{l:.1f}", f"{100 * l / b:.2f}" if b else ""])
    print("wrote", p)

    if hotspot_from is not None:
        hotspot_rows.sort(key=lambda r: -r[2])          # by loss area, unrounded
        p = os.path.join(out_dir, f"forest_loss_hotspots_from{hotspot_from}.csv")
        with open(p, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["rank", "lat", "lon", "loss_ha", "cell_area_ha",
                        "loss_pct_of_cell", "zone_at_centre"])
            for rank, (lat, lon, loss_ha, cell_ha, pct, zone) in enumerate(hotspot_rows[:40], 1):
                w.writerow([rank, f"{lat:.4f}", f"{lon:.4f}", f"{loss_ha:.1f}",
                            f"{cell_ha:.1f}", f"{pct:.1f}", zone])
        print("wrote", p, "(cells are ~1 km squares of pixels on the lat/lon grid; "
                          "area is given per cell, not assumed to be 1 km^2)")

    return {"years": years, "annual": annual, "canopy_2000": base, "names": names,
            "coverage_pct": coverage, "version": version, "tiles": used_tiles}


def _hotspots(loss, canopy_in_aoi, zone_ids, names, tr, ha, from_year, last_idx):
    """Loss since `from_year` aggregated into blocks of k x k pixels (~1 km at the
    equator). Returns unrounded rows [lat, lon, loss_ha, cell_area_ha, loss_pct, zone]."""
    idx = from_year - FIRST_YEAR + 1
    hit = canopy_in_aoi & (loss >= idx) & (loss <= last_idx)
    k = max(1, int(round(1000 / (tr.a * 111_320))))
    rows = []
    h, w = hit.shape
    for r0 in range(0, h, k):
        r1 = min(r0 + k, h)
        row_ha = ha[r0:r1]
        for c0 in range(0, w, k):
            c1 = min(c0 + k, w)
            block = hit[r0:r1, c0:c1]
            if not block.any():
                continue
            loss_ha = float((block.sum(axis=1) * row_ha).sum())
            cell_ha = float(row_ha.sum() * (c1 - c0))
            rc, cc = (r0 + r1) // 2, (c0 + c1) // 2
            lon, lat = tr * (cc + 0.5, rc + 0.5)
            zid = int(zone_ids[rc, cc])
            rows.append([lat, lon, loss_ha, cell_ha, 100 * loss_ha / cell_ha,
                         names[zid - 1] if zid else ""])
    return rows
