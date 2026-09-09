# Data catalog — URLs, licences, citation strings, and the traps

Every source below is free and needs no account. Endpoints were verified in
September 2026. **Versions change: check for a newer release before you publish.**
Where a number below comes from our own runs it is marked *(observed)* with the
conditions; treat those as examples, not as constants.

---

## 1. ESA WorldCover 10 m (single-year land cover)

- URL: `https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/ESA_WorldCover_10m_2021_v200_{TILE}_Map.tif`
- Tiles are 3° × 3°, named after the **south-west corner** (`N00E120` = 0–3 °N, 120–123 °E).
- Classes: 10 tree cover / 20 shrubland / 30 grassland / 40 cropland / 50 built-up /
  60 bare / 70 snow-ice / 80 permanent water / 90 herbaceous wetland / 95 mangroves /
  100 moss-lichen.
- Licence: **CC BY 4.0**
- Map credit: `© ESA WorldCover project 2021 / Contains modified Copernicus Sentinel data (2021) processed by ESA WorldCover consortium`
- Dataset citation: Zanaga, D. et al. (2022) *ESA WorldCover 10 m 2021 v200*, doi:10.5281/zenodo.7254221
- **Traps**: the published global overall accuracy is 76.7 % — a global, all-class
  figure, not a per-region or per-class accuracy and not an area-error rate.
  Cropland under-detection can occur in rotational or smallholder landscapes;
  whether it does in *your* area needs local validation, and national
  harvested-area statistics are a different quantity (flow vs stock), not a
  validation. v100 (2020) and v200 (2021) use different algorithms —
  **do not read the difference between them as change**.

## 2. Hansen Global Forest Change (annual tree-cover loss)

- URL: `https://storage.googleapis.com/earthenginepartners-hansen/GFC-2025-v1.13/Hansen_GFC-2025-v1.13_{LAYER}_{TILE}.tif`
  (`LAYER` = `treecover2000` / `lossyear` / `datamask` / `gain`; `TILE` = `10N_120E`
  — zero-padded, 10° tiles named after the **north-west corner**)
- Coverage 80°N–60°S. Updated annually; the version string encodes the end year.
- `lossyear`: 0 = none, 1..N = 2001..(2000+N). `datamask`: 0 nodata / 1 land / 2 permanent water.
- Licence: **CC BY 4.0**
- Map credit: `Source: Hansen/UMD/Google/USGS/NASA`
- Citation: `Hansen, M. C. et al. (2013) "High-Resolution Global Maps of 21st-Century Forest Cover Change." Science 342: 850-853.`
- Provider usage notes (paraphrased): care must be taken comparing change across
  intervals because of sensor, data-availability and algorithm changes; and
  **"definitive area estimation should not be made using pixel counts from the
  forest loss layers"** — the maps can stratify a probability sample, but a
  pixel tally is not a statistical area estimate.
- **Traps**: loss is a *stand-replacement disturbance* of vegetation over 5 m and is
  **not netted against regrowth**, so `treecover2000 − loss` is not remaining
  forest. Plantations and tree crops count as canopy. Loss says nothing about
  legality or cause.

## 3. JRC Global Surface Water

- **Current, v1.5 (1984–2024)**:
  `https://storage.googleapis.com/water-world/download2024/VER1-5/{PROD}/{PROD}_{LON}_{LAT}_v1_5_2024.tif`
  `PROD` = occurrence / change / seasonality / recurrence / transitions / extent.
- **Tile names are NOT zero-padded**: `120E_10N`, `10E_10N`, `0E_10N`, `10W_10S`
  *(verified 2026-09: `000E_10N` and `010E_10N` → 404; `0E_10N` and `10E_10N` → 200)*.
  This differs from the Hansen convention.
- Previous, v1.4 (1984–2021):
  `https://storage.googleapis.com/global-surface-water/downloads2021/{PROD}/{PROD}_{LON}_{LAT}v1_4_2021.tif`
  — different bucket, different underscore placement.
