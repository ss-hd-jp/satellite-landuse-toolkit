"""Resolve and download the public rasters an AOI needs.

Every source here is free and needs no account. Files are fetched with `curl`
because GDAL's /vsicurl is blocked or unusably slow in some environments; the
whole toolkit assumes local files.
"""
from __future__ import annotations

import json
import os
import subprocess
import urllib.request

from .geo_util import (bbox_of, esri_tile, hansen_tile_name, jrc_tile_name,
                       load_zones, tiles_10deg_nw, worldcover_tiles)

# Bump these when the upstream projects publish a new version.
HANSEN_VERSION = "GFC-2025-v1.13"        # 2000-2025
WORLDCOVER_VERSION, WORLDCOVER_YEAR = "v200", "2021"
JRC_BASE = "https://storage.googleapis.com/water-world/download2024/VER1-5"  # 1984-2024
ESRI_YEARS = tuple(range(2017, 2024))    # v003 stops at 2023

STAC_URL = "https://earth-search.aws.element84.com/v1/search"


def aoi_bbox(path_or_bbox) -> tuple[float, float, float, float]:
    """Accept a GeoJSON path or an explicit bbox tuple/list."""
    if isinstance(path_or_bbox, (list, tuple)):
        return tuple(float(v) for v in path_or_bbox)  # type: ignore[return-value]
    zones = load_zones(path_or_bbox)
    xs, ys = [], []
    for _, g in zones:
        b = bbox_of(g)
        xs += [b[0], b[2]]
        ys += [b[1], b[3]]
    return min(xs), min(ys), max(xs), max(ys)


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

    mid_lat = (bbox[1] + bbox[3]) / 2
    zones = sorted({esri_tile(bbox[0], mid_lat), esri_tile(bbox[2], mid_lat)})
    out["esri"] = [
        (f"esri_lulc_{yr}_{z}.tif",
         f"https://lulctimeseries.blob.core.windows.net/lulctimeseriesv003/lc{yr}/"
         f"{z}_{yr}0101-{yr + 1}0101.tif")
        for z in zones for yr in ESRI_YEARS]

    return out


def download(pairs, out_dir: str, timeout: int = 1800) -> None:
    """Fetch with curl, skipping files that already exist."""
    os.makedirs(out_dir, exist_ok=True)
    for name, url in pairs:
        dst = os.path.join(out_dir, name)
        if os.path.exists(dst) and os.path.getsize(dst) > 0:
            print(f"  skip {name}")
            continue
        print(f"  get  {name}")
        subprocess.run(["curl", "-sL", "-m", str(timeout), url, "-o", dst], check=False)
        size = os.path.getsize(dst) if os.path.exists(dst) else 0
        print(f"       {size / 1e6:.1f} MB")
        if size < 1000:
            print("       WARNING: suspiciously small - check the URL/tile name")


def s2_search(bbox, start: str, end: str, max_cloud: float = 20.0, limit: int = 10):
    """Sentinel-2 L2A scenes over the AOI centre, least cloudy first."""
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
            "assets": {"B04": a["red"]["href"], "B08": a["nir"]["href"],
                       "B03": a["green"]["href"], "SCL": a["scl"]["href"],
                       "TCI": a["visual"]["href"]},
        })
    return rows


def download_scene(scene: dict, out_dir: str, tag: str,
                   bands=("B04", "B08", "SCL")) -> None:
    """Download selected bands of one STAC scene as <tag>_<band>.tif."""
    pairs = [(f"{tag}_{b}.tif", scene["assets"][b]) for b in bands]
    download(pairs, out_dir)
