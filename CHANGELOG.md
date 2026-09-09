# Changelog

## 1.0.0 — 2026-09 (release candidate)

First public release. Before tagging, an external pre-publication review of the
draft found the defects listed under *Fixed*; all are covered by `tests/`.

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

### Fixed (from the pre-publication review)
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
