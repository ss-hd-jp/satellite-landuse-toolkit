"""Geometry, area and tile-naming helpers (region independent).

Only depends on numpy (+ rasterio for the raster helpers). No geopandas / shapely.
"""
from __future__ import annotations

import json
import math

import numpy as np

R_EARTH = 6_371_007.181  # m, authalic sphere radius (same convention as ESA WorldCover)


# ---------------------------------------------------------------- geometry

def bbox_of(geom: dict) -> tuple[float, float, float, float]:
    """Bounding box (minx, miny, maxx, maxy) of a GeoJSON geometry."""
    xs: list[float] = []
    ys: list[float] = []

    def walk(c):
        if isinstance(c[0], (int, float)):
            xs.append(c[0]); ys.append(c[1])
        else:
            for x in c:
                walk(x)

    walk(geom["coordinates"])
    return min(xs), min(ys), max(xs), max(ys)


def bbox_geom(box) -> dict:
    """GeoJSON polygon from (minx, miny, maxx, maxy)."""
    minx, miny, maxx, maxy = box
    return {"type": "Polygon",
            "coordinates": [[[minx, miny], [maxx, miny], [maxx, maxy],
                             [minx, maxy], [minx, miny]]]}


def load_zones(path: str, name_field: str = "name") -> list[tuple[str, dict]]:
    """Read a GeoJSON file and return [(zone name, geometry), ...].

    Accepts a FeatureCollection, a single Feature, or a bare geometry.
    """
    obj = json.load(open(path, encoding="utf-8"))
    if obj.get("type") == "FeatureCollection":
        feats = obj["features"]
    elif obj.get("type") == "Feature":
        feats = [obj]
    else:
        return [("aoi", obj)]
    out = []
    for i, ft in enumerate(feats):
        props = ft.get("properties") or {}
        name = props.get(name_field)
        if name is None:
            for k in ("name", "NAME", "shapeName", "id"):
                if k in props:
                    name = props[k]
                    break
        out.append((str(name if name is not None else f"zone{i + 1}"), ft["geometry"]))
    return out


def union_geom(geoms: list[dict]) -> dict:
    """Cheap union: collect every polygon into one MultiPolygon (no dissolve).

    Fine for rasterization/masking, which is all this toolkit needs.
    """
    polys: list = []
    for g in geoms:
        if g["type"] == "Polygon":
            polys.append(g["coordinates"])
        elif g["type"] == "MultiPolygon":
            polys.extend(g["coordinates"])
    return {"type": "MultiPolygon", "coordinates": polys}


# ---------------------------------------------------------------- area

def row_area_m2(lat_top: float, pixel_deg: float, n_rows: int,
                pixel_deg_x: float | None = None) -> np.ndarray:
    """Exact spherical area [m^2] of one pixel in each raster row (EPSG:4326 only).

    Uses the latitude-band formula R^2 * dlon * (sin lat1 - sin lat2); do not
    approximate with cos(lat) * constant.
    """
    if pixel_deg_x is None:
        pixel_deg_x = pixel_deg
    lat1 = np.deg2rad(lat_top - pixel_deg * np.arange(n_rows))
    lat2 = np.deg2rad(lat_top - pixel_deg * (np.arange(n_rows) + 1))
    return (R_EARTH ** 2) * math.radians(pixel_deg_x) * (np.sin(lat1) - np.sin(lat2))


def sum_area_ha(mask: np.ndarray, row_ha: np.ndarray) -> float:
    """Total area [ha] of True pixels, given per-row pixel area [ha]."""
    return float((mask.sum(axis=1) * row_ha).sum())


# ---------------------------------------------------------------- raster windows