- Yearly classification: not in the bucket paths above; the provider publishes
  `YearlyClassification` on its own server
  (`https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/GSWE/YearlyClassification/`),
  which this toolkit does not fetch.
- Transition classes: 1 permanent / 2 new permanent / 3 lost permanent / 4 seasonal /
  5 new seasonal / 6 lost seasonal / 7 seasonal→permanent / 8 permanent→seasonal /
  9 ephemeral permanent / 10 ephemeral seasonal.
- Terms: produced under the Copernicus Programme, "free of charge, without restriction of use".
- Attribution: `Source: EC JRC/Google`
- Citation: `Pekel, J-F., Cottam, A., Gorelick, N., Belward, A. S. (2016) High-resolution mapping of global surface water and its long-term changes. Nature 540: 418-422.`
- **Traps**: `new permanent water` lumps ponds, reservoirs, channel migration and
  tidal effects together — look at imagery before you name it. v1.5 combines
  Landsat Collection 1 (to 2021) with Collection 2 (2022–2024); the provider notes
  a residual co-registration offset that is usually sub-pixel but "can reach or
  exceed one 30 m pixel" in some path/rows, and reprocessed the 2016–2021
  seasonality layers. Differences between v1.4 and v1.5 include those changes,
  so **never quote the version-to-version delta as "change since 2021"**.
  Occurrence ≥ 5 % is *not* the provider's Maximum Water Extent layer.

## 4. Sentinel-2 L2A (10 m, for looking at the ground)

- Search: `POST https://earth-search.aws.element84.com/v1/search`, collection
  `sentinel-2-l2a`. This toolkit searches with a point at the AOI centre — check
  scene footprints yourself.
- Assets are public COGs on `sentinel-cogs.s3.us-west-2.amazonaws.com`
  (B04/B08 ≈ 150 MB each, TCI ≈ 200 MB, SCL < 1 MB).
- Cite: **`Contains modified Copernicus Sentinel data [year].`**
  Do **not** append `processed by ESA` to your own analysis.
- SCL classes: 3 cloud shadow / 4 vegetation / 5 not vegetated / 6 water /
  7 **unclassified** (not "clear") / 8 cloud medium / 9 cloud high / 10 thin cirrus / 11 snow.
- **Reflectance scaling — read this.** Since processing baseline 04.00
  (25 Jan 2022) L2A products carry a BOA add-offset (−1000 DN). The Earth Search
  provider states that the offset "has been applied to some of the Items" during
  COG conversion and tells users to check `raster:bands` scale/offset. In
  practice the item metadata can be contradictory *(observed 2026-09, tile 51NUA,
  baseline 05.11: `earthsearch:boa_offset_applied: true` **and**
  `raster:bands.offset: -0.1` on the same asset)*. Deciding from the pixels:
  water-class NIR had median DN 146 → 0.015 with plain `DN×1e-4`, and −0.085 if
  the −0.1 were applied again; vegetation NIR 0.277. So for that item the
  offset was already in the pixels and the `raster:bands` offset was stale.
  `slandu change` therefore (a) records the STAC item in a sidecar, (b) uses
  `earthsearch:boa_offset_applied` when present, and (c) checks the median NIR
  of SCL-water pixels and **refuses to run** if scaling yields negative water or
  implausibly bright water. Override with `--offset applied|apply` if you know
  better, and say which you used.
- **Traps**: a low scene-level cloud percentage says nothing about your AOI —
  mask always. Scenes from older baselines can have sea-surface NIR far above
  clear-water values *(observed: baseline 02.13 scene, water NIR median DN 613)*,
  so if you keep SCL class 6 the ocean can be classified as bare ground.

## 5. Esri 10 m Annual Land Cover

- URL: `https://lulctimeseries.blob.core.windows.net/lulctimeseriesv003/lc{YEAR}/{TILE}_{YEAR}0101-{YEAR+1}0101.tif`
  (100–200 MB per file). The **v003 path serves 2017–2023**; requests for 2024+ on
  that path return 404. Newer years may exist through other Esri channels — the
  404 is a statement about this path, not about the product.
