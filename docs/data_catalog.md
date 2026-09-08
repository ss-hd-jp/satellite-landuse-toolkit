# Data catalog — URLs, licences, citation strings, and the traps

Every source below is free and needs no account. Endpoints were verified in
August 2026. **Versions change: check for a newer release before you publish.**

---

## 1. ESA WorldCover 10 m (single-year land cover)

- URL: `https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/ESA_WorldCover_10m_2021_v200_{TILE}_Map.tif`
- Tiles are 3° × 3°, named after the **south-west corner** (`N00E120` = 0–3 °N, 120–123 °E).
- Classes: 10 tree cover / 20 shrubland / 30 grassland / 40 cropland / 50 built-up /
  60 bare / 70 snow-ice / 80 permanent water / 90 herbaceous wetland / 95 mangroves /
  100 moss-lichen.
- Licence: **CC BY 4.0**
- Cite: `© ESA WorldCover project 2021 / Contains modified Copernicus Sentinel data (2021) processed by ESA WorldCover consortium`
- **Traps**: global overall accuracy is 76.7 %. In landscapes with rotational or
  smallholder farming the `cropland` class is heavily under-detected and the area
  lands in grassland or tree cover instead. v100 (2020) and v200 (2021) use
  different algorithms — **do not read the difference between them as change**.

## 2. Hansen Global Forest Change (annual tree-cover loss)

- URL: `https://storage.googleapis.com/earthenginepartners-hansen/GFC-2025-v1.13/Hansen_GFC-2025-v1.13_{LAYER}_{TILE}.tif`
  (`LAYER` = `treecover2000` / `lossyear` / `datamask` / `gain`; `TILE` = `10N_120E`,
  10° tiles named after the **north-west corner**)
- Updated annually — confirm the current version string.
- `lossyear`: 0 = none, 1..N = 2001..(2000+N). `datamask`: 0 nodata / 1 land / 2 permanent water.
- Cite: `Hansen, M. C. et al. (2013) "High-Resolution Global Maps of 21st-Century Forest Cover Change." Science 342: 850-853.`
- **Traps**: loss is a *stand-replacement disturbance* of vegetation over 5 m and is
  **not netted against regrowth**, so `treecover2000 − loss` is not remaining
  forest. Plantations and tree crops count as canopy. Loss says nothing about
  legality or cause.

## 3. JRC Global Surface Water (1984–)

- **Current, v1.5 (1984–2024)**:
  `https://storage.googleapis.com/water-world/download2024/VER1-5/{PROD}/{PROD}_{LON}_{LAT}_v1_5_2024.tif`
  `PROD` = occurrence / change / seasonality / recurrence / transitions / extent.
  10° tiles named after the north-west corner, e.g. `120E_10N`.
- Previous, v1.4 (1984–2021):
  `https://storage.googleapis.com/global-surface-water/downloads2021/{PROD}/{PROD}_{LON}_{LAT}v1_4_2021.tif`
  — **note the different bucket and the different underscore placement.**
- Transition classes: 1 permanent / 2 new permanent / 3 lost permanent / 4 seasonal /
  5 new seasonal / 6 lost seasonal / 7 seasonal→permanent / 8 permanent→seasonal /
  9 ephemeral permanent / 10 ephemeral seasonal.
- Cite: `Pekel, J-F. et al. (2016) High-resolution mapping of global surface water and its long-term changes. Nature 540: 418-422.`
- **Traps**: the yearly classification is **not** in this distribution path (404;
  it exists only inside Earth Engine). `new permanent water` lumps ponds,
  reservoirs, channel migration and tidal effects together — look at imagery
  before you name it. Differences between v1.4 and v1.5 include algorithm
  changes, so **never quote the version-to-version delta as "change since 2021"**.

## 4. Sentinel-2 L2A (10 m, for looking at the ground)

- Search: `POST https://earth-search.aws.element84.com/v1/search`, collection
  `sentinel-2-l2a`, with `intersects` + `datetime` + `query.eo:cloud_cover` + `sortby`.
- Assets are public COGs on `sentinel-cogs.s3.us-west-2.amazonaws.com`
  (B04/B08 ≈ 150 MB each, TCI ≈ 200 MB, SCL < 1 MB).
- Cite: **`Contains modified Copernicus Sentinel data [year].`**
  Do **not** append `processed by ESA` to your own analysis — that reads as if ESA
  produced your result.
- SCL classes: 3 cloud shadow / 4 vegetation / 5 not vegetated / 6 water /
  7 unclassified / 8 cloud medium / 9 cloud high / 10 thin cirrus / 11 snow.
