# Quickstart

A complete run over a small area. Replace the bounding box with yours.
Rough download sizes are noted so nothing surprises you.

```bash
export AOI="--bbox 138.55 36.95 138.75 37.10"      # minlon minlat maxlon maxlat
export DATA=data/rasters
export OUT=out
```

On Windows PowerShell use `$AOI = "--bbox ..."` or just paste the arguments.

## 1. See what the area needs, then fetch it

```bash
python -m slandu fetch $AOI                                   # list URLs only
python -m slandu fetch $AOI --data-dir $DATA --only hansen jrc --download
```

`--only` keeps the download small. Sizes per tile: WorldCover ~10 MB,
Hansen `lossyear` ~30 MB / `treecover2000` ~140 MB, JRC ~20–50 MB,
Esri Annual LULC 100–200 MB **per year**.

## 2. Land cover today

```bash
python -m slandu fetch $AOI --data-dir $DATA --only worldcover --download
python -m slandu landcover $AOI --data-dir $DATA --out-dir $OUT
```

→ `out/landcover_by_zone.csv` (area and share per class).

Print national crop statistics next to the `cropland` row before drawing any
conclusion — see pitfall 4.

## 3. Tree-cover loss over time

```bash
python -m slandu forest $AOI --data-dir $DATA --out-dir $OUT --hotspot-from 2016
```

→ `forest_loss_annual.csv`, `forest_loss_summary.csv`,
`forest_loss_threshold_sensitivity.csv`,
`forest_loss_hotspots_1km_from2016.csv`.

The summary column is `no_loss_detected_ha`. It is **not** remaining forest —
see pitfall 1. The hotspot file gives you coordinates: open a couple of the top
cells in any imagery viewer before you interpret them.

To break the result down by district, pass a GeoJSON instead:

```bash
python -m slandu forest --aoi aoi/districts.geojson --name-field name \
    --data-dir $DATA --out-dir $OUT
```

## 4. Surface water, and one lake in particular

```bash
python -m slandu water $AOI --data-dir $DATA --out-dir $OUT \
    --seed 138.62 37.02 --label lake
```

→ `water_transitions.csv` for the zones, `lake_water_summary.csv` for the water
body containing the seed point. The seed matters: a bounding box alone pulls in
rivers, estuaries and paddies, and inflates the "lake".

Read the maximum extent (`occurrence>=5%`) and the near-permanent area
(`occurrence>=95%`) together. A large gap between them means a water body that
swings seasonally rather than one that simply shrank.

## 5. Two-date change from Sentinel-2

Find scenes, download three bands each, then compare.

```bash
python -m slandu fetch $AOI --s2-search 2019-06-01 2019-12-31 --s2-cloud 10
python -m slandu fetch $AOI --s2-search 2026-01-01 2026-08-31 --s2-cloud 10
```

Download the bands you need (`B04`, `B08`, `SCL`) into `data/s2/` naming them
`<tag>_B04.tif` etc. — for example with the helper:

```python
from slandu.fetch import s2_search, download_scene
scenes = s2_search((138.55, 36.95, 138.75, 37.10), "2026-01-01", "2026-08-31", 10)
download_scene(scenes[0], "data/s2", tag="late")
```

Then:

```bash
python -m slandu change $AOI --s2-dir data/s2 --tag-a early --tag-b late \
    --out-dir $OUT --label myaoi
```

→ `myaoi_bare_change_summary.csv` and `myaoi_new_bare_clusters.csv`.

Check `common_valid_pct` first. Everything is computed on pixels valid on both
dates, so this number tells you how much of the area the comparison actually
covers. A single-date NDVI difference also tracks crop phenology: before calling
anything permanent, repeat with a second season and keep only ground that is
bare in both.

## 6. Before you publish

Work through [`docs/pitfalls.md`](../docs/pitfalls.md). It is ten checks and
takes about fifteen minutes; it is the difference between an internal note and
something that survives review.
