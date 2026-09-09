"""Resolve and download the public rasters an AOI needs.

Every source here is free and needs no account. Files are fetched with `curl`
(external command) because GDAL's /vsicurl is blocked or unusably slow in some
environments; the whole toolkit assumes local files.
"""
from __future__ import annotations

import json
import os
import subprocess
import urllib.request

from .geo_util import (esri_tiles, hansen_tile_name, jrc_tile_name, load_zones,
                       tiles_10deg_nw, worldcover_tiles, zones_bbox)

# Bump these when the upstream projects publish a new version.
HANSEN_VERSION = "GFC-2025-v1.13"        # 2000-2025
WORLDCOVER_VERSION, WORLDCOVER_YEAR = "v200", "2021"
JRC_BASE = "https://storage.googleapis.com/water-world/download2024/VER1-5"  # 1984-2024
ESRI_YEARS = tuple(range(2017, 2024))    # the v003 path stops at 2023

STAC_URL = "https://earth-search.aws.element84.com/v1/search"


def aoi_bbox(path_or_bbox) -> tuple[float, float, float, float]:
    """Accept a GeoJSON path or an explicit bbox tuple/list."""
    if isinstance(path_or_bbox, (list, tuple)):
        return tuple(float(v) for v in path_or_bbox)  # type: ignore[return-value]
    return zones_bbox(load_zones(path_or_bbox))


def urls_for(bbox) -> dict[str, list[tuple[str, str]]]:
    """{group: [(local filename, url), ...]} for every raster the AOI touches."""
    out: dict[str, list[tuple[str, str]]] = {}
    v, y = WORLDCOVER_VERSION, WORLDCOVER_YEAR

    out["worldcover"] = [
        (f"ESA_WorldCover_10m_{y}_{v}_{t}_Map.tif",
         f"https://esa-worldcover.s3.eu-central-1.amazonaws.com/{v}/{y}/map/"
         f"ESA_WorldCover_10m_{y}_{v}_{t}_Map.tif")
        for t in worldcover_tiles(bbox)]

    tiles = tiles_10deg_nw(bbox)
    out["hansen"] = [
        (f"Hansen_{HANSEN_VERSION}_{layer}_{hansen_tile_name(*t)}.tif",
         f"https://storage.googleapis.com/earthenginepartners-hansen/{HANSEN_VERSION}/"
         f"Hansen_{HANSEN_VERSION}_{layer}_{hansen_tile_name(*t)}.tif")
        for t in tiles for layer in ("treecover2000", "lossyear", "datamask")]

    out["jrc"] = [
        (f"{prod}_{jrc_tile_name(*t)}_v1_5_2024.tif",
         f"{JRC_BASE}/{prod}/{prod}_{jrc_tile_name(*t)}_v1_5_2024.tif")
        for t in tiles for prod in ("occurrence", "transitions")]

    out["esri"] = [
        (f"esri_lulc_{yr}_{z}.tif",
         f"https://lulctimeseries.blob.core.windows.net/lulctimeseriesv003/lc{yr}/"
         f"{z}_{yr}0101-{yr + 1}0101.tif")
        for z in esri_tiles(bbox) for yr in ESRI_YEARS]

    return out


def download(pairs, out_dir: str, timeout: int = 1800, min_bytes: int = 1000) -> list[str]:
    """Fetch with curl. HTTP errors and truncated transfers are failures, never cached.

    Returns the list of filenames that failed.
    """
    os.makedirs(out_dir, exist_ok=True)
    failed = []
    for name, url in pairs:
        dst = os.path.join(out_dir, name)
        part = dst + ".part"
        if os.path.exists(dst) and os.path.getsize(dst) >= min_bytes:
            print(f"  skip {name}")
            continue
        print(f"  get  {name}")
        r = subprocess.run(["curl", "-fsSL", "--retry", "2", "-m", str(timeout),
                            url, "-o", part], check=False)
        size = os.path.getsize(part) if os.path.exists(part) else 0
        if r.returncode != 0 or size < min_bytes:
            print(f"       FAILED (curl exit {r.returncode}, {size} bytes) - not kept")
            if os.path.exists(part):
                os.remove(part)
            failed.append(name)
            continue
        os.replace(part, dst)
        print(f"       {size / 1e6:.1f} MB")
    return failed


def s2_search(bbox, start: str, end: str, max_cloud: float = 20.0, limit: int = 10):
    """Sentinel-2 L2A scenes over the AOI centre, least cloudy first.

    Note the search is a point query on the AOI centre: it does not guarantee
    that one scene covers the whole AOI, nor that two scenes share a grid.
    `change` reprojects onto a common grid, but coverage is on you.
    """
    body = {
        "collections": ["sentinel-2-l2a"],
        "intersects": {"type": "Point",
                       "coordinates": [(bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2]},
        "datetime": f"{start}T00:00:00Z/{end}T23:59:59Z",
        "query": {"eo:cloud_cover": {"lt": max_cloud}},
        "limit": limit,
        "sortby": [{"field": "properties.eo:cloud_cover", "direction": "asc"}],
    }
    req = urllib.request.Request(STAC_URL, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=90) as r:
        doc = json.load(r)
    rows = []
    for f in doc.get("features", []):
        p, a = f["properties"], f["assets"]
        rows.append({
            "id": f["id"], "date": p["datetime"][:10],
            "cloud": round(p["eo:cloud_cover"], 1),
            "grid": p.get("grid:code"),
            "boa_offset_applied": p.get("earthsearch:boa_offset_applied"),
            "processing_baseline": p.get("s2:processing_baseline"),
            "assets": {"B04": a["red"]["href"], "B08": a["nir"]["href"],
                       "B03": a["green"]["href"], "SCL": a["scl"]["href"],
                       "TCI": a["visual"]["href"]},
            "item": f,
        })
    return rows


def download_scene(scene: dict, out_dir: str, tag: str,
                   bands=("B04", "B08", "SCL"), overwrite: bool = False) -> list[str]:
    """Download selected bands as <tag>_<band>.tif plus a <tag>_stac.json sidecar.

    The sidecar keeps the full STAC item so `change` can decide how to scale
    reflectance later. A tag is bound to one scene: if files for `tag` already
    exist and belong to a different scene id (or to no known scene), the call
    stops - or, with overwrite=True, removes them first. The sidecar is written
    last and only when every band downloaded, so images and metadata cannot
    disagree.
    """
    os.makedirs(out_dir, exist_ok=True)
    item = scene.get("item", scene)
    new_id = item.get("id") or scene.get("id")
    side = os.path.join(out_dir, f"{tag}_stac.json")
    band_files = [os.path.join(out_dir, f"{tag}_{b}.tif") for b in bands]
    existing = [p for p in band_files if os.path.exists(p)]
    old_id = None
    if os.path.exists(side):
        try:
            old_id = json.load(open(side, encoding="utf-8")).get("id")
        except (OSError, ValueError):
            old_id = None
    if existing and old_id != new_id:
        if not overwrite:
            raise SystemExit(f"tag {tag!r} already holds files for scene {old_id!r}; "
                             f"use another tag, or overwrite=True, to fetch {new_id!r}")
        for p in existing + ([side] if os.path.exists(side) else []):
            os.remove(p)
    pairs = [(f"{tag}_{b}.tif", scene["assets"][b]) for b in bands]
    failed = download(pairs, out_dir)
    if failed:
        print(f"  {tag}: {len(failed)} band(s) failed; sidecar not written")
        return failed
    with open(side, "w", encoding="utf-8") as fh:
        json.dump(item, fh)
    return failed
