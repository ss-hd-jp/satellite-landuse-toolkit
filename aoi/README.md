# Defining an area of interest

Two ways:

1. `--bbox MINLON MINLAT MAXLON MAXLAT` — quick, single zone.
2. `--aoi your_area.geojson` — one zone per feature, so you get a table broken
   down by district, catchment, protected area, or whatever you supply.

The GeoJSON must be in EPSG:4326 (plain longitude/latitude). Each feature should
carry a name in its properties; change which key is used with `--name-field`.

`example.geojson` is a placeholder bounding box, provided only so the commands in
the README run. Replace it with your own area.

Administrative boundaries are not bundled with this toolkit. Free sources include
geoBoundaries, GADM and OpenStreetMap — check the licence of the level you use,
and read the note in `docs/data_catalog.md` about levels of the same country
coming from different providers.
