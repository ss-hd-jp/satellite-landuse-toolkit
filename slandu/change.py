"""Two-date bare-ground change from Sentinel-2, and NDVI trajectories.

Rules baked in, because ignoring them produces confident nonsense:

1. Every input is reprojected onto ONE reference grid (the later scene's red
   band, coarsened by `stride`). Two scenes from different MGRS tiles or with a
   sub-pixel shift are therefore compared at the same ground location.
2. Cloud/water masking with the SCL band, keeping classes 4/5/7 only
   (vegetated / not vegetated / unclassified). Class 6 (water) is dropped:
   scenes from older processing baselines have sea-surface NIR around 0.06,
   so leaving water in turns the ocean into "bare ground". Note that class 7
   means *unclassified*, not "clear".
3. A COMMON valid mask: only pixels valid on BOTH dates enter any number.
4. Reflectance scaling is decided per scene from the STAC sidecar
   (`<tag>_stac.json`) and then sanity-checked against water pixels, because
   Earth Search items can carry contradictory offset metadata.
"""
from __future__ import annotations

import csv
import json
import os

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import Affine
from rasterio.warp import reproject, transform as warp_transform, transform_geom

from .geo_util import rasterize_zones

SCL_KEEP = (4, 5, 7)


# ---------------------------------------------------------------- reference grid

