"""Two-date bare-ground change from Sentinel-2, and NDVI trajectories.

Rules baked in, because ignoring them produces confident nonsense:

1. One reference grid. The later scene's red band defines the CRS and pixel
   grid; the analysis window is the AOI's *densified* envelope in that CRS,
   snapped outward to whole cells, and NOT clipped to the image. Every input
   (both dates, both SCLs) is reprojected onto that grid, so a sub-pixel shift
   or a different MGRS tile is compared at the same ground location, and cells
   outside a scene's footprint are counted as "not covered" rather than
   silently dropped.
2. Cloud/water masking with the SCL band, keeping classes 4/5/7 only
   (vegetated / not vegetated / unclassified). Class 6 (water) is dropped
   because sea-surface NIR in some scenes is far above clear-water values and
   would be classified as bare. Class 7 means *unclassified*, not "clear".
3. A COMMON valid mask: only cells valid on BOTH dates enter any number, and
   the valid share is reported against the whole AOI, not the covered part.
4. Reflectance scaling is decided per scene from that scene's STAC sidecar and
   must be *confirmed* - by the provider flag, or by the processing baseline
   when no offset can apply, or by an explicit per-scene override. Anything
   ambiguous or unknown stops the run. A water-pixel check then flags
   implausible results; it is a quality trigger, not proof of what happened.
"""
from __future__ import annotations

import csv
import json
import math
import os

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import Affine
from rasterio.warp import reproject, transform as warp_transform, transform_bounds, transform_geom

from .geo_util import rasterize_zones

SCL_KEEP = (4, 5, 7)
WATER_NIR_MIN, WATER_NIR_MAX = -0.01, 0.15   # median over >=50 SCL-water cells


# ---------------------------------------------------------------- reference grid