- **Traps**:
  1. A low scene-level cloud percentage says nothing about *your* AOI. Mask always.
  2. Scenes from older processing baselines have sea-surface NIR near 0.06, so if
     you keep SCL class 6 the ocean is classified as bare ground.
  3. From 2022 the products carry a BOA offset — check
     `earthsearch:boa_offset_applied` in the STAC item before scaling DN/10000.

## 5. Esri 10 m Annual Land Cover (2017–2023)

- URL: `https://lulctimeseries.blob.core.windows.net/lulctimeseriesv003/lc{YEAR}/{TILE}_{YEAR}0101-{YEAR+1}0101.tif`
  (100–200 MB per file; 2024 onwards returns 404)
- **`TILE` = UTM zone number + MGRS latitude-band letter — not the N/S hemisphere.**
  Bands are 8° apart, lettered C…X with I and O skipped.
  Getting it wrong **does not 404**: a valid tile for another continent is returned
  with HTTP 200. Always confirm `ds.bounds` covers your AOI.
- Classes: 1 water / 2 trees / 4 flooded vegetation / 5 crops / 7 built area /
  8 bare ground / 9 snow-ice / 10 clouds / 11 rangeland.
- Cite: `Karra, K. et al. (2021) Global land use/land cover with Sentinel-2 and deep learning. IGARSS 2021. Esri / Impact Observatory / Microsoft`
- Data are in UTM: project your AOI before rasterizing.
- **Trap**: the tree ⇄ rangeland split is unstable between years (swings of tens of
  thousands of hectares are common). Use it for the direction of crops, built area
  and water; use Hansen for forest change.

## 6. Administrative boundaries (geoBoundaries)

- Metadata API: `https://www.geoboundaries.org/api/current/gbOpen/{ISO3}/{ADM1|ADM2}/`
  returns `gjDownloadURL` plus `boundarySource` and `boundaryLicense` **for that level**.
- **Source and licence differ per level.** A real example (IDN, 2026-08):
  ADM1 came from OpenStreetMap/Wambacher under ODbL 1.0, while ADM2 came from the
  national statistics office via WFP/OCHA under CC BY 3.0 IGO.
- Cite the product as `geoBoundaries gbOpen — Runfola, D. et al. (2020) PLoS ONE 15(4): e0231866` (CC BY 4.0), **plus** the upstream source for the level you used.
- **Trap**: because levels come from different providers, the national polygon does
  not equal the union of its subdivisions. Expect your totals to disagree by a
  fraction of a percent and say so in a footnote.

## 7. Protected areas (OpenStreetMap via Overpass)

- `POST https://overpass-api.de/api/interpreter` with
  `[out:json];(relation["boundary"="protected_area"](S,W,N,E);relation["boundary"="national_park"](...);way["boundary"="protected_area"](...););out geom;`
- Ways are single rings; relations must be assembled from outer/inner members.
- Licence ODbL 1.0. **These are not official designations** and carry no
  management category — never use them for a legal claim.

## 8. Watersheds (HydroBASINS / HydroRIVERS)

- `https://data.hydrosheds.org/file/hydrobasins/standard/hybas_{region}_lev{NN}_v1c.zip`
  (regions af / ar / as / au / eu / gr / na / sa / si; level 12 is ~37 MB per region)
- Useful attributes: `HYBAS_ID`, `NEXT_DOWN` (walk downstream), `MAIN_BAS`,
  `SUB_AREA`, `UP_AREA`, `COAST`.
- Readable with `pyshp`; geopandas is not required.
- Cite: `Lehner, B., Grill G. (2013) Hydrological Processes 27(15): 2171-2186. HydroSHEDS/WWF`
- **Trap**: even at level 12 the granularity is uneven — coastal strips merge many
  small catchments into a single basin of several hundred km². Always report the
  basin count and area alongside any "downstream" figure.

## 9. National forest-zoning layers

Ministry portals are frequently unreachable from outside the country. Before
giving up, check whether the layer is mirrored on an open data portal: as one
documented example, Indonesia's forest legal classification (Kawasan Hutan) is
downloadable as GeoJSON from Global Forest Watch Open Data even when the
ministry's own servers are not reachable. Such mirrors often ship the whole
country as one line-per-feature GeoJSON, which streams cheaply — filter by
bounding box while reading instead of loading it all.

**Trap**: mirrored copies rarely state the vintage of the source. Zoning is
revised by administrative decision, so mark the version as unverified unless you
confirm it locally.

## 10. National statistics

Statistical offices often block automated fetching (HTTP 403). Take the figures
from the press release itself and cite that URL; do not scrape.
Remember that harvested area is a **flow** (double cropping counts twice) and land
cover is a **stock** — the two are not directly comparable.
