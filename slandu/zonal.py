"""Zonal statistics for categorical rasters on a lat/lon grid."""
from __future__ import annotations

import csv
import glob
import os

import numpy as np
import rasterio

from .geo_util import (bbox_of, iter_strips, rasterize_zones, row_area_m2,
                       window_for_bbox)

WORLDCOVER_CLASSES = {
    10: "tree cover", 20: "shrubland", 30: "grassland", 40: "cropland",
    50: "built-up", 60: "bare / sparse vegetation", 70: "snow and ice",
    80: "permanent water bodies", 90: "herbaceous wetland", 95: "mangroves",
    100: "moss and lichen",
}

JRC_TRANSITIONS = {
    1: "permanent", 2: "new permanent", 3: "lost permanent", 4: "seasonal",
    5: "new seasonal", 6: "lost seasonal", 7: "seasonal to permanent",
    8: "permanent to seasonal", 9: "ephemeral permanent", 10: "ephemeral seasonal",
}

ESRI_CLASSES = {
    1: "water", 2: "trees", 4: "flooded vegetation", 5: "crops", 7: "built area",
    8: "bare ground", 9: "snow/ice", 10: "clouds", 11: "rangeland",
}

CLASS_SETS = {"worldcover": WORLDCOVER_CLASSES, "jrc_transitions": JRC_TRANSITIONS,
              "esri": ESRI_CLASSES, "raw": {}}


def find_rasters(data_dir: str, pattern: str) -> list[str]:
    """Glob helper so callers pass a directory instead of tile paths."""
    return sorted(glob.glob(os.path.join(data_dir, pattern)))


def dedupe_tiles(paths: list[str]) -> list[str]:
    """Drop rasters whose bounds duplicate an earlier one (e.g. two versions of
    the same tile matched by a loose glob) - otherwise areas are double counted."""
    seen, out = set(), []
    for p in paths:
        with rasterio.open(p) as ds:
            key = (tuple(round(v, 6) for v in ds.bounds), ds.crs.to_string())
        if key in seen:
            print(f"  WARNING: {os.path.basename(p)} duplicates an earlier tile's extent - skipped")
            continue
        seen.add(key)
        out.append(p)
    return out


def class_areas(geom: dict, raster_paths: list[str], strip_rows: int = 1024,
                exclude: tuple[int, ...] = (0, 255)) -> dict[int, float]:
    """Area [ha] per class value inside `geom`, summed over (possibly several) tiles."""
    acc: dict[int, float] = {}
    for path in raster_paths:
        with rasterio.open(path) as ds:
            if ds.crs is None or not ds.crs.is_geographic:
                raise SystemExit(f"{path}: zonal statistics need a lat/lon (geographic) raster")
            win = window_for_bbox(ds, bbox_of(geom))
            if win is None:
                continue
            for sub in iter_strips(win, strip_rows):
                data = ds.read(1, window=sub)
                tr = ds.window_transform(sub)
                mask = rasterize_zones([(geom, 1)], tr, data.shape).astype(bool)
                if not mask.any():
                    continue
                ha = row_area_m2(tr.f, -tr.e, data.shape[0], tr.a) / 10_000.0
                for r in np.nonzero(mask.any(axis=1))[0]:
                    counts = np.bincount(data[r][mask[r]], minlength=256)
                    for c in np.nonzero(counts)[0]:
                        if c in exclude:
                            continue
                        acc[int(c)] = acc.get(int(c), 0.0) + counts[c] * ha[r]
    return acc


def write_zone_table(zones, raster_paths, out_csv: str, class_set: str = "raw",
                     strip_rows: int = 1024) -> None:
    """Write zone x class areas to CSV. `zones` is [(name, geometry), ...]."""
    labels = CLASS_SETS[class_set]
    raster_paths = dedupe_tiles(raster_paths)
    rows = []
    for name, geom in zones:
        acc = class_areas(geom, raster_paths, strip_rows)
        total = sum(acc.values())
        for code, area in sorted(acc.items()):
            rows.append({"zone": name, "class_code": code,
                         "class_label": labels.get(code, str(code)),
                         "area_ha": round(area, 1),
                         "share_pct": round(100 * area / total, 3) if total else ""})
        rows.append({"zone": name, "class_code": "TOTAL", "class_label": "total",
                     "area_ha": round(total, 1), "share_pct": 100.0 if total else ""})
        if not total:
            print(f"{name}: no valid pixels inside the supplied rasters")
        else:
            print(f"{name}: total {total:,.0f} ha across {len(acc)} classes")

    os.makedirs(os.path.dirname(os.path.abspath(out_csv)), exist_ok=True)
    with open(out_csv, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["zone", "class_code", "class_label",
                                          "area_ha", "share_pct"])
        w.writeheader()
        w.writerows(rows)
    print("wrote", out_csv)
