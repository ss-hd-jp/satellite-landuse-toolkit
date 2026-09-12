# Run record — bundled example AOI

A real run of `landcover`, `forest` and `water` on `aoi/example.geojson`, kept
so that inputs, versions, commands and outputs are tied together and anyone
can repeat it. The numbers are map-pixel tallies on the analysis grid (see
`docs/pitfalls.md` §11); they are recorded here for reproducibility, not as
findings about the area.

## Environment

- Run date: 2026-09-12
- Toolkit revision: the commit in which this file first appears
  (`git log --format=%H -- examples/run_record_example.md`)
- Windows 11, Python 3.13.13, rasterio 1.5.1, numpy 2.4.4, scipy 1.17.1, `curl`

## AOI

`aoi/example.geojson` — one feature named `example-aoi`, a lat/lon rectangle
138.55–138.75 °E, 36.95–37.10 °N (a placeholder box; see `aoi/README.md`).

## Inputs (as downloaded, with SHA-256)

Fetched with

```bash
python -m slandu fetch --aoi aoi/example.geojson --data-dir data/rasters --only hansen jrc worldcover --download
```

| File | Bytes | SHA-256 | Upstream `Last-Modified` |
|---|---:|---|---|
| `ESA_WorldCover_10m_2021_v200_N36E138_Map.tif` | 57,241,102 | `73cbc027db3397746990e9c95be3ae45e1b461a33add4a29a04252700add9115` | 2022-10-26 |
| `Hansen_GFC-2025-v1.13_treecover2000_40N_130E.tif` | 185,047,590 | `cd38e07ec4f4afa42bf2dc72e5d679776767fee1c814fa2cadc5dff65aa434f6` | 2026-03-19 |
| `Hansen_GFC-2025-v1.13_lossyear_40N_130E.tif` | 21,638,215 | `797570ece257968114d7bd79a57458fd3d1a1c5caf182d553e763cf1ea8e9eae` | 2026-03-16 |
| `Hansen_GFC-2025-v1.13_datamask_40N_130E.tif` | 22,512,140 | `b1cbd6c24e416ed0ba80a6241c1ceaa328549286aaac9776d64a38b1671f7290` | 2026-03-19 |
| `occurrence_130E_40N_v1_5_2024.tif` | 67,415,888 | `76aba6835acc3935bedc708deb5ac1a82fa36b7d324d6e392d302f9d5c0d1cfe` | 2026-06-19 |
| `transitions_130E_40N_v1_5_2024.tif` | 19,974,826 | `4472428fc4cb8e1777047b507c9fda8ba47e79360033604411200b1de0a50c28` | 2026-06-21 |

Dataset versions: ESA WorldCover 10 m 2021 v200; Hansen GFC-2025-v1.13
(2001–2025); JRC GSW v1.5 (1984–2024). Upstream files can be re-issued under
the same name — compare the hash before treating a re-run as identical.

## Commands and outputs

Output CSVs are copied verbatim in `examples/run_record_example/`.

### landcover

```bash
python -m slandu landcover --aoi aoi/example.geojson --data-dir data/rasters --out-dir out
```

| class | area_ha | share_pct |
|---|---:|---:|
| 10 tree cover | 21,404.9 | 72.28 |
| 30 grassland | 1,369.2 | 4.62 |
| 40 cropland | 5,306.7 | 17.92 |
| 50 built-up | 954.0 | 3.22 |
| 60 bare / sparse vegetation | 156.3 | 0.53 |
| 80 permanent water bodies | 423.1 | 1.43 |
| TOTAL | 29,614.1 | 100.0 |

Classes absent from the AOI (20, 70, 90, 95, 100) are not listed by this
command. No coverage column: WorldCover tiles are checked for presence, not
for their share of the AOI.

### forest

```bash
python -m slandu forest --aoi aoi/example.geojson --data-dir data/rasters --out-dir out --hotspot-from 2016
```

`forest_loss_summary.csv`:

| zone | tiles_coverage_pct | canopy_gt30pct_2000_ha | loss_2001_2025_ha | loss_pct_of_2000 | no_loss_detected_ha | annual_mean_first10_ha | annual_mean_last10_ha | data_version |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| example-aoi | 100.0 | 19,407.3 | 72.3 | 0.37 | 19,335.0 | 4.0 | 1.4 | GFC-2025-v1.13 |

`forest_loss_threshold_sensitivity.csv`: canopy 2000 / loss 2001–2025 =
20,484.6 / 74.6 ha at 10 %, 19,407.3 / 72.3 ha at 30 %, 18,425.0 / 67.3 ha at
50 % — loss share 0.36–0.37 % at every threshold.

`forest_loss_annual.csv` (ha): 2001 2.5 · 2002 5.1 · 2003 0.2 · 2004 4.0 ·
2005 13.0 · 2006 3.9 · 2007 3.6 · 2008 3.3 · 2009 0.8 · 2010 3.1 · 2011 7.0 ·
2012 5.2 · 2013 3.6 · 2014 3.0 · 2015 0.0 · 2016 2.2 · 2017 0.5 · 2018 2.2 ·
2019 0.8 · 2020 0.3 · 2021 0.7 · 2022 1.2 · 2023 0.8 · 2024 3.3 · 2025 2.0.

`forest_loss_hotspots_from2016.csv`: 25 cells, ranked by loss area; the
largest holds 3.8 ha of loss in an 80.0 ha cell (4.8 %). Edge cells have
smaller `cell_area_ha` (e.g. 53.4 ha) because the AOI boundary cuts the block.

`no_loss_detected_ha` is not remaining forest; the provider states that
definitive area estimates should not be made from loss-pixel counts.

### water

```bash
python -m slandu water --aoi aoi/example.geojson --data-dir data/rasters --out-dir out
```

`water_transitions.csv` (tiles_coverage_pct = 100.0 for every row):

| code | transition | area_ha |
|---|---|---:|
| 1 | permanent | 53.7 |
| 2 | new permanent | 149.6 |
| 3 | lost permanent | 28.5 |
| 4 | seasonal | 9.1 |
| 5 | new seasonal | 67.4 |
| 6 | lost seasonal | 15.2 |
| 7 | seasonal to permanent | 15.5 |
| 8 | permanent to seasonal | 12.2 |
| 9 | ephemeral permanent | 20.1 |
| 10 | ephemeral seasonal | 120.6 |
| TOTAL | sum of classes 1–10 | 491.9 |

"New permanent" lumps reservoirs, ponds, channel migration and similar; it is
not named here because no imagery was inspected for this record.

### change

Not part of this record: it needs two Sentinel-2 scenes chosen for the AOI
and their STAC sidecars, and the scene choice (date, cloud, footprint) is
itself an input that must be recorded per run — the run manifest
`<label>_change_manifest.json` does that (scene ids, scaling decision and
evidence, water check, grid, thresholds, `aoi_in_both_scenes_pct`).

## What this record does and does not show

It shows that the commands run end-to-end on real tiles, which files and
versions they read, and what they wrote. It does not validate the
classification accuracy of any dataset in this area, and the tallies are not
statistical area estimates.
