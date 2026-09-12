# satellite-landuse-toolkit

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.22730573.svg)](https://doi.org/10.5281/zenodo.22730573)

Local, reproducible tallies of land cover, tree-cover loss and surface-water
change from **free, account-free satellite products** — ESA WorldCover, Hansen
Global Forest Change, JRC Global Surface Water and Sentinel-2 L2A. No Earth
Engine, no API keys; everything runs from downloaded tiles.

**What the outputs are:** areas of *map pixels* by class, on the analysis grid.
They are not statistical area estimates, not land *use*, not tenure, and not
evidence of cause or legality. The toolkit's job is to make those tallies
correct and to keep you from over-reading them; the interpretation rules that
reviewers enforce are in [docs/pitfalls.md](docs/pitfalls.md).

**Status:** v1.0.0, tagged 2026-09-13 and archived on Zenodo (DOI on the
release page and in `CITATION.cff`). Six rounds of external review preceded
the tag. The first found defects in an early draft (multi-tile
handling, period end, tile naming, Sentinel-2 co-registration and offset
handling, AOI masking). The second confirmed those fixes and raised further
issues — behaviour when the Sentinel-2 correction state cannot be determined,
an analysis window that clipped the AOI, hotspot ordering, scene-tag reuse,
memory of the coverage denominator, water zones vanishing from the CSV, and
tests without detection power. The third confirmed those and found two
remaining gaps (tag reuse when only some bands are requested; a stale
clusters CSV after a zero-change re-run); the fourth confirmed those fixes,
reproduced the example run record byte-for-byte, and found one more (a tag
matched by prefix, so overwriting `early` could delete `early_wet`); the
fifth confirmed that fix and found a Windows-specific one (tags differing
only in letter case are one set of files there); the sixth confirmed that
fix and raised no further findings within its scope (diff, regression
tests, tag handling). A first real run over a Japanese wetland then exposed a
one-pixel window mismatch between two JRC products of the same tile, fixed
with its own test. 26 regression tests pass (`tests/test_regression.py`
lists exactly what is checked; the tests added for each review fail against
the commit that review examined). None of the reviews validated the
classification accuracy of any dataset in any region, and none covered a
real two-scene Sentinel-2 run — see *Reading the output*. A real run on the bundled example AOI, with inputs,
versions, commands and outputs, is recorded in
[examples/run_record_example.md](examples/run_record_example.md).
Dataset coverage is global-ish, not universal — see *Limitations*.

## What it does

| Command | Source | Output |
|---|---|---|
| `slandu fetch` | — | resolves the tiles the AOI's bounding box touches and downloads them (`curl`); Sentinel-2 scene search; a scene tag is bound to one scene id |
| `slandu landcover` | ESA WorldCover 10 m (2021) | area per class, per zone (no coverage column) |
| `slandu forest` | Hansen GFC 30 m (2001–2025) | annual tree-cover loss per zone with `tiles_coverage_pct`, threshold sensitivity, ~1 km hotspot cells ranked by loss |
| `slandu water` | JRC GSW v1.5 30 m (1984–2024) | transition classes per zone with `tiles_coverage_pct` (every class row kept, zeros included); connected water area around a seed point (single tile, no coverage column) |
| `slandu change` | Sentinel-2 L2A | two-date bare-ground change per zone on one reference grid: `in_both_scenes_pct` (AOI inside both footprints), `common_valid_pct` (AOI valid on both dates), run manifest |

`forest`, `water` (transitions) and `change` sum every tile or scene that
intersects the AOI and report how much of the AOI was covered; `landcover` and
the seed-point water body do not carry a coverage figure. Lat/lon pixel areas
use the exact spherical latitude-band formula (that is cell area, not
classification accuracy).

## Install

```bash
git clone https://github.com/ss-hd-jp/satellite-landuse-toolkit.git
cd satellite-landuse-toolkit
pip install -r requirements.txt
python tests/test_regression.py          # or: pip install -r requirements-dev.txt && python -m pytest tests -q
```

Python 3.10+, `rasterio`, `numpy`, `scipy`, `Pillow`, and the external
command **`curl`** on your PATH. No geopandas, no shapely. `pytest` is only
needed for the second form of the test command.

## Quickstart

```bash
python -m slandu fetch --bbox 138.55 36.95 138.75 37.10 --data-dir data/rasters --only hansen --download
python -m slandu forest --bbox 138.55 36.95 138.75 37.10 --data-dir data/rasters --out-dir out --hotspot-from 2016
```

`--aoi your_area.geojson` (EPSG:4326) instead of `--bbox` gives one row group
per feature for `landcover`, `forest`, `water` (transitions) and `change`;
`fetch` only uses the union bounding box, and the seed-point water body is one
region by construction. Full walk-through:
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
`slandu change` reprojects both scenes onto one reference grid whose window is
the AOI's densified envelope (not two bbox corners); decides the reflectance
scaling per scene and per band from its STAC sidecar and **stops when that
state cannot be confirmed** (no sidecar; no provider flag on a post-04.00
baseline; `false` with an unknown baseline) unless you state `--offset-a` /
`--offset-b` after checking the product — when the provider flag is present
it is followed, and a `raster:bands` offset that disagrees with it is recorded
in the manifest rather than applied; then checks the result against
SCL-water cells — a median NIR over ≥ 50 such cells outside −0.01…0.15 stops
the run with a request for verification (a quality trigger, not proof of what
was applied); keeps SCL classes 4/5/7 only; and compares only cells valid on
both dates. Read `in_both_scenes_pct` (AOI inside both footprints) before
`common_valid_pct`. It cannot remove residual haze, shadow, BRDF or seasonal
effects — one date pair is a candidate, not a finding.

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
  nearest neighbour; it does not aggregate every 10 m pixel. Cells outside
  either scene's footprint count as not covered: the run stops below
  `--min-coverage` (default 50 % of the AOI) and warns below 99 %.
- `change` needs the STAC sidecar that `fetch.download_scene` writes. Without
  it, or with metadata that does not settle the offset state, it stops until
  you state the correction mode per scene.
- Scene tags name files (`<tag>_B04.tif`, `<tag>_stac.json`): band names
  carry no underscore, a tag is bound to one scene id, and tags that differ
  only in letter case are refused (they are the same files on Windows/macOS).
- Hotspot cells are blocks of pixels on the lat/lon grid (~1 km at the
  equator); the CSV gives the true cell area rather than assuming 1 km².
- `tiles_coverage_pct` compares a tile-grid tally with an independent lat/lon
  rasterization; a very small zone can show a fraction of a percent of
  boundary effect without any tile missing.
- Tiles are downloaded whole (Sentinel-2 band ≈150 MB, Hansen `treecover2000`
  ≈140 MB). `/vsicurl` is deliberately unused.

## Citing

Cite the archived release and, separately, every upstream dataset you used.

- All versions (concept DOI): `10.5281/zenodo.22730573`
- v1.0.0 (this version): `10.5281/zenodo.22730574` — https://doi.org/10.5281/zenodo.22730574

Suzuki, K. (2026). *satellite-landuse-toolkit: land-use, forest-loss and
surface-water analysis from free satellite data* (v1.0.0). Zenodo.
https://doi.org/10.5281/zenodo.22730574 — machine-readable form in
[CITATION.cff](CITATION.cff).

## Licence

Code: [MIT](LICENSE). Downloaded datasets keep their own licences.
