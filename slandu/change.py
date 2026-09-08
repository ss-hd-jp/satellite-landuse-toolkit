"""Two-date bare-ground change from Sentinel-2, and NDVI trajectories.

Two rules are baked in because ignoring them produces confident nonsense:

1. Cloud/water masking with the SCL band, keeping only classes 4/5/7
   (vegetated / not vegetated / unclassified). Class 6 (water) is dropped:
   scenes from older processing baselines have sea-surface NIR around 0.06,
   so leaving water in turns the ocean into "bare ground".
2. A COMMON valid mask. Every comparison uses only pixels that are valid on
   BOTH dates, so a difference in cloud cover cannot masquerade as change.
"""
from __future__ import annotations

import csv
import os

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.warp import transform as warp_transform
from rasterio.windows import Window

SCL_KEEP = (4, 5, 7)


def utm_window(ds, bbox) -> Window:
    xs, ys = warp_transform("EPSG:4326", ds.crs, [bbox[0], bbox[2]], [bbox[3], bbox[1]])
    r0, c0 = ds.index(xs[0], ys[0])
    r1, c1 = ds.index(xs[1], ys[1])
    r0, r1 = sorted((int(r0), int(r1)))
    c0, c1 = sorted((int(c0), int(c1)))
    return Window(c0, r0, max(1, c1 - c0), max(1, r1 - r0))


def _band(path, win, stride, shape=None):
    with rasterio.open(path) as ds:
        a = ds.read(1, window=win)
    a = a[::stride, ::stride].astype(np.float32) / 10000.0
    return a if shape is None else a[:shape[0], :shape[1]]


def _scl_ok(path, bbox, shape):
    """SCL is 20 m while the bands are 10 m, so derive its window from the AOI
    itself rather than halving the band window (which drifts by a pixel)."""
    with rasterio.open(path) as ds:
        a = ds.read(1, window=utm_window(ds, bbox), out_shape=shape,
                    resampling=Resampling.nearest)
    return np.isin(a, SCL_KEEP)


def ndvi(nir, red):
    return (nir - red) / np.maximum(nir + red, 1e-6)


