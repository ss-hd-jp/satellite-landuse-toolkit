# satellite-landuse-toolkit

Land-use, forest-loss and surface-water analysis for **any area on Earth**, using
**only free, no-account satellite data**. No Earth Engine, no API keys, no cloud
compute — everything runs locally from downloaded tiles.

The toolkit exists because the same handful of mistakes turn a plausible-looking
land-use report into a wrong one. Those mistakes are handled in code and spelled
out in [docs/pitfalls.md](docs/pitfalls.md).

## What it does

| Command | Data source | Output |
|---|---|---|
| `slandu fetch` | resolves the tiles your AOI needs, downloads them | local GeoTIFFs |
| `slandu landcover` | ESA WorldCover 10 m | area per land-cover class, per zone |
| `slandu forest` | Hansen Global Forest Change 30 m | annual tree-cover loss per zone, 1 km hotspots, threshold sensitivity |
| `slandu water` | JRC Global Surface Water 30 m | water-transition classes per zone; one lake isolated by seed point |
| `slandu change` | Sentinel-2 L2A 10 m | two-date bare-ground change on a **common valid mask**, clustered |

Areas are integrated with the exact spherical latitude-band formula, not a
`cos(lat)` approximation.

## Install

```bash
git clone https://github.com/ss-hd-jp/satellite-landuse-toolkit.git
cd satellite-landuse-toolkit
pip install -r requirements.txt
```

Python 3.10+, `rasterio`, `numpy`, `scipy`, `Pillow`. No geopandas, no shapely.

## Quickstart

```bash
python -m slandu fetch --bbox 138.55 36.95 138.75 37.10 --data-dir data/rasters --only hansen --download
python -m slandu forest --bbox 138.55 36.95 138.75 37.10 --data-dir data/rasters --out-dir out --hotspot-from 2016
```

Use `--aoi your_area.geojson` instead of `--bbox` to get per-zone tables
(one row group per feature; the zone name comes from `--name-field`, default `name`).
See [examples/quickstart.md](examples/quickstart.md) for the full walk-through
including Sentinel-2 change detection.

## Reading the output honestly

Three points that reviewers always raise, handled up front:

**1. Hansen loss is not netted against regrowth.** The summary column is called
`no_loss_detected_ha`, never "remaining forest". A pixel that lost its canopy in
2005 and is fully wooded again today still counts as loss. Report it as
*"area with >30 % canopy in 2000 where loss has been detected"*.

**2. Land cover is not land use, and it is not tenure.** ESA WorldCover's global
overall accuracy is 76.7 %, and its `cropland` class is badly under-detected in
landscapes with rotational or smallholder agriculture. Always print national
crop statistics next to it — and remember that a harvested-area statistic is a
*flow* (a field cropped twice counts twice) while land cover is a *stock*.

**3. Cloud masking decides your answer.** `slandu change` keeps SCL classes
4/5/7 only, drops water (class 6), and compares **only pixels valid on both
dates**, reporting `common_valid_pct` so a reader can check. Without this, a
cloudier baseline date silently manufactures "change".

## Data sources

All free and account-free. Versions, URL patterns, licences, required citation
strings and the traps in each dataset are in
[docs/data_catalog.md](docs/data_catalog.md).

- ESA WorldCover 10 m (CC BY 4.0)
- Hansen Global Forest Change (UMD/Google/USGS/NASA)
- JRC Global Surface Water v1.5, 1984–2024 (EC JRC / Google)
- Sentinel-2 L2A COGs via AWS Open Data + the Earth Search STAC API
- Esri 10 m Annual Land Cover 2017–2023 (URL resolution only)

**You are responsible for the attribution of whatever you publish.** This
toolkit downloads other people's data; the required citation string for each
source is listed in the data catalog. In particular, do not add
`processed by ESA` to your own analysis of Sentinel-2 —
`Contains modified Copernicus Sentinel data [year].` is the correct form.

Administrative boundaries are *not* bundled. If you use
[geoBoundaries](https://www.geoboundaries.org/), note that **the source and
licence differ per level** (ADM1 and ADM2 of the same country can come from
different providers), which also means the national total may not equal the sum
of its subdivisions. Check the API metadata and state the difference in a footnote.

## Limitations

- Lat/lon rasters only for the zonal statistics (Sentinel-2 handling is UTM-aware).
- No reprojection of your AOI: give it in EPSG:4326.
- The union used for masking is a plain collection of polygons, not a topological
  dissolve — fine for rasterization, not for geometry work.
- Tiles are downloaded whole. A large AOI means large downloads (a Sentinel-2
  band is ~150 MB, a Hansen `treecover2000` tile ~140 MB).
- GDAL's `/vsicurl` is deliberately not used; some environments block or throttle
  it badly enough to hang.

## Citing

If this toolkit contributed to your work, please cite the archived release
(DOI is minted per version by Zenodo — see [CITATION.cff](CITATION.cff)) and,
separately, every upstream dataset you actually used.

## Licence

Code: [MIT](LICENSE). The datasets it downloads keep their own licences.