def window_for_bbox(ds, bbox):
    """Integer window of `ds` covering bbox, clipped to the dataset. None if disjoint."""
    from rasterio.windows import Window
    minx, miny, maxx, maxy = bbox
    b = ds.bounds
    minx, maxx = max(minx, b.left), min(maxx, b.right)
    miny, maxy = max(miny, b.bottom), min(maxy, b.top)
    if minx >= maxx or miny >= maxy:
        return None
    inv = ~ds.transform
    c0, r0 = inv * (minx, maxy)
    c1, r1 = inv * (maxx, miny)
    col, row = max(0, int(math.floor(c0))), max(0, int(math.floor(r0)))
    w = min(int(math.ceil(c1)) - col, ds.width - col)
    h = min(int(math.ceil(r1)) - row, ds.height - row)
    return Window(col, row, w, h) if w > 0 and h > 0 else None


def iter_strips(window, rows: int = 1024):
    """Split a window into horizontal strips to keep memory bounded."""
    from rasterio.windows import Window
    for off in range(0, int(window.height), rows):
        h = min(rows, int(window.height) - off)
        yield Window(window.col_off, window.row_off + off, window.width, h)


def rasterize_zones(geoms_values, transform, shape, all_touched: bool = False) -> np.ndarray:
    """Burn [(geometry, value), ...] into a uint8 array (0 = outside)."""
    from rasterio.features import rasterize
    return rasterize(geoms_values, out_shape=shape, transform=transform,
                     fill=0, dtype="uint8", all_touched=all_touched)


# ---------------------------------------------------------------- tile naming

def worldcover_tiles(bbox) -> list[str]:
    """ESA WorldCover 3-degree tile names, keyed on the SOUTH-WEST corner (e.g. N00E120)."""
    minx, miny, maxx, maxy = bbox
    out = []
    lat = math.floor(miny / 3) * 3
    while lat <= math.floor(maxy / 3) * 3:
        lon = math.floor(minx / 3) * 3
        while lon <= math.floor(maxx / 3) * 3:
            ns = "N" if lat >= 0 else "S"
            ew = "E" if lon >= 0 else "W"
            out.append(f"{ns}{abs(lat):02d}{ew}{abs(lon):03d}")
            lon += 3
        lat += 3
    return out


def tiles_10deg_nw(bbox) -> list[tuple[int, int]]:
    """10-degree tiles as (lat of north edge, lon of west edge)."""
    minx, miny, maxx, maxy = bbox
    out = []
    lat = math.ceil(maxy / 10) * 10
    while lat > miny:
        lon = math.floor(minx / 10) * 10
        while lon < maxx:
            out.append((lat, lon))
            lon += 10
        lat -= 10
    return out


def hansen_tile_name(lat_top: int, lon_left: int) -> str:
    """Hansen GFC tile name, e.g. 10N_120E."""
    ns = "N" if lat_top >= 0 else "S"
    ew = "E" if lon_left >= 0 else "W"
    return f"{abs(lat_top):02d}{ns}_{abs(lon_left):03d}{ew}"


def jrc_tile_name(lat_top: int, lon_left: int) -> str:
    """JRC Global Surface Water tile name, e.g. 120E_10N (longitude first)."""
    ns = "N" if lat_top >= 0 else "S"
    ew = "E" if lon_left >= 0 else "W"
    return f"{abs(lon_left):03d}{ew}_{abs(lat_top):02d}{ns}"


# MGRS latitude bands: 8 degrees each, letters C..X, omitting I and O (X spans 12).
_MGRS_BANDS = "CDEFGHJKLMNPQRSTUVWX"


def mgrs_band(lat: float) -> str:
    """MGRS latitude band letter for -80..84 degrees."""
    if lat >= 72:
        return "X"
    return _MGRS_BANDS[int((max(lat, -80) + 80) // 8)]


def esri_tile(lon: float, lat: float) -> str:
    """Esri Annual Land Cover tile = UTM zone number + MGRS BAND LETTER.

    WARNING: the suffix is the MGRS band, NOT the N/S hemisphere. Getting this
    wrong does not raise a 404 - a real tile for a different continent is
    returned with HTTP 200. Always verify `ds.bounds` covers your AOI.
    """
    z = int((lon + 180) // 6) + 1
    return f"{z}{mgrs_band(lat)}"