def bare_change(s2_dir: str, tag_a: str, tag_b: str, bbox, out_dir: str,
                stride: int = 2, ndvi_max: float = 0.25, nir_min: float = 0.05,
                red_max: float = 0.35, min_cluster_ha: float = 20.0,
                label: str = "aoi") -> dict:
    """Bare ground on date A vs date B inside bbox, on a common valid mask.

    Expects <tag>_B04.tif, <tag>_B08.tif, <tag>_SCL.tif in `s2_dir`.
    """
    from scipy import ndimage

    ref = os.path.join(s2_dir, f"{tag_b}_B04.tif")
    with rasterio.open(ref) as ds:
        win = utm_window(ds, bbox)
        crs, base_tr = ds.crs, ds.window_transform(win)
    shape = (int(win.height) // stride, int(win.width) // stride)

    a4 = _band(os.path.join(s2_dir, f"{tag_a}_B04.tif"), win, stride, shape)
    a8 = _band(os.path.join(s2_dir, f"{tag_a}_B08.tif"), win, stride, shape)
    b4 = _band(os.path.join(s2_dir, f"{tag_b}_B04.tif"), win, stride, shape)
    b8 = _band(os.path.join(s2_dir, f"{tag_b}_B08.tif"), win, stride, shape)
    ok_a = _scl_ok(os.path.join(s2_dir, f"{tag_a}_SCL.tif"), bbox, shape)
    ok_b = _scl_ok(os.path.join(s2_dir, f"{tag_b}_SCL.tif"), bbox, shape)

    valid = (a8 > 0) & (b8 > 0) & ok_a & ok_b            # <- common valid mask
    bare_a = valid & (ndvi(a8, a4) < ndvi_max) & (a8 > nir_min) & (a4 < red_max)
    bare_b = valid & (ndvi(b8, b4) < ndvi_max) & (b8 > nir_min) & (b4 < red_max)
    new_bare = bare_b & ~bare_a

    px_ha = (10 * stride) ** 2 / 10_000.0
    stats = {
        "aoi_ha": round(valid.size * px_ha, 1),
        "common_valid_pct": round(100 * float(valid.mean()), 1),
        f"bare_{tag_a}_ha": round(float(bare_a.sum() * px_ha), 1),
        f"bare_{tag_b}_ha": round(float(bare_b.sum() * px_ha), 1),
        "new_bare_ha": round(float(new_bare.sum() * px_ha), 1),
        "revegetated_ha": round(float((bare_a & ~bare_b).sum() * px_ha), 1),
    }

    os.makedirs(out_dir, exist_ok=True)
    p = os.path.join(out_dir, f"{label}_bare_change_summary.csv")
    with open(p, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["metric", "value"])
        for k, v in stats.items():
            w.writerow([k, v])
        w.writerow(["note", "single-date NDVI tracks crop phenology; confirm with a "
                            "second season before calling this permanent change"])
    print("wrote", p)
    for k, v in stats.items():
        print(f"  {k:24s} {v}")

    lab, n = ndimage.label(new_bare, structure=np.ones((3, 3)))
    if n:
        sizes = ndimage.sum(new_bare, lab, index=np.arange(1, n + 1))
        order = np.argsort(sizes)[::-1]
        rows = []
        for i in order:
            area = float(sizes[i] * px_ha)
            if area < min_cluster_ha:
                break
            cy, cx = ndimage.center_of_mass(new_bare, lab, i + 1)
            x, y = base_tr * (cx * stride, cy * stride)
            lon, lat = warp_transform(crs, "EPSG:4326", [x], [y])
            rows.append([len(rows) + 1, f"{lat[0]:.4f}", f"{lon[0]:.4f}", f"{area:.1f}"])
        p = os.path.join(out_dir, f"{label}_new_bare_clusters.csv")
        with open(p, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["rank", "lat", "lon", "new_bare_ha"])
            w.writerows(rows)
        print(f"wrote {p} ({len(rows)} clusters >= {min_cluster_ha} ha)")
        print("  ALWAYS eyeball the top clusters in true colour before interpreting")
    return stats


def ndvi_trajectory(s2_dir: str, tags_dates, bbox, out_csv: str,
                    masks: dict[str, np.ndarray] | None = None,
                    stride: int = 2) -> dict:
    """Median NDVI per date for one or more pixel groups.

    `tags_dates` is [(tag, "YYYY-MM-DD"), ...]. `masks` maps a group name to a
    boolean array on the same grid (e.g. pixels cleared in a given year). With
    no masks the whole AOI is used. Include an undisturbed control group: it
    tells you whether a wiggle is real or just atmosphere.
    """
    ref = os.path.join(s2_dir, f"{tags_dates[0][0]}_B04.tif")
    with rasterio.open(ref) as ds:
        win = utm_window(ds, bbox)
    shape = (int(win.height) // stride, int(win.width) // stride)
    groups = masks or {"aoi": np.ones(shape, bool)}

    series: dict[str, list] = {k: [] for k in groups}
    rows = []
    for tag, date in tags_dates:
        r = _band(os.path.join(s2_dir, f"{tag}_B04.tif"), win, stride, shape)
        n = _band(os.path.join(s2_dir, f"{tag}_B08.tif"), win, stride, shape)
        ok = _scl_ok(os.path.join(s2_dir, f"{tag}_SCL.tif"), bbox, shape)
        v = ndvi(n, r)
        valid = ok & (n > 0)
        for name, m in groups.items():
            sel = m & valid
            cnt = int(sel.sum())
            med = float(np.median(v[sel])) if cnt > 100 else float("nan")
            series[name].append(med)
            rows.append({"date": date, "group": name, "valid_px": cnt,
                         "valid_pct": round(100 * cnt / max(int(m.sum()), 1), 1),
                         "ndvi_median": "" if np.isnan(med) else round(med, 3)})
        print(f"{date}: " + "  ".join(
            f"{k}={series[k][-1]:.3f}" if not np.isnan(series[k][-1]) else f"{k}=NA"
            for k in groups))

    os.makedirs(os.path.dirname(os.path.abspath(out_csv)), exist_ok=True)
    with open(out_csv, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["date", "group", "valid_px", "valid_pct",
                                          "ndvi_median"])
        w.writeheader()
        w.writerows(rows)
    print("wrote", out_csv)
    return series
