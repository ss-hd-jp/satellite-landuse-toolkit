# Quickstart

A complete run over a small area. Replace the bounding box with yours.

The commands below are Bash. On Windows PowerShell, either type the arguments
out in full or splat an array — a string such as `$AOI = "--bbox ..."` is
passed as *one* argument and will not work:

```powershell
$AOI = @("--bbox", "138.55", "36.95", "138.75", "37.10")
python -m slandu forest @AOI --data-dir data/rasters --out-dir out
```

```bash
export AOI="--bbox 138.55 36.95 138.75 37.10"      # minlon minlat maxlon maxlat
export DATA=data/rasters
export OUT=out
```

## 1. See what the area needs, then fetch it

```bash
python -m slandu fetch $AOI                                   # list URLs only
python -m slandu fetch $AOI --data-dir $DATA --only hansen jrc --download
```

Downloads use `curl -f`; an HTTP error or truncated transfer is reported as a
failure and never kept as a cached file. Sizes per tile: WorldCover ~10 MB,
Hansen `lossyear` ~30 MB / `treecover2000` ~140 MB, JRC ~20–50 MB, Esri Annual
Land Cover 100–200 MB **per year**.

## 2. Land cover in 2021

```bash
python -m slandu fetch $AOI --data-dir $DATA --only worldcover --download
python -m slandu landcover $AOI --data-dir $DATA --out-dir $OUT
```

→ `out/landcover_by_zone.csv`. Print national crop statistics beside the
`cropland` row before concluding anything (pitfall 4).

## 3. Tree-cover loss over time

```bash
python -m slandu forest $AOI --data-dir $DATA --out-dir $OUT --hotspot-from 2016
```

→ `forest_loss_annual.csv` (every year from 2001 to the dataset's end, zeros
included), `forest_loss_summary.csv` (with `tiles_coverage_pct` — anything
below ~99 % means a tile is missing), `forest_loss_threshold_sensitivity.csv`,
`forest_loss_hotspots_from2016.csv`.

`no_loss_detected_ha` is **not** remaining forest (pitfall 1). Hotspot rows give
the cell's real area and the loss share; open the top cells in an imagery
viewer before interpreting them.

Per district:

```bash
python -m slandu forest --aoi aoi/districts.geojson --name-field name \
    --data-dir $DATA --out-dir $OUT
```

## 4. Surface water, and one lake in particular

```bash
python -m slandu water $AOI --data-dir $DATA --out-dir $OUT \
    --seed 138.62 37.02 --label lake
```

→ `water_transitions.csv` per zone; `lake_water_summary.csv` for the
**connected area of occurrence ≥ 5 % containing the seed**. That region can
include channels joined to the lake and is not a validated lake boundary or the
provider's Maximum Water Extent layer.

Read the ≥5 % and ≥95 % areas together, but do not read their gap as
"seasonality rather than shrinkage": long-term occurrence mixes intra-annual,
inter-annual and secular change, and a lake that shrank over decades also
produces intermediate occurrence values. Separating the two needs a time series.

## 5. Two-date change from Sentinel-2

```bash
python -m slandu fetch $AOI --s2-search 2019-06-01 2019-12-31 --s2-cloud 10
python -m slandu fetch $AOI --s2-search 2026-01-01 2026-08-31 --s2-cloud 10
```

The search is a point query on the AOI centre; check that the scenes you pick
actually cover the AOI. Download with the helper so the STAC sidecar is kept —
`change` needs it to decide reflectance scaling:

```python
from slandu.fetch import s2_search, download_scene
bbox = (138.55, 36.95, 138.75, 37.10)
early = s2_search(bbox, "2019-06-01", "2019-12-31", 10)[0]
late  = s2_search(bbox, "2026-01-01", "2026-08-31", 10)[0]
download_scene(early, "data/s2", tag="early")
download_scene(late,  "data/s2", tag="late")
```

Then:

```bash
python -m slandu change $AOI --s2-dir data/s2 --tag-a early --tag-b late \
    --out-dir $OUT --label myaoi
```

→ `myaoi_bare_change_summary.csv` (per zone), `myaoi_new_bare_clusters.csv`,
`myaoi_change_manifest.json` (inputs, grid, scaling decision, thresholds).

Both scenes are reprojected onto the later scene's grid, coarsened to
`stride`×10 m (default 20 m). The scaling decision and its water-pixel sanity
check are printed; the run stops if the offset looks double-applied. Read
`common_valid_pct` first. A single-date NDVI difference also tracks crop
phenology — before calling anything permanent, repeat with a second season.

## 6. Before you publish

Work through [`docs/pitfalls.md`](../docs/pitfalls.md).
