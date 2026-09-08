# Changelog

## 1.0.0 — 2026-09-09

First public release.

- `slandu fetch` — resolve and download the tiles an AOI needs
  (ESA WorldCover, Hansen GFC, JRC GSW v1.5, Esri Annual LULC; Sentinel-2 scene
  search via the Earth Search STAC API)
- `slandu landcover` — zonal class areas for any categorical lat/lon raster
- `slandu forest` — annual tree-cover loss per zone, 1 km hotspot cells, and a
  canopy-threshold sensitivity table
- `slandu water` — JRC water-transition classes per zone, plus isolation of a
  single water body by seed point
- `slandu change` — two-date bare-ground change on a common valid mask, with
  connected-component clustering
- Exact spherical latitude-band area integration
- Tile-name resolution for 3-degree, 10-degree and MGRS-band tiling schemes
- `docs/data_catalog.md` and `docs/pitfalls.md`
