"""Hansen Global Forest Change: annual tree-cover loss by zone, plus hotspots.

Terminology matters here. Hansen `loss` is a stand-replacement disturbance of
vegetation taller than 5 m; it is NOT netted against regrowth. This module
therefore never reports "remaining forest" - it reports
"area with tree cover > threshold in 2000 where no loss has been detected".
"""
from __future__ import annotations

import csv
import glob
import os

import numpy as np
import rasterio

from .geo_util import (bbox_of, rasterize_zones, row_area_m2, sum_area_ha,
                       union_geom, window_for_bbox)

FIRST_YEAR = 2001  # lossyear == 1


def _find(data_dir: str, layer: str) -> str:
    hits = sorted(glob.glob(os.path.join(data_dir, f"Hansen_*_{layer}_*.tif")))
    if not hits:
        raise SystemExit(f"missing Hansen {layer} raster in {data_dir} "
                         f"(run `slandu fetch --download`)")
    return hits[0]


def analyse(zones, data_dir: str, out_dir: str, threshold: int = 30,
            last_year: int | None = None, hotspot_from: int | None = None) -> dict:
    """Annual loss per zone + summary CSV. `zones` is [(name, geometry), ...]."""
    p_loss = _find(data_dir, "lossyear")
    p_tc = _find(data_dir, "treecover2000")
    p_dm = _find(data_dir, "datamask")

    all_geom = union_geom([g for _, g in zones])
    with rasterio.open(p_loss) as dl, rasterio.open(p_tc) as dt, rasterio.open(p_dm) as dd:
        win = window_for_bbox(dl, bbox_of(all_geom))
        if win is None:
            raise SystemExit("AOI does not overlap the Hansen tile")
        tr = dl.window_transform(win)
        loss = dl.read(1, window=win)
        tc = dt.read(1, window=win)
        dm = dd.read(1, window=win)

    if last_year is None:
        last_year = FIRST_YEAR + int(loss.max()) - 1
    n_years = last_year - FIRST_YEAR + 1
    years = list(range(FIRST_YEAR, last_year + 1))

    ha = row_area_m2(tr.f, -tr.e, loss.shape[0], tr.a) / 10_000.0
    zone_ids = rasterize_zones([(g, i + 1) for i, (_, g) in enumerate(zones)],
                               tr, loss.shape)
    canopy = (dm == 1) & (tc > threshold)

    names = [n for n, _ in zones]
    annual = np.zeros((len(zones), n_years))
    base = np.zeros(len(zones))
    for r in range(loss.shape[0]):
        rowsel = canopy[r]
        if not rowsel.any():
            continue
        z = zone_ids[r][rowsel]
        ly = loss[r][rowsel]
        for i in range(len(zones)):
            m = z == i + 1
            if not m.any():
                continue
            base[i] += m.sum() * ha[r]
            lz = ly[m]
            hit = lz > 0
            if hit.any():
                annual[i] += np.bincount(lz[hit] - 1, minlength=n_years)[:n_years] * ha[r]

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
        w.writerow(["zone", f"canopy_gt{threshold}pct_2000_ha",
                    f"loss_{FIRST_YEAR}_{last_year}_ha", "loss_pct_of_2000",
                    "no_loss_detected_ha", "annual_mean_first10_ha",
                    "annual_mean_last10_ha"])
        for i, name in enumerate(names):
            tot = annual[i].sum()
            w.writerow([name, f"{base[i]:.1f}", f"{tot:.1f}",
                        f"{100 * tot / base[i]:.2f}" if base[i] else "",
                        f"{base[i] - tot:.1f}",
                        f"{annual[i][:10].mean():.1f}", f"{annual[i][-10:].mean():.1f}"])
    print("wrote", p, "(note: 'no_loss_detected' is NOT remaining forest)")

    # sensitivity to the canopy threshold - report it, do not hide it
    p = os.path.join(out_dir, "forest_loss_threshold_sensitivity.csv")
    aoi_mask = zone_ids > 0
    with open(p, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["threshold_pct", "canopy_2000_ha", "loss_ha", "loss_pct"])
        for thr in (10, threshold, 50):
            cm = aoi_mask & (dm == 1) & (tc > thr)
            b = sum_area_ha(cm, ha)
            l = sum_area_ha(cm & (loss > 0), ha)
            w.writerow([thr, f"{b:.1f}", f"{l:.1f}",
                        f"{100 * l / b:.2f}" if b else ""])
    print("wrote", p)

    if hotspot_from is not None:
        _hotspots(loss, canopy, zone_ids, names, tr, ha, out_dir, hotspot_from)

    return {"years": years, "annual": annual, "canopy_2000": base, "names": names}


def _hotspots(loss, canopy, zone_ids, names, tr, ha, out_dir, from_year, top=40):
    """1 km cells with the most loss since `from_year`."""
    idx = from_year - FIRST_YEAR + 1
    recent = (canopy & (loss >= idx)).astype(np.float32)
    k = max(1, int(round(1000 / (tr.a * 111_320))))
    hh, ww = (recent.shape[0] // k) * k, (recent.shape[1] // k) * k
    if hh == 0 or ww == 0:
        return
    cells = recent[:hh, :ww].reshape(hh // k, k, ww // k, k).sum(axis=(1, 3))
    cell_ha = cells * float(ha.mean())
    order = np.argsort(cell_ha, axis=None)[::-1][:top]
    p = os.path.join(out_dir, f"forest_loss_hotspots_1km_from{from_year}.csv")
    with open(p, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["rank", "lat", "lon", "loss_ha_per_km2", "zone"])
        for rank, flat in enumerate(order, 1):
            cy, cx = np.unravel_index(flat, cell_ha.shape)
            py, px = cy * k + k // 2, cx * k + k // 2
            lon, lat = tr * (px + 0.5, py + 0.5)
            zid = int(zone_ids[py, px])
            w.writerow([rank, f"{lat:.4f}", f"{lon:.4f}", f"{cell_ha[cy, cx]:.1f}",
                        names[zid - 1] if zid else ""])
    print("wrote", p)