def reference_grid(ref_path: str, bbox, stride: int):
    """(crs, transform, shape) of the analysis grid: the reference band's grid
    over bbox, coarsened by `stride` (stride=2 on 10 m bands -> 20 m cells).

    Coarsening samples every stride-th pixel when reprojecting with nearest
    neighbour; it does not aggregate all 10 m pixels. Areas are cell counts x
    cell area on this grid.
    """
    with rasterio.open(ref_path) as ds:
        xs, ys = warp_transform("EPSG:4326", ds.crs, [bbox[0], bbox[2]], [bbox[3], bbox[1]])
        r0, c0 = ds.index(xs[0], ys[0])
        r1, c1 = ds.index(xs[1], ys[1])
        r0, r1 = sorted((int(r0), int(r1)))
        c0, c1 = sorted((int(c0), int(c1)))
        r0, c0 = max(r0, 0), max(c0, 0)
        r1, c1 = min(r1, ds.height), min(c1, ds.width)
        if r1 - r0 < stride or c1 - c0 < stride:
            raise SystemExit("bbox does not overlap the reference scene (or is smaller than one cell)")
        base = ds.transform * Affine.translation(c0, r0)
        tr = base * Affine.scale(stride, stride)
        shape = ((r1 - r0) // stride, (c1 - c0) // stride)
        return ds.crs, tr, shape


def read_on_grid(path: str, crs, tr, shape, resampling=Resampling.nearest,
                 dtype=np.float32):
    """Read any raster onto the reference grid (reprojecting if needed)."""
    dst = np.zeros(shape, dtype=dtype)
    with rasterio.open(path) as ds:
        reproject(rasterio.band(ds, 1), dst, dst_transform=tr, dst_crs=crs,
                  resampling=resampling, dst_nodata=0)
    return dst


# ---------------------------------------------------------------- reflectance scaling

def _sidecar(s2_dir: str, tag: str) -> dict | None:
    p = os.path.join(s2_dir, f"{tag}_stac.json")
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None


def scaling_for(s2_dir: str, tag: str, mode: str = "auto") -> tuple[float, float, str]:
    """(scale, offset, reason) to turn DN into reflectance: refl = DN*scale + offset.

    mode: 'auto' | 'applied' (offset already in the pixels) | 'apply' (subtract 0.1)
    """
    if mode == "applied":
        return 1e-4, 0.0, "forced: offset already applied"
    if mode == "apply":
        return 1e-4, -0.1, "forced: apply BOA offset -0.1"
    item = _sidecar(s2_dir, tag)
    if item is None:
        return 1e-4, 0.0, "no sidecar; assumed offset already applied (verify with water check)"
    p = item.get("properties", {})
    flag = p.get("earthsearch:boa_offset_applied")
    baseline = str(p.get("s2:processing_baseline", "") or "")
    rb = (item.get("assets", {}).get("red", {}).get("raster:bands") or [{}])[0]
    scale = float(rb.get("scale", 1e-4) or 1e-4)
    meta_off = float(rb.get("offset", 0.0) or 0.0)
    if flag is True:
        # Earth Search COGs with this flag have the offset already subtracted
        # from the pixel values; the raster:bands offset (-0.1) is stale there.
        # Verified empirically on a baseline 05.11 scene: water NIR DN ~146.
        return scale, 0.0, f"boa_offset_applied=true (baseline {baseline}); raster:bands offset {meta_off} ignored"
    if flag is False and baseline and baseline >= "04.00":
        return scale, (meta_off if meta_off else -0.1), f"boa_offset_applied=false, baseline {baseline}: applying offset"
    return scale, 0.0, f"pre-offset baseline {baseline or '?'}: no offset"


def water_sanity(nir_refl: np.ndarray, scl: np.ndarray) -> tuple[float | None, str]:
    """Median NIR reflectance over SCL water pixels; flags likely mis-scaling."""
    w = (scl == 6) & np.isfinite(nir_refl)
    if w.sum() < 50:
        return None, "too few water pixels to check scaling"
    med = float(np.median(nir_refl[w]))
    if med < -0.01:
        return med, f"NEGATIVE water reflectance ({med:.3f}): offset applied twice - use --offset applied"
    if med > 0.15:
        return med, f"water NIR {med:.3f} is implausibly bright: offset probably NOT applied - use --offset apply"
    return med, f"water NIR median {med:.3f}: scaling looks plausible"


def ndvi(nir, red):
    return (nir - red) / np.maximum(nir + red, 1e-6)


# ---------------------------------------------------------------- two-date change

def _load_scene(s2_dir, tag, crs, tr, shape, offset_mode):
    scale, off, reason = scaling_for(s2_dir, tag, offset_mode)
    red = read_on_grid(os.path.join(s2_dir, f"{tag}_B04.tif"), crs, tr, shape)
    nir = read_on_grid(os.path.join(s2_dir, f"{tag}_B08.tif"), crs, tr, shape)
    scl = read_on_grid(os.path.join(s2_dir, f"{tag}_SCL.tif"), crs, tr, shape, dtype=np.uint8)
    nodata = (red == 0) | (nir == 0)
    red = red * scale + off
    nir = nir * scale + off
    med, verdict = water_sanity(nir, scl)
    return {"red": red, "nir": nir, "scl": scl, "nodata": nodata,
            "scaling": reason, "water_check": verdict, "water_nir": med}


def bare_change(s2_dir: str, tag_a: str, tag_b: str, bbox, out_dir: str,
                zones=None, stride: int = 2, ndvi_max: float = 0.25,
                nir_min: float = 0.05, red_max: float = 0.35,
                min_cluster_ha: float = 20.0, label: str = "aoi",
                offset_mode: str = "auto") -> dict:
    """Bare ground on date A vs date B, per zone, on a common valid mask.

    Expects <tag>_B04.tif, <tag>_B08.tif, <tag>_SCL.tif (and optionally
    <tag>_stac.json) in `s2_dir`. `zones` = [(name, geometry EPSG:4326)];
    when None the bbox is used as the single zone.
    """
    from scipy import ndimage

    crs, tr, shape = reference_grid(os.path.join(s2_dir, f"{tag_b}_B04.tif"), bbox, stride)
    A = _load_scene(s2_dir, tag_a, crs, tr, shape, offset_mode)
    B = _load_scene(s2_dir, tag_b, crs, tr, shape, offset_mode)
    for tag, S in ((tag_a, A), (tag_b, B)):
        print(f"  {tag}: {S['scaling']}")
        print(f"  {tag}: {S['water_check']}")
        if S["water_check"].startswith("NEGATIVE") or "NOT applied" in S["water_check"]:
            raise SystemExit(f"{tag}: refusing to continue - {S['water_check']}")

    if zones is None:
        zones = [(label, {"type": "Polygon", "coordinates": [[
            [bbox[0], bbox[1]], [bbox[2], bbox[1]], [bbox[2], bbox[3]],
            [bbox[0], bbox[3]], [bbox[0], bbox[1]]]]})]
    zone_ids = rasterize_zones(
        [(transform_geom("EPSG:4326", crs, g), i + 1) for i, (_, g) in enumerate(zones)],
        tr, shape)
    aoi = zone_ids > 0

    valid = aoi & ~A["nodata"] & ~B["nodata"] & np.isin(A["scl"], SCL_KEEP) & np.isin(B["scl"], SCL_KEEP)
    bare_a = valid & (ndvi(A["nir"], A["red"]) < ndvi_max) & (A["nir"] > nir_min) & (A["red"] < red_max)
    bare_b = valid & (ndvi(B["nir"], B["red"]) < ndvi_max) & (B["nir"] > nir_min) & (B["red"] < red_max)
    new_bare = bare_b & ~bare_a
    no_longer_bare = bare_a & ~bare_b

    cell_ha = abs(tr.a * tr.e) / 10_000.0
    os.makedirs(out_dir, exist_ok=True)
    rows = []
    for i, (name, _) in enumerate(zones):
        z = zone_ids == i + 1
        n_aoi = int(z.sum())
        v = valid & z
        rows.append({
            "zone": name,
            "zone_area_ha": round(n_aoi * cell_ha, 1),
            "common_valid_pct": round(100 * v.sum() / max(n_aoi, 1), 1),
            f"bare_{tag_a}_ha": round(float((bare_a & z).sum() * cell_ha), 1),
            f"bare_{tag_b}_ha": round(float((bare_b & z).sum() * cell_ha), 1),
            "new_bare_ha": round(float((new_bare & z).sum() * cell_ha), 1),
            "no_longer_bare_ha": round(float((no_longer_bare & z).sum() * cell_ha), 1),
        })
        print("  " + "  ".join(f"{k}={v}" for k, v in rows[-1].items()))

    p = os.path.join(out_dir, f"{label}_bare_change_summary.csv")
    with open(p, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print("wrote", p)

    lab, n = ndimage.label(new_bare, structure=np.ones((3, 3)))
    clusters = []
    if n:
        sizes = ndimage.sum(new_bare, lab, index=np.arange(1, n + 1))
        for i in np.argsort(sizes)[::-1]:
            area = float(sizes[i] * cell_ha)
            if area < min_cluster_ha:
                break
            cy, cx = ndimage.center_of_mass(new_bare, lab, i + 1)
            x, y = tr * (cx + 0.5, cy + 0.5)
            lon, lat = warp_transform(crs, "EPSG:4326", [x], [y])
            zid = int(zone_ids[int(cy), int(cx)])
            clusters.append([len(clusters) + 1, f"{lat[0]:.4f}", f"{lon[0]:.4f}",
                             f"{area:.1f}", zones[zid - 1][0] if zid else ""])
        p = os.path.join(out_dir, f"{label}_new_bare_clusters.csv")
        with open(p, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["rank", "lat", "lon", "new_bare_ha", "zone"])
            w.writerows(clusters)
        print(f"wrote {p} ({len(clusters)} clusters >= {min_cluster_ha} ha)")
        print("  ALWAYS eyeball the top clusters in true colour before interpreting")

    manifest = {
        "inputs": {t: [f"{t}_B04.tif", f"{t}_B08.tif", f"{t}_SCL.tif"] for t in (tag_a, tag_b)},
        "reference_grid": {"crs": crs.to_string(), "transform": list(tr)[:6], "shape": list(shape),
                           "cell_m": abs(tr.a), "stride": stride},
        "scaling": {tag_a: A["scaling"], tag_b: B["scaling"]},
        "water_check": {tag_a: A["water_check"], tag_b: B["water_check"]},
        "thresholds": {"ndvi_max": ndvi_max, "nir_min": nir_min, "red_max": red_max,
                       "min_cluster_ha": min_cluster_ha, "scl_keep": list(SCL_KEEP)},
        "bbox": list(bbox), "zones": [z for z, _ in zones],
        "note": "single-date NDVI tracks crop phenology; confirm with a second season "
                "before calling any of this permanent change",
    }
    with open(os.path.join(out_dir, f"{label}_change_manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    return {"rows": rows, "clusters": clusters, "manifest": manifest}


# ---------------------------------------------------------------- NDVI trajectory

def ndvi_trajectory(s2_dir: str, tags_dates, bbox, out_csv: str,
                    masks: dict[str, np.ndarray] | None = None,
                    stride: int = 2, offset_mode: str = "auto") -> dict:
    """Median NDVI per date for one or more pixel groups on the reference grid
    of the first scene. `masks` maps group name -> boolean array on that grid.
    Always include an undisturbed control group.
    """
    crs, tr, shape = reference_grid(os.path.join(s2_dir, f"{tags_dates[0][0]}_B04.tif"),
                                    bbox, stride)
    groups = masks or {"aoi": np.ones(shape, bool)}
    series: dict[str, list] = {k: [] for k in groups}
    rows = []
    for tag, date in tags_dates:
        S = _load_scene(s2_dir, tag, crs, tr, shape, offset_mode)
        v = ndvi(S["nir"], S["red"])
        valid = np.isin(S["scl"], SCL_KEEP) & ~S["nodata"]
        for name, m in groups.items():
            sel = m & valid
            cnt = int(sel.sum())
            med = float(np.median(v[sel])) if cnt > 100 else float("nan")
            series[name].append(med)
            rows.append({"date": date, "group": name, "valid_px": cnt,
                         "valid_pct": round(100 * cnt / max(int(m.sum()), 1), 1),
                         "ndvi_median": "" if np.isnan(med) else round(med, 3),
                         "scaling": S["scaling"]})
        print(f"{date}: " + "  ".join(
            f"{k}={series[k][-1]:.3f}" if not np.isnan(series[k][-1]) else f"{k}=NA"
            for k in groups))
    os.makedirs(os.path.dirname(os.path.abspath(out_csv)), exist_ok=True)
    with open(out_csv, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["date", "group", "valid_px", "valid_pct",
                                          "ndvi_median", "scaling"])
        w.writeheader()
        w.writerows(rows)
    print("wrote", out_csv)
    return series