def reference_grid(ref_path: str, bbox, stride: int):
    """(crs, transform, shape, scene_bounds) of the analysis grid.

    The window is the AOI bbox's envelope in the scene CRS computed with edge
    densification (a lat/lon rectangle is not axis-aligned in UTM), snapped
    outward to the reference pixel grid and padded to a multiple of `stride`.
    It is not clipped to the image: coverage is measured, not assumed.
    """
    with rasterio.open(ref_path) as ds:
        if ds.crs is None:
            raise SystemExit(f"{ref_path}: no CRS")
        left, bottom, right, top = transform_bounds("EPSG:4326", ds.crs, *bbox, densify_pts=41)
        inv = ~ds.transform
        cs, rs = [], []
        for x, y in ((left, top), (right, top), (left, bottom), (right, bottom)):
            c, r = inv * (x, y)
            cs.append(c)
            rs.append(r)
        c0, r0 = math.floor(min(cs)), math.floor(min(rs))
        c1, r1 = max(c0 + 1, math.ceil(max(cs))), max(r0 + 1, math.ceil(max(rs)))
        w = int(math.ceil((c1 - c0) / stride) * stride)
        h = int(math.ceil((r1 - r0) / stride) * stride)
        base = ds.transform * Affine.translation(c0, r0)
        tr = base * Affine.scale(stride, stride)
        shape = (h // stride, w // stride)
        return ds.crs, tr, shape, ds.bounds


def read_on_grid(path: str, crs, tr, shape, resampling=Resampling.nearest, dtype=np.float32):
    """Read any raster onto the reference grid (reprojecting if needed).
    Cells outside the source footprint become 0."""
    dst = np.zeros(shape, dtype=dtype)
    with rasterio.open(path) as ds:
        reproject(rasterio.band(ds, 1), dst, dst_transform=tr, dst_crs=crs,
                  resampling=resampling, dst_nodata=0)
    return dst


def cells_inside_bounds(path: str, crs, tr, shape) -> np.ndarray:
    """Boolean mask of analysis cells whose centres fall inside `path`'s footprint."""
    with rasterio.open(path) as ds:
        b = ds.bounds
        src_crs = ds.crs
    rows, cols = np.indices(shape)
    xs = tr.c + (cols + 0.5) * tr.a + (rows + 0.5) * tr.b
    ys = tr.f + (cols + 0.5) * tr.d + (rows + 0.5) * tr.e
    if src_crs != crs:
        fx, fy = warp_transform(crs, src_crs, xs.ravel().tolist(), ys.ravel().tolist())
        xs, ys = np.array(fx).reshape(shape), np.array(fy).reshape(shape)
    return (xs >= b.left) & (xs <= b.right) & (ys >= b.bottom) & (ys <= b.top)


# ---------------------------------------------------------------- reflectance scaling

def _sidecar(s2_dir: str, tag: str) -> dict | None:
    p = os.path.join(s2_dir, f"{tag}_stac.json")
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None


def _band_meta(item: dict, asset: str) -> dict:
    rb = (item.get("assets", {}).get(asset, {}).get("raster:bands") or [{}])[0]
    return {"scale": float(rb.get("scale", 1e-4) or 1e-4),
            "offset": float(rb.get("offset", 0.0) or 0.0)}


def scaling_for(s2_dir: str, tag: str, mode: str = "auto") -> dict:
    """Decide how DN becomes reflectance for one scene: refl = DN*scale + offset.

    mode: 'auto' | 'applied' (offset already in the pixels) | 'apply' (add the
    negative offset) | 'none' (pre-offset product). Returns a dict with
    scale/offset per band, `status` ('confirmed' | 'ambiguous' | 'unknown'),
    the reason, and what the sidecar said.
    """
    item = _sidecar(s2_dir, tag)
    props = (item or {}).get("properties", {})
    flag = props.get("earthsearch:boa_offset_applied")
    baseline = str(props.get("s2:processing_baseline") or "")
    meta = {b: _band_meta(item, a) for b, a in (("red", "red"), ("nir", "nir"))} if item else \
           {"red": {"scale": 1e-4, "offset": 0.0}, "nir": {"scale": 1e-4, "offset": 0.0}}
    evidence = {"sidecar": bool(item), "item_id": (item or {}).get("id"), "boa_offset_applied": flag,
                "processing_baseline": baseline or None, "raster_bands": meta}

    def out(off_by_band, status, reason):
        return {"scale": {b: meta[b]["scale"] for b in meta},
                "offset": off_by_band, "status": status, "reason": reason,
                "mode": mode, "evidence": evidence}

    zero = {b: 0.0 for b in meta}
    neg = {b: (meta[b]["offset"] if meta[b]["offset"] else -0.1) for b in meta}
    if mode == "applied":
        return out(zero, "confirmed", "forced by user: offset already applied to pixels")
    if mode == "apply":
        return out(neg, "confirmed", "forced by user: applying negative BOA offset")
    if mode == "none":
        return out(zero, "confirmed", "forced by user: pre-offset product, no offset")
    if mode != "auto":
        raise SystemExit(f"unknown offset mode {mode!r}")

    if item is None:
        return out(zero, "unknown", "no STAC sidecar: correction state cannot be determined")
    if flag is True:
        note = "" if all(meta[b]["offset"] == 0 for b in meta) else \
               f" (raster:bands offset {meta['red']['offset']} contradicts the flag; flag used)"
        return out(zero, "confirmed", f"earthsearch:boa_offset_applied=true, baseline {baseline}{note}")
    if flag is False:
        if baseline and baseline >= "04.00":
            return out(neg, "confirmed", f"boa_offset_applied=false, baseline {baseline}: offset must be applied")
        if baseline and baseline < "04.00":
            return out(zero, "confirmed", f"baseline {baseline} predates the offset: none applies")
        return out(zero, "ambiguous", "boa_offset_applied=false but baseline unknown")
    # flag missing
    if baseline and baseline < "04.00" and all(meta[b]["offset"] == 0 for b in meta):
        return out(zero, "confirmed", f"baseline {baseline} predates the offset: none applies")
    return out(zero, "ambiguous",
               f"no boa_offset_applied flag; baseline {baseline or '?'}, raster:bands offset "
               f"{meta['red']['offset']}: correction state cannot be determined")


def water_sanity(nir_refl: np.ndarray, scl: np.ndarray) -> tuple[float | None, bool, str]:
    """(median NIR over SCL-water cells, ok?, message). A failed check means the
    scaling or the scene quality needs verification - it does not by itself prove
    what correction was or was not applied."""
    w = (scl == 6) & np.isfinite(nir_refl)
    n = int(w.sum())
    if n < 50:
        return None, True, f"only {n} SCL-water cells: scaling not verified by water"
    med = float(np.median(nir_refl[w]))
    if med < WATER_NIR_MIN:
        return med, False, (f"water NIR median {med:.3f} is strongly negative: scaling or scene "
                            f"quality needs verification (a doubly applied offset is one cause)")
    if med > WATER_NIR_MAX:
        return med, False, (f"water NIR median {med:.3f} is implausibly bright: scaling or scene "
                            f"quality needs verification (an unapplied offset is one cause)")
    return med, True, f"water NIR median {med:.3f} over {n} cells: plausible"


def ndvi(nir, red):
    return (nir - red) / np.maximum(nir + red, 1e-6)


# ---------------------------------------------------------------- scene loading

def _load_scene(s2_dir, tag, crs, tr, shape, offset_mode, strict=True):
    sc = scaling_for(s2_dir, tag, offset_mode)
    if sc["status"] != "confirmed":
        msg = f"{tag}: {sc['reason']}. Set --offset-a/--offset-b (applied|apply|none) after checking the product."
        if strict:
            raise SystemExit(msg)
        print("  WARNING " + msg)
    red_dn = read_on_grid(os.path.join(s2_dir, f"{tag}_B04.tif"), crs, tr, shape)
    nir_dn = read_on_grid(os.path.join(s2_dir, f"{tag}_B08.tif"), crs, tr, shape)
    scl = read_on_grid(os.path.join(s2_dir, f"{tag}_SCL.tif"), crs, tr, shape, dtype=np.uint8)
    nodata = (red_dn == 0) | (nir_dn == 0)
    red = red_dn * sc["scale"]["red"] + sc["offset"]["red"]
    nir = nir_dn * sc["scale"]["nir"] + sc["offset"]["nir"]
    med, ok, verdict = water_sanity(nir, scl)
    inside = cells_inside_bounds(os.path.join(s2_dir, f"{tag}_B04.tif"), crs, tr, shape)
    return {"red": red, "nir": nir, "scl": scl, "nodata": nodata, "inside": inside,
            "scaling": sc, "water_check": verdict, "water_ok": ok, "water_nir": med}


# ---------------------------------------------------------------- two-date change

def bare_change(s2_dir: str, tag_a: str, tag_b: str, bbox, out_dir: str,
                zones=None, stride: int = 2, ndvi_max: float = 0.25,
                nir_min: float = 0.05, red_max: float = 0.35,
                min_cluster_ha: float = 20.0, label: str = "aoi",
                offset_mode: str = "auto", offset_mode_a: str | None = None,
                offset_mode_b: str | None = None, min_coverage_pct: float = 50.0) -> dict:
    """Bare ground on date A vs date B, per zone, on a common valid mask.

    Expects <tag>_B04.tif, <tag>_B08.tif, <tag>_SCL.tif and <tag>_stac.json in
    `s2_dir`. `zones` = [(name, geometry EPSG:4326)]; None means the bbox.
    """
    from scipy import ndimage

    crs, tr, shape, _ = reference_grid(os.path.join(s2_dir, f"{tag_b}_B04.tif"), bbox, stride)
    A = _load_scene(s2_dir, tag_a, crs, tr, shape, offset_mode_a or offset_mode)
    B = _load_scene(s2_dir, tag_b, crs, tr, shape, offset_mode_b or offset_mode)
    for tag, S in ((tag_a, A), (tag_b, B)):
        print(f"  {tag}: {S['scaling']['reason']}")
        print(f"  {tag}: {S['water_check']}")
        if not S["water_ok"]:
            raise SystemExit(f"{tag}: refusing to continue - {S['water_check']}")

    if zones is None:
        zones = [(label, {"type": "Polygon", "coordinates": [[
            [bbox[0], bbox[1]], [bbox[2], bbox[1]], [bbox[2], bbox[3]],
            [bbox[0], bbox[3]], [bbox[0], bbox[1]]]]})]
    zone_ids = rasterize_zones(
        [(transform_geom("EPSG:4326", crs, g), i + 1) for i, (_, g) in enumerate(zones)],
        tr, shape)
    aoi = zone_ids > 0
    covered = aoi & A["inside"] & B["inside"]
    cov_pct = 100 * covered.sum() / max(int(aoi.sum()), 1)
    if cov_pct < min_coverage_pct:
        raise SystemExit(f"only {cov_pct:.1f}% of the AOI lies inside both scenes' footprints; "
                         f"pick scenes that cover the AOI")
    if cov_pct < 99:
        print(f"  WARNING: only {cov_pct:.1f}% of the AOI lies inside both scenes")

    valid = covered & ~A["nodata"] & ~B["nodata"] & np.isin(A["scl"], SCL_KEEP) & np.isin(B["scl"], SCL_KEEP)
    bare_a = valid & (ndvi(A["nir"], A["red"]) < ndvi_max) & (A["nir"] > nir_min) & (A["red"] < red_max)
    bare_b = valid & (ndvi(B["nir"], B["red"]) < ndvi_max) & (B["nir"] > nir_min) & (B["red"] < red_max)
    new_bare = bare_b & ~bare_a
    no_longer_bare = bare_a & ~bare_b

    cell_ha = abs(tr.a * tr.e) / 10_000.0
    os.makedirs(out_dir, exist_ok=True)
    rows = []
    for i, (name, _) in enumerate(zones):
        z = zone_ids == i + 1
        n_aoi = max(int(z.sum()), 1)
        rows.append({
            "zone": name,
            "zone_area_ha": round(int(z.sum()) * cell_ha, 1),
            "in_both_scenes_pct": round(100 * (z & covered).sum() / n_aoi, 1),
            "common_valid_pct": round(100 * (z & valid).sum() / n_aoi, 1),
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
        "inputs": {t: {"files": [f"{t}_B04.tif", f"{t}_B08.tif", f"{t}_SCL.tif"],
                       "scaling": S["scaling"], "water_check": S["water_check"],
                       "water_nir_median": S["water_nir"]}
                   for t, S in ((tag_a, A), (tag_b, B))},
        "reference_grid": {"crs": crs.to_string(), "transform": list(tr)[:6], "shape": list(shape),
                           "cell_m": abs(tr.a), "stride": stride},
        "aoi_in_both_scenes_pct": round(cov_pct, 1),
        "thresholds": {"ndvi_max": ndvi_max, "nir_min": nir_min, "red_max": red_max,
                       "min_cluster_ha": min_cluster_ha, "scl_keep": list(SCL_KEEP),
                       "water_nir_range": [WATER_NIR_MIN, WATER_NIR_MAX]},
        "bbox": list(bbox), "zones": [z for z, _ in zones],
        "note": "single-date NDVI tracks crop phenology; confirm with a second season "
                "before calling any of this permanent change",
    }
    with open(os.path.join(out_dir, f"{label}_change_manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, default=str)
    return {"rows": rows, "clusters": clusters, "manifest": manifest}


# ---------------------------------------------------------------- NDVI trajectory

def ndvi_trajectory(s2_dir: str, tags_dates, bbox, out_csv: str,
                    masks: dict[str, np.ndarray] | None = None,
                    stride: int = 2, offset_mode: str = "auto",
                    offset_modes: dict[str, str] | None = None) -> dict:
    """Median NDVI per date for pixel groups on the first scene's reference grid.
    `masks` maps group name -> boolean array on that grid. Always include an
    undisturbed control group. `offset_modes` overrides per tag."""
    crs, tr, shape, _ = reference_grid(os.path.join(s2_dir, f"{tags_dates[0][0]}_B04.tif"),
                                       bbox, stride)
    groups = masks or {"aoi": np.ones(shape, bool)}
    series: dict[str, list] = {k: [] for k in groups}
    rows = []
    for tag, date in tags_dates:
        S = _load_scene(s2_dir, tag, crs, tr, shape, (offset_modes or {}).get(tag, offset_mode))
        if not S["water_ok"]:
            raise SystemExit(f"{tag}: {S['water_check']}")
        v = ndvi(S["nir"], S["red"])
        valid = np.isin(S["scl"], SCL_KEEP) & ~S["nodata"] & S["inside"]
        for name, m in groups.items():
            sel = m & valid
            cnt = int(sel.sum())
            med = float(np.median(v[sel])) if cnt > 100 else float("nan")
            series[name].append(med)
            rows.append({"date": date, "group": name, "valid_px": cnt,
                         "valid_pct": round(100 * cnt / max(int(m.sum()), 1), 1),
                         "ndvi_median": "" if np.isnan(med) else round(med, 3),
                         "scaling": S["scaling"]["reason"]})
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
