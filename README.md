# satellite-landuse-toolkit

Local, reproducible tallies of land cover, tree-cover loss and surface-water
change from **free, account-free satellite products** — ESA WorldCover, Hansen
Global Forest Change, JRC Global Surface Water and Sentinel-2 L2A. No Earth
Engine, no API keys; everything runs from downloaded tiles.

**What the outputs are:** areas of *map pixels* by class, on the analysis grid.
They are not statistical area estimates, not land *use*, not tenure, and not
evidence of cause or legality. The toolkit's job is to make those tallies
correct and to keep you from over-reading them; the interpretation rules that
reviewers enforce are in [docs/pitfalls.md](docs/pitfalls.md).

**Status:** pre-release (v1.0.0 candidate). An external review found several
defects in an earlier draft (multi-tile handling, period end, tile naming,
Sentinel-2 co-registration and offset handling, AOI masking); those are fixed
and covered by `tests/`. Coverage of the datasets is global-ish but not
universal — see *Limitations*.

## What it does

| Command | Source | Output |
|---|---|---|
| `slandu fetch` | — | resolves the tiles your AOI touches, downloads them (`curl`), Sentinel-2 scene search |
| `slandu landcover` | ESA WorldCover 10 m (2021) | area per class, per zone |
| `slandu forest` | Hansen GFC 30 m (2001–2025) | annual tree-cover loss per zone, tile coverage, threshold sensitivity, ~1 km hotspot cells |
| `slandu water` | JRC GSW v1.5 30 m (1984–2024) | transition classes per zone; connected water area around a seed point |
| `slandu change` | Sentinel-2 L2A | two-date bare-ground change per zone on one reference grid with a **common valid mask**; run manifest |

All tiles intersecting the AOI are summed; each result reports what share of
the AOI the available tiles covered. Lat/lon pixel areas use the exact
spherical latitude-band formula (that is cell area, not classification accuracy).

## Install

```bash
git clone https://github.com/ss-hd-jp/satellite-landuse-toolkit.git
cd satellite-landuse-toolkit
pip install -r requirements.txt
python -m pytest tests -q
```

Python 3.10+, `rasterio`, `numpy`, `scipy`, `Pillow`, and the external
command **`curl`** on your PATH. No geopandas, no shapely.

## Quickstart

```bash
python -m slandu fetch --bbox 138.55 36.95 138.75 37.10 --data-dir data/rasters --only hansen --download
python -m slandu forest --bbox 138.55 36.95 138.75 37.10 --data-dir data/rasters --out-dir out --hotspot-from 2016
```

`--aoi your_area.geojson` (EPSG:4326) instead of `--bbox` gives one row group
per feature, for every command including `change`. Full walk-through:
[examples/quickstart.md](examples/quickstart.md).

## Reading the output

Three points reviewers always raise:

**1. Hansen loss is not netted against regrowth.** The summary column is
`no_loss_detected_ha`, never "remaining forest": a pixel that lost its canopy
in 2005 and is fully wooded today still counts as loss. Say
*"area with >30 % canopy in 2000 where no loss has been detected"*. The
provider also states that definitive area estimates should not be made from
loss-pixel counts and that intervals are not strictly comparable across sensor
and algorithm changes — treat `annual_mean_first10` vs `last10` as descriptive.

**2. Land cover ≠ land use ≠ tenure.** WorldCover 2021's global overall accuracy
is 76.7 %; that is not a per-class or per-region figure, and cropland
under-detection *can* occur in rotational or smallholder landscapes. Print
national crop statistics next to the map figure, and remember a harvested-area
statistic is a *flow* (a field cropped twice counts twice) while land cover is
a *stock*.

**3. Two-date change depends on registration, scaling and masking.**
`slandu change` reprojects both scenes onto one reference grid, decides the
reflectance scaling per scene from its STAC sidecar and then checks it against
water pixels (refusing to run on a double-applied offset), keeps SCL classes
4/5/7 only, and compares only pixels valid on both dates (`common_valid_pct`).
It cannot remove residual haze, shadow, BRDF or seasonal effects — one date
pair is a candidate, not a finding.

## Data sources

Versions, URL patterns, licences, required citation and attribution strings,
and the traps in each dataset: [docs/data_catalog.md](docs/data_catalog.md).

- ESA WorldCover 10 m 2021 v200 — CC BY 4.0
- Hansen Global Forest Change 2025 v1.13 — CC BY 4.0, credit `Source: Hansen/UMD/Google/USGS/NASA`
- JRC Global Surface Water v1.5 (1984–2024) — Copernicus terms, credit `Source: EC JRC/Google`
- Sentinel-2 L2A COGs on AWS via the Earth Search STAC API — `Contains modified Copernicus Sentinel data [year].`
- Esri 10 m Annual Land Cover (v003 path, 2017–2023) — URL resolution only

**Attribution of what you publish is your responsibility.** Do not append
`processed by ESA` to your own Sentinel-2 analysis.

Administrative boundaries are not bundled. If you use geoBoundaries, the
source and licence can differ per level (ADM1 vs ADM2 of the same country), and
when they do the national total will not equal the sum of subdivisions —
check the API metadata and footnote the difference.

## Limitations

- Zonal statistics need lat/lon (geographic) rasters; `change` works in the
  scene's UTM CRS and reprojects inputs onto the later scene's grid.
- AOI must be EPSG:4326. Overlapping zones overwrite each other in the zone
  raster (later wins).
- Hansen covers 80°N–60°S; JRC and WorldCover have their own extents. AOIs
  crossing the antimeridian are not handled.
- `change` samples the 10 m bands onto a `stride`×10 m grid (default 20 m) by
  nearest neighbour; it does not aggregate every 10 m pixel. Scene footprints
  are not checked — verify both scenes cover the AOI.
- Hotspot cells are blocks of pixels on the lat/lon grid (~1 km at the
  equator); the CSV gives the true cell area rather than assuming 1 km².
- Tiles are downloaded whole (Sentinel-2 band ≈150 MB, Hansen `treecover2000`
  ≈140 MB). `/vsicurl` is deliberately unused.

## Citing

Cite the archived release (Zenodo DOI, see [CITATION.cff](CITATION.cff)) and,
separately, every upstream dataset you used.

## Licence

Code: [MIT](LICENSE). Downloaded datasets keep their own licences.
