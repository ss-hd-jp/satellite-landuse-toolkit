"""Geometry, area and tile-naming helpers (region independent).

Only depends on numpy (+ rasterio for the raster helpers). No geopandas / shapely.
"""
from __future__ import annotations

import json
import math
import re

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


def zones_bbox(zones) -> tuple[float, float, float, float]:
    xs, ys = [], []
    for _, g in zones:
        b = bbox_of(g)
        xs += [b[0], b[2]]
        ys += [b[1], b[3]]
    return min(xs), min(ys), max(xs), max(ys)


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

    Latitude-band formula R^2 * dlon * (sin lat1 - sin lat2) on the authalic
    sphere. This is the area of the *pixel cell*; it says nothing about how
    well the pixel's class label matches the ground.
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


def rasterize_zones(geoms_values, transform, shape, all_touched: bool = False,
                    dtype: str = "uint16") -> np.ndarray:
    """Burn [(geometry, value), ...] into an integer array (0 = outside).

    Later geometries overwrite earlier ones where they overlap. If your zones
    overlap, rasterize them one at a time instead.
    """
    from rasterio.features import rasterize
    maxv = max((v for _, v in geoms_values), default=0)
    if dtype == "uint8" and maxv > 255:
        raise ValueError("more than 255 zones: use dtype='uint16' or 'uint32'")
    if dtype == "uint16" and maxv > 65535:
        raise ValueError("more than 65535 zones: use dtype='uint32'")
    return rasterize(geoms_values, out_shape=shape, transform=transform,
                     fill=0, dtype=dtype, all_touched=all_touched)


def expected_zone_area_ha(zones, bbox, pixel_deg: float = 1 / 4000,
                          strip_rows: int = 2048) -> np.ndarray:
    """Area of each zone by rasterizing it on a synthetic lat/lon grid, strip by
    strip, so memory is bounded by one strip rather than by the AOI.

    Used to report what share of the AOI the available tiles actually covered.
    Numerator and denominator are rasterized on different grids, so a very
    small zone can show a fraction of a percent of boundary effect.
    """
    from rasterio.transform import from_origin
    minx, miny, maxx, maxy = bbox
    w = max(1, int(math.ceil((maxx - minx) / pixel_deg)))
    h = max(1, int(math.ceil((maxy - miny) / pixel_deg)))
    geoms = [(g, i + 1) for i, (_, g) in enumerate(zones)]
    out = np.zeros(len(zones))
    for r0 in range(0, h, strip_rows):
        rows = min(strip_rows, h - r0)
        top = maxy - r0 * pixel_deg
        ids = rasterize_zones(geoms, from_origin(minx, top, pixel_deg, pixel_deg), (rows, w))
        if not ids.any():
            continue
        ha = row_area_m2(top, pixel_deg, rows, pixel_deg) / 10_000.0
        for i in range(len(zones)):
            out[i] += sum_area_ha(ids == i + 1, ha)
    return out


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
    """Hansen GFC tile name, zero-padded: 10N_120E, 00N_000E, 10S_010W."""
    ns = "N" if lat_top >= 0 else "S"
    ew = "E" if lon_left >= 0 else "W"
    return f"{abs(lat_top):02d}{ns}_{abs(lon_left):03d}{ew}"


def jrc_tile_name(lat_top: int, lon_left: int) -> str:
    """JRC Global Surface Water tile name. NOT zero-padded: 120E_10N, 0E_10N, 10W_10S.

    Verified against the v1.5 bucket (2026-09): `000E_10N` and `010E_10N` return
    404, `0E_10N` and `10E_10N` return 200. Do not reuse the Hansen convention.
    """
    ns = "N" if lat_top >= 0 else "S"
    ew = "E" if lon_left >= 0 else "W"
    return f"{abs(lon_left)}{ew}_{abs(lat_top)}{ns}"


HANSEN_TILE_RE = re.compile(r"_(\d{2}[NS]_\d{3}[EW])\.tif$")
JRC_TILE_RE = re.compile(r"_(\d{1,3}[EW]_\d{1,2}[NS])_v")
HANSEN_VERSION_RE = re.compile(r"(GFC-(\d{4})-v[\d.]+)")


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


def esri_tiles(bbox) -> list[str]:
    """Every Esri tile (zone x band) the bbox touches, not just its corners."""
    minx, miny, maxx, maxy = bbox
    zones = range(int((minx + 180) // 6) + 1, int((maxx + 180) // 6) + 2)
    bands = []
    lat = miny
    while lat <= maxy:
        b = mgrs_band(lat)
        if b not in bands:
            bands.append(b)
        lat += 8
    bmax = mgrs_band(maxy)
    if bmax not in bands:
        bands.append(bmax)
    return [f"{z}{b}" for z in zones for b in bands]
