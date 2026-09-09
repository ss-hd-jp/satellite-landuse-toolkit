"""Command line interface: python -m slandu <command>."""
from __future__ import annotations

import argparse
import os

from .geo_util import bbox_geom, load_zones, zones_bbox


def _aoi(args):
    """Return (zones, bbox). --aoi takes a GeoJSON path; --bbox takes 4 numbers."""
    if args.bbox:
        box = tuple(args.bbox)
        return [("aoi", bbox_geom(box))], box
    zones = load_zones(args.aoi, args.name_field)
    return zones, zones_bbox(zones)


def cmd_fetch(args):
    from .fetch import download, s2_search, urls_for
    _, box = _aoi(args)
    groups = urls_for(box)
    for name, pairs in groups.items():
        if args.only and name not in args.only:
            continue
        print(f"== {name}: {len(pairs)} file(s)")
        for _, url in pairs[:6]:
            print("   ", url)
        if len(pairs) > 6:
            print(f"    ... and {len(pairs) - 6} more")
        if args.download:
            failed = download(pairs, args.data_dir)
            if failed:
                print(f"   {len(failed)} download(s) FAILED: {failed}")
    if args.s2_search:
        print("== sentinel-2 candidates (least cloudy first; point query on the AOI centre)")
        for s in s2_search(box, args.s2_search[0], args.s2_search[1], args.s2_cloud):
            print(f"   {s['date']} cloud={s['cloud']:5.1f} {s['grid']} {s['id']} "
                  f"baseline={s['processing_baseline']} boa_offset_applied={s['boa_offset_applied']}")


def cmd_landcover(args):
    from .zonal import find_rasters, write_zone_table
    zones, _ = _aoi(args)
    rasters = find_rasters(args.data_dir, args.pattern)
    if not rasters:
        raise SystemExit(f"no rasters matching {args.pattern} in {args.data_dir}")
    write_zone_table(zones, rasters, os.path.join(args.out_dir, args.out_name),
                     class_set=args.classes)


def cmd_forest(args):
    from .forest import analyse
    zones, _ = _aoi(args)
    analyse(zones, args.data_dir, args.out_dir, threshold=args.threshold,
            last_year=args.last_year, hotspot_from=args.hotspot_from)


def cmd_water(args):
    from .water import transitions_by_zone, water_body
    zones, box = _aoi(args)
    transitions_by_zone(zones, args.data_dir, args.out_dir)
    if args.seed:
        water_body(args.seed[0], args.seed[1], box, args.data_dir, args.out_dir,
                   label=args.label)


def cmd_change(args):
    from .change import bare_change
    zones, box = _aoi(args)
    bare_change(args.s2_dir, args.tag_a, args.tag_b, box, args.out_dir,
                zones=None if args.bbox else zones, stride=args.stride,
                label=args.label, offset_mode=args.offset)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="slandu",
                                description="Land-use analysis from free satellite data")
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp, need_out=True):
        sp.add_argument("--aoi", help="GeoJSON of the area(s) of interest, EPSG:4326")
        sp.add_argument("--bbox", nargs=4, type=float,
                        metavar=("MINLON", "MINLAT", "MAXLON", "MAXLAT"))
        sp.add_argument("--name-field", default="name")
        sp.add_argument("--data-dir", default="data/rasters")
        if need_out:
            sp.add_argument("--out-dir", default="out")

    sp = sub.add_parser("fetch", help="resolve / download the rasters an AOI needs")
    common(sp, need_out=False)
    sp.add_argument("--download", action="store_true")
    sp.add_argument("--only", nargs="*", choices=["worldcover", "hansen", "jrc", "esri"])
    sp.add_argument("--s2-search", nargs=2, metavar=("START", "END"))
    sp.add_argument("--s2-cloud", type=float, default=20.0)
    sp.set_defaults(func=cmd_fetch)

    sp = sub.add_parser("landcover", help="zonal class areas from a categorical raster")
    common(sp)
    sp.add_argument("--pattern", default="ESA_WorldCover_*_Map.tif")
    sp.add_argument("--classes", default="worldcover",
                    choices=["worldcover", "jrc_transitions", "esri", "raw"])
    sp.add_argument("--out-name", default="landcover_by_zone.csv")
    sp.set_defaults(func=cmd_landcover)

    sp = sub.add_parser("forest", help="annual tree-cover loss by zone (Hansen GFC)")
    common(sp)
    sp.add_argument("--threshold", type=int, default=30, help="canopy %% in 2000")
    sp.add_argument("--last-year", type=int, help="truncate the period (default: data end)")
    sp.add_argument("--hotspot-from", type=int, help="e.g. 2016 for ~1 km hotspot cells")
    sp.set_defaults(func=cmd_forest)

    sp = sub.add_parser("water", help="surface-water transitions (JRC GSW)")
    common(sp)
    sp.add_argument("--seed", nargs=2, type=float, metavar=("LON", "LAT"),
                    help="seed point inside a lake to isolate its connected water area")
    sp.add_argument("--label", default="waterbody")
    sp.set_defaults(func=cmd_water)

    sp = sub.add_parser("change", help="two-date bare-ground change (Sentinel-2)")
    common(sp)
    sp.add_argument("--s2-dir", default="data/s2")
    sp.add_argument("--tag-a", required=True, help="earlier scene tag")
    sp.add_argument("--tag-b", required=True, help="later scene tag (defines the grid)")
    sp.add_argument("--stride", type=int, default=2, help="analysis cell = stride x 10 m")
    sp.add_argument("--offset", default="auto", choices=["auto", "applied", "apply"],
                    help="BOA offset handling (auto = sidecar + water sanity check)")
    sp.add_argument("--label", default="aoi")
    sp.set_defaults(func=cmd_change)
    return p


def main(argv=None) -> None:
    args = build_parser().parse_args(argv)
    if not getattr(args, "aoi", None) and not getattr(args, "bbox", None):
        raise SystemExit("give --aoi <file.geojson> or --bbox minlon minlat maxlon maxlat")
    args.func(args)


if __name__ == "__main__":
    main()
