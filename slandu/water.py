"""JRC Global Surface Water: transition classes per zone, and one water body.

`new permanent water` lumps together fish/shrimp ponds, reservoirs, channel
migration and tidal effects. Never label it before looking at imagery.
v1.5 mixes Landsat Collection 1 (to 2021) and Collection 2 (2022-2024); the
provider notes a residual co-registration offset that can reach one 30 m pixel.
"""
from __future__ import annotations

import csv
import glob
import os

import numpy as np
import rasterio

from .geo_util import (JRC_TILE_RE, expected_zone_area_ha, rasterize_zones,
                       row_area_m2, sum_area_ha, window_for_bbox, zones_bbox)
from .zonal import JRC_TRANSITIONS


def _tiles(data_dir: str, product: str) -> list[str]:
    paths = sorted(glob.glob(os.path.join(data_dir, f"{product}_*.tif")))
    if not paths:
        raise SystemExit(f"missing JRC {product} raster(s) in {data_dir}")
    versions = {os.path.basename(p).split("_v")[-1] for p in paths if "_v" in os.path.basename(p)}
    if len(versions) > 1:
        raise SystemExit(f"mixed JRC versions for {product}: {sorted(versions)} - keep one")
    return paths


def transitions_by_zone(zones, data_dir: str, out_dir: str) -> None:
    """Sum every transitions tile that intersects the zones; report coverage."""
    bbox = zones_bbox(zones)
    acc = np.zeros((len(zones), 11))
    covered = np.zeros(len(zones))
    used = 0
    for path in _tiles(data_dir, "transitions"):
        with rasterio.open(path) as ds:
            win = window_for_bbox(ds, bbox)
            if win is None:
                continue
            tr = ds.window_transform(win)
            trans = ds.read(1, window=win)
        used += 1
        ha = row_area_m2(tr.f, -tr.e, trans.shape[0], tr.a) / 10_000.0
        zone_ids = rasterize_zones([(g, i + 1) for i, (_, g) in enumerate(zones)],
                                   tr, trans.shape)
        valid = (trans >= 1) & (trans <= 10)
        for r in np.nonzero((zone_ids > 0).any(axis=1))[0]:
            zr = zone_ids[r]
            for i in range(len(zones)):
                m = zr == i + 1
                if not m.any():
                    continue
                covered[i] += m.sum() * ha[r]
                tv = trans[r][m & valid[r]]
                if tv.size:
                    acc[i] += np.bincount(tv, minlength=11) * ha[r]
    if not used:
        raise SystemExit("no JRC tile intersects the AOI")

    coverage = 100 * covered / np.maximum(expected_zone_area_ha(zones, bbox), 1e-9)
    os.makedirs(out_dir, exist_ok=True)
    p = os.path.join(out_dir, "water_transitions.csv")
    with open(p, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["zone", "tiles_coverage_pct", "transition_code", "transition_label", "area_ha"])
        for i, (name, _) in enumerate(zones):
            for c in range(1, 11):
                if acc[i][c] > 0:
                    w.writerow([name, f"{coverage[i]:.1f}", c, JRC_TRANSITIONS[c], f"{acc[i][c]:.1f}"])
            print(f"{name}: new permanent {acc[i][2]:,.0f} ha / lost permanent {acc[i][3]:,.0f} ha"
                  + ("" if coverage[i] >= 99 else f"  WARNING coverage {coverage[i]:.1f}%"))
    print("wrote", p)


def water_body(seed_lon: float, seed_lat: float, bbox, data_dir: str, out_dir: str,
               label: str = "waterbody", seed_threshold: int = 5) -> None:
    """Isolate the connected water area around a seed point.

    The result is "the connected region with occurrence >= seed_threshold that
    contains the seed" - which may include channels or rivers joined to the lake,
    and may split a lake in two at the threshold. It is not a validated lake
    boundary and it is not the provider's Maximum Water Extent layer.
    """
    from scipy import ndimage

    def read_box(product):
        hits = []
        for path in _tiles(data_dir, product):
            with rasterio.open(path) as ds:
                win = window_for_bbox(ds, bbox)
                if win is not None:
                    hits.append((path, win))
        if len(hits) != 1:
            raise SystemExit(f"water_body needs the bbox inside exactly one {product} tile "
                             f"(found {len(hits)}); shrink the bbox or move it")
        path, win = hits[0]
        with rasterio.open(path) as ds:
            return ds.read(1, window=win), ds.window_transform(win)

    occ, tr = read_box("occurrence")
    trans, _ = read_box("transitions")
    trans = trans[:occ.shape[0], :occ.shape[1]]

    ha = row_area_m2(tr.f, -tr.e, occ.shape[0], tr.a) / 10_000.0
    valid = occ <= 100
    labels, _ = ndimage.label(valid & (occ >= seed_threshold))
    inv = ~tr
    col, row = inv * (seed_lon, seed_lat)
    seed = int(labels[int(row), int(col)])
    body = labels == seed if seed else np.zeros_like(labels, bool)
    if not seed:
        print("WARNING: the seed point is not on water at this threshold - check the coordinates")

    os.makedirs(out_dir, exist_ok=True)
    p = os.path.join(out_dir, f"{label}_water_summary.csv")
    with open(p, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["metric", "area_ha", "note"])
        w.writerow(["seed", f"{seed_lon},{seed_lat}",
                    f"connected component of occurrence>={seed_threshold}% containing the seed"])
        for thr in (5, 25, 50, 75, 90, 95):
            w.writerow([f"connected_area_occurrence>={thr}%",
                        f"{sum_area_ha(body & (occ >= thr), ha):.1f}",
                        "occurrence = share of valid observations with water, whole record"])
        for c in range(1, 11):
            v = sum_area_ha(body & (trans == c), ha)
            if v > 0:
                w.writerow([f"transition:{JRC_TRANSITIONS[c]}", f"{v:.1f}", ""])
        w.writerow(["note", "", "occurrence mixes intra-annual, inter-annual and long-term change; "
                              "a gap between low and high thresholds is not by itself evidence of "
                              "seasonality rather than shrinkage - use a time series for that"])
    print("wrote", p)
    print(f"  connected area >=5%: {sum_area_ha(body & (occ >= 5), ha):,.0f} ha / "
          f">=95%: {sum_area_ha(body & (occ >= 95), ha):,.0f} ha")
