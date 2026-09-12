# Changelog

## 1.0.0 — 2026-09 (release candidate, not yet tagged)

First public release. Six external pre-publication reviews have been run on
the draft; the sixth (on `2b9db7b`) raised no further findings within its
scope. The defects the earlier ones found are listed under *Fixed*; 26
regression tests pass (`tests/test_regression.py` lists what each one checks —
the tests added for the second to fifth reviews fail against the commit each
review examined). `examples/run_record_example.md` ties a real run on the
bundled example AOI to its inputs, versions, commands and outputs; the fourth
review reproduced all six output CSVs byte-for-byte from the recorded inputs.

### Added
- `slandu fetch` — resolve and download tiles (ESA WorldCover, Hansen GFC,
  JRC GSW v1.5, Esri Annual LULC v003 path); Sentinel-2 scene search with a
  STAC sidecar saved per scene
- `slandu landcover` — zonal class areas for categorical lat/lon rasters
- `slandu forest` — annual tree-cover loss per zone, tile coverage, canopy
  threshold sensitivity, ~1 km hotspot cells with their true cell area
- `slandu water` — JRC transition classes per zone; connected water area around a seed
- `slandu change` — two-date bare-ground change per zone on one reference grid,
  common valid mask, per-scene reflectance scaling with a water sanity check,
  run manifest
- `docs/data_catalog.md`, `docs/pitfalls.md`, Japanese versions, `tests/`

### Fixed (found in use, 2026-09-12)
- `water_body` read the occurrence and transitions tiles with windows computed
  independently per file; real tiles of the same name carry origins that
  differ by ~1e-13 degrees (observed on `140E_50N`: 140.00000000000023 vs
  140.0), so the windows differed by one pixel and the run crashed (or, with
  the opposite sign, silently misaligned). Transitions are now read onto the
  occurrence window's grid

### Fixed (fifth review, 2026-09-12)
- `download_scene` compared tags case-sensitively while the filesystem may
  not: on Windows, fetching a scene under `early` when `Early_*` existed found
  no files of its own, skipped the (identical) old images and wrote the new
  sidecar next to them — with or without `overwrite`. Tags that differ only
  in letter case from an existing tag are now refused on every platform
  (`fetch.tags_present`)

### Fixed (fourth review, 2026-09-12)
- `download_scene` matched a tag's files by prefix (`<tag>_*.tif`), so tag
  `early` also matched `early_wet_B04.tif`: a new tag that is a prefix of an
  existing one was refused, and `overwrite=True` deleted the other tag's
  bands. Now files are split into tag and band on the last underscore and the
  tag must match exactly (`fetch.tag_files`)

### Fixed (third review, 2026-09-12)
- `download_scene` only checked the bands requested in the current call, so
  fetching an additional band (e.g. B03) for a tag that already held another
  scene's B04/B08/SCL passed the identity check and left old images with new
  metadata; and `overwrite=True` with a band subset left the other bands of
  the previous scene in place. Now every `<tag>_*.tif` is checked against the
  tag's sidecar (files without a sidecar are refused too), and overwrite
  removes all of them
- `change` wrote the clusters CSV only when at least one connected component
  existed, so a re-run with the same label that found no change kept the
  previous run's clusters next to a summary saying 0 ha. Now the CSV is
  rewritten on every run (header only when empty)
- README (EN/JA): "contradictory metadata stops the run" corrected to the
  implemented policy — the provider flag is followed and a disagreeing
  `raster:bands` offset is recorded in the manifest, not applied

### Fixed (second review, 2026-09-09)
- `change` assumed "offset already applied" when the correction state could
  not be determined (no sidecar; no provider flag on a post-04.00 baseline),
  which turned an unchanged pair into 100 % new bare ground; now the run stops
  unless the state is confirmed by the flag, by a pre-04.00 baseline, or by a
  per-scene `--offset-a` / `--offset-b`; scale/offset are kept per band and the
  decision with its evidence is written to the manifest
- `change` built the analysis window from two bbox corners, clipping a lat/lon
  rectangle that is rotated in UTM (~2.3 % of the README AOI); now the window
  is the densified envelope (`transform_bounds`) snapped outward, and the
  polygon mask is applied afterwards
- `change` used the clipped window as the denominator of `zone_area_ha` and
  `common_valid_pct`; now cells outside either scene footprint are counted as
  not covered, `in_both_scenes_pct` is reported against the whole AOI, and the
  run stops below `--min-coverage`
- `water_sanity` prescribed a correction ("use --offset applied") from the sign
  of the median alone; now it asks for verification and names possible causes
- hotspots were sorted by cell area, not loss; now by unrounded loss area
- `download_scene` overwrote the sidecar before downloading and `download`
  skipped existing images, so re-using a tag for another scene left old images
  with new metadata; now a tag is bound to one scene id (stop or `overwrite=True`)
  and the sidecar is written last, only after every band downloaded
- `expected_zone_area_ha` rasterized the whole AOI at once (6.4 GB for
  20° × 10°); now strip-wise
- `water_transitions.csv` dropped zones with no water; now every class row is
  kept (zeros included) plus a per-zone TOTAL row
- tests: synthetic scenes are now rendered from a ground-defined pattern per
  grid, with negative controls (a geometry-ignoring reader and a two-corner
  window must fail); added stale-offset, mixed-encoding, unknown/ambiguous
  metadata, water-check, partial coverage, hotspot ordering, download failure
  and tag re-use cases
- docs: reflectance wording no longer treats a negative estimate as proof of a
  double-applied offset; JA catalog synced (licences/credits, cropland
  wording, JRC offset "usually sub-pixel, can reach or exceed one pixel");
  README claims about coverage and per-feature output made per command;
  `requirements-dev.txt` for pytest

### Fixed (first review)
- forest/water summed only the first tile found; now every intersecting tile is
  summed and coverage is reported
- forest period end was taken from the last observed loss year; now from the
  dataset version, so zero years are kept and the axis is comparable
- JRC tile names were zero-padded (404 for lon < 100 or lat < 10); now `0E_10N`
- Sentinel-2 dates were compared by array index without co-registration; now
  reprojected onto one reference grid
- Sentinel-2 reflectance was scaled uniformly; now per-scene from the sidecar
  with an empirical water-pixel check
- `change --aoi` silently used the bounding box; now the polygons
- hotspots included loss outside the AOI and assumed 1 km² cells; now masked,
  with real cell area
- zone ids were uint8 (255 max); now uint16
- empty zones reported total 1 ha / 100 %; now 0 / blank
- failed or truncated downloads were cached as successes; now `curl -f` to a
  `.part` file, kept only on success
- `revegetated_ha` renamed `no_longer_bare_ha`
- Esri tiles resolved from two corner points; now every zone × band the AOI spans
