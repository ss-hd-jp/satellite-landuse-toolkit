"""JRC Global Surface Water: transition classes per zone, and one water body.

`new permanent water` lumps together fish/shrimp ponds, reservoirs, channel
migration and tidal effects. Never label it before looking at imagery.
"""
from __future__ import annotations

import csv
import glob
import os

import numpy as np
import rasterio

from .geo_util import (bbox_of, rasterize_zones, row_area_m2, sum_area_ha,
                       union_geom, window_for_bbox)
from .zonal import JRC_TRANSITIONS


def _find(data_dir: str, product: str) -> str:
    hits = sorted(glob.glob(os.path.join(data_dir, f"{product}_*.tif")))
    if not hits:
        raise SystemExit(f"missing JRC {product} raster in {data_dir}")
    return hits[0]


def transitions_by_zone(zones, data_dir: str, out_dir: str) -> None:
    path = _find(data_dir, "transitions")
    all_geom = union_geom([g for _, g in zones])
    with rasterio.open(path) as ds:
        win = window_for_bbox(ds, bbox_of(all_geom))
        if win is None:
            raise SystemExit("AOI does not overlap the JRC tile")
        tr = ds.window_transform(win)
        trans = ds.read(1, window=win)

    ha = row_area_m2(tr.f, -tr.e, trans.shape[0], tr.a) / 10_000.0
    zone_ids = rasterize_zones([(g, i + 1) for i, (_, g) in enumerate(zones)],
                               tr, trans.shape)
    acc = np.zeros((len(zones), 11))
    sel_any = (zone_ids > 0) & (trans >= 1) & (trans <= 10)
    for r in np.nonzero(sel_any.any(axis=1))[0]:
        s = sel_any[r]
        tv, zv = trans[r][s], zone_ids[r][s]
        for i in range(len(zones)):
            m = zv == i + 1
            if m.any():
                acc[i] += np.bincount(tv[m], minlength=11) * ha[r]

    os.makedirs(out_dir, exist_ok=True)
    p = os.path.join(out_dir, "water_transitions.csv")
    with open(p, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["zone", "transition_code", "transition_label", "area_ha"])
        for i, (name, _) in enumerate(zones):
            for c in range(1, 11):
                if acc[i][c] > 0:
                    w.writerow([name, c, JRC_TRANSITIONS[c], f"{acc[i][c]:.1f}"])
            print(f"{name}: new permanent {acc[i][2]:,.0f} ha / "
                  f"lost permanent {acc[i][3]:,.0f} ha")
    print("wrote", p)


def water_body(seed_lon: float, seed_lat: float, bbox, data_dir: str, out_dir: str,
               label: str = "waterbody", seed_threshold: int = 5) -> None:
    """Isolate one lake/reservoir by flood-filling from a seed point.

    A plain bounding box mixes in rivers, estuaries and paddies; the connected
    component keeps only the water body you meant.
    """
    from scipy import ndimage

    occ_path = _find(data_dir, "occurrence")
    tra_path = _find(data_dir, "transitions")
    with rasterio.open(occ_path) as ds:
        win = window_for_bbox(ds, bbox)
        tr = ds.window_transform(win)
        occ = ds.read(1, window=win)
    with rasterio.open(tra_path) as ds:
        win2 = window_for_bbox(ds, bbox)
        trans = ds.read(1, window=win2)
    trans = trans[:occ.shape[0], :occ.shape[1]]

    ha = row_area_m2(tr.f, -tr.e, occ.shape[0], tr.a) / 10_000.0
    valid = occ <= 100
    labels, _ = ndimage.label(valid & (occ >= seed_threshold))
    inv = ~tr
    col, row = inv * (seed_lon, seed_lat)
    seed = int(labels[int(row), int(col)])
    body = labels == seed if seed else np.zeros_like(labels, bool)
    if not seed:
        print("WARNING: the seed point is not on water - check the coordinates")

    os.makedirs(out_dir, exist_ok=True)
    p = os.path.join(out_dir, f"{label}_water_summary.csv")
    with open(p, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["metric", "area_ha", "note"])
        w.writerow(["seed", f"{seed_lon},{seed_lat}", "connected-component seed"])
        for thr in (5, 25, 50, 75, 90, 95):
            w.writerow([f"occurrence>={thr}%", f"{sum_area_ha(body & (occ >= thr), ha):.1f}",
                        "water occurrence over the full record"])
        for c in range(1, 11):
            v = sum_area_ha(body & (trans == c), ha)
            if v > 0:
                w.writerow([f"transition:{JRC_TRANSITIONS[c]}", f"{v:.1f}", ""])
    print("wrote", p)
    print(f"  max extent (>=5%) {sum_area_ha(body & (occ >= 5), ha):,.0f} ha / "
          f"near-permanent (>=95%) {sum_area_ha(body & (occ >= 95), ha):,.0f} ha")