- **`TILE` = UTM zone number + MGRS latitude-band letter — not the N/S hemisphere.**
  Bands are 8° apart, C…X with I and O skipped. Getting it wrong **does not 404**:
  a valid tile for another continent is returned with HTTP 200 *(observed:
  requesting `50S` for a site at 5 °S returned tiles for 32–40 °N)*.
  Always confirm `ds.bounds` covers your AOI. AOIs spanning several bands or
  zones need every combination (`geo_util.esri_tiles`).
- Classes: 1 water / 2 trees / 4 flooded vegetation / 5 crops / 7 built area /
  8 bare ground / 9 snow-ice / 10 clouds / 11 rangeland.
- Cite: `Karra, K. et al. (2021) Global land use/land cover with Sentinel-2 and deep learning. IGARSS 2021. Esri / Impact Observatory / Microsoft`
- Data are in UTM: project your AOI before rasterizing.
- **Trap**: the tree ⇄ rangeland split can be unstable between years *(observed
  in one province-scale run: year-to-year swings of tens of thousands of hectares
  in opposite directions)*. Prefer Hansen for forest change; use this product for
  the direction of crops, built area and water, and say so.

## 6. Administrative boundaries (geoBoundaries)

- Metadata API: `https://www.geoboundaries.org/api/current/gbOpen/{ISO3}/{ADM1|ADM2}/`
  returns `gjDownloadURL` plus `boundarySource` and `boundaryLicense` **for that level**.
- **Source and licence can differ per level.** A real example (IDN, 2026-08):
  ADM1 from OpenStreetMap/Wambacher under ODbL 1.0; ADM2 from the national
  statistics office via WFP/OCHA under CC BY 3.0 IGO.
- Cite the product as `geoBoundaries gbOpen — Runfola, D. et al. (2020) PLoS ONE 15(4): e0231866` (CC BY 4.0), **plus** the upstream source for the level you used.
- **Trap**: when levels come from different providers the national polygon need
  not equal the union of its subdivisions (it may also differ for other
  reasons — rasterization, coastline treatment, overlapping zones overwriting one
  another). Check the totals and footnote any difference.

## 7. Protected areas (OpenStreetMap via Overpass)

- `POST https://overpass-api.de/api/interpreter` with
  `[out:json];(relation["boundary"="protected_area"](S,W,N,E);relation["boundary"="national_park"](...);way["boundary"="protected_area"](...););out geom;`
- Ways are single rings; relations must be assembled from outer/inner members.
- Licence ODbL 1.0. **Not official designations**, no management category —
  never the basis of a legal claim.

## 8. Watersheds (HydroBASINS / HydroRIVERS)

- `https://data.hydrosheds.org/file/hydrobasins/standard/hybas_{region}_lev{NN}_v1c.zip`
  (regions af / ar / as / au / eu / gr / na / sa / si; level 12 ≈ 37 MB per region)
- Attributes: `HYBAS_ID`, `NEXT_DOWN`, `MAIN_BAS`, `SUB_AREA`, `UP_AREA`, `COAST`.
- Cite: `Lehner, B., Grill G. (2013) Hydrological Processes 27(15): 2171-2186. HydroSHEDS/WWF`
- **Trap**: granularity is uneven — coastal strips merge many small catchments
  into single basins of several hundred km². Report basin count and area with
  any "downstream" figure.

## 9. National forest-zoning layers

Ministry portals are frequently unreachable from outside the country. Check
open-data mirrors (e.g. Global Forest Watch Open Data) before giving up; such
mirrors often ship a whole country as one line-per-feature GeoJSON, which
streams cheaply. **Trap**: mirrored copies rarely state the source vintage;
zoning is revised administratively, so mark the version as unverified unless
confirmed locally.

## 10. National statistics

Statistical offices often block automated fetching. Use only figures you can
read in the original release, official PDF or statistical table — a search
snippet can be truncated, superseded or stripped of its footnotes. Remember
that harvested area is a **flow** (double cropping counts twice) and land cover
is a **stock**.
