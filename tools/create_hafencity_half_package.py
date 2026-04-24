"""Create a smaller HafenCity CityPyo package from the prepared full package.

The generated package is intended for faster local NM5 debugging runs. It keeps
the same layer names as the full package, but uses the western half of the
project-area bounding box and filters features to that smaller AOI.
"""

from __future__ import annotations

import csv
import json
import shutil
import argparse
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parent.parent
SOURCE_PACKAGE = ROOT / "downloads" / "hafencity_full" / "citypyo" / "hafencity_full"
CITYPYO_ROOT = ROOT / "downloads" / "hafencity_full" / "citypyo"

GEOJSON_LAYERS = [
    "upperfloor.geojson",
    "roads.geojson",
    "dem.geojson",
    "ground_absorption.geojson",
    "traffic_counts_reference.geojson",
    "alkis_reference.geojson",
]


def load_geojson(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as file_handle:
        return json.load(file_handle)


def write_geojson(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")


def positions(coordinates: Any) -> Iterable[tuple[float, float]]:
    if (
        isinstance(coordinates, list)
        and len(coordinates) >= 2
        and isinstance(coordinates[0], (int, float))
        and isinstance(coordinates[1], (int, float))
    ):
        yield float(coordinates[0]), float(coordinates[1])
        return

    if isinstance(coordinates, list):
        for child in coordinates:
            yield from positions(child)


def feature_bounds(feature: dict[str, Any]) -> tuple[float, float, float, float] | None:
    geometry = feature.get("geometry") or {}
    coords = list(positions(geometry.get("coordinates")))
    if not coords:
        return None
    xs = [coord[0] for coord in coords]
    ys = [coord[1] for coord in coords]
    return min(xs), min(ys), max(xs), max(ys)


def bounds_intersect(
    left: tuple[float, float, float, float],
    right: tuple[float, float, float, float],
) -> bool:
    return not (
        left[2] < right[0]
        or left[0] > right[2]
        or left[3] < right[1]
        or left[1] > right[3]
    )


def collection_bounds(collection: dict[str, Any]) -> tuple[float, float, float, float]:
    all_bounds = [
        bounds
        for feature in collection.get("features", [])
        if (bounds := feature_bounds(feature)) is not None
    ]
    if not all_bounds:
        raise ValueError("GeoJSON collection has no usable feature coordinates")
    return (
        min(bounds[0] for bounds in all_bounds),
        min(bounds[1] for bounds in all_bounds),
        max(bounds[2] for bounds in all_bounds),
        max(bounds[3] for bounds in all_bounds),
    )


def half_project_area(
    full_project_area: dict[str, Any],
) -> tuple[dict[str, Any], tuple[float, float, float, float]]:
    minx, miny, maxx, maxy = collection_bounds(full_project_area)
    midx = (minx + maxx) / 2
    half_bounds = (minx, miny, midx, maxy)
    polygon = {
        "type": "Polygon",
        "coordinates": [
            [
                [minx, miny],
                [midx, miny],
                [midx, maxy],
                [minx, maxy],
                [minx, miny],
            ]
        ],
    }
    return (
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {
                        "name": "hafencity_half",
                        "source": "derived from hafencity_full/project_area.geojson",
                        "selection": "western half of full project-area bounding box",
                    },
                    "geometry": polygon,
                }
            ],
        },
        half_bounds,
    )


def filter_collection(
    collection: dict[str, Any],
    half_bounds: tuple[float, float, float, float],
) -> tuple[dict[str, Any], int, int]:
    source_features = collection.get("features", [])
    filtered_features = []
    for feature in source_features:
        bounds = feature_bounds(feature)
        if bounds is not None and bounds_intersect(bounds, half_bounds):
            filtered_features.append(feature)

    payload = {
        "type": "FeatureCollection",
        "features": filtered_features,
    }
    if "crs" in collection:
        payload["crs"] = collection["crs"]
    return payload, len(source_features), len(filtered_features)


def downsample_point_collection(
    collection: dict[str, Any],
    spacing_meters: int,
) -> tuple[dict[str, Any], int, int]:
    if spacing_meters <= 1:
        feature_count = len(collection.get("features", []))
        return collection, feature_count, feature_count

    features = collection.get("features", [])
    point_features = [
        feature
        for feature in features
        if (feature.get("geometry") or {}).get("type") == "Point"
    ]
    if not point_features:
        return collection, len(features), len(features)

    xs = []
    ys = []
    for feature in point_features:
        coordinates = (feature.get("geometry") or {}).get("coordinates") or []
        if len(coordinates) >= 2:
            xs.append(float(coordinates[0]))
            ys.append(float(coordinates[1]))

    origin_x = min(xs)
    origin_y = min(ys)
    selected_features = []
    for feature in point_features:
        coordinates = (feature.get("geometry") or {}).get("coordinates") or []
        x_coord = float(coordinates[0])
        y_coord = float(coordinates[1])
        x_offset = round(x_coord - origin_x)
        y_offset = round(y_coord - origin_y)
        if x_offset % spacing_meters == 0 and y_offset % spacing_meters == 0:
            selected_features.append(feature)

    payload = {
        "type": "FeatureCollection",
        "features": selected_features,
    }
    if "crs" in collection:
        payload["crs"] = collection["crs"]
    return payload, len(features), len(selected_features)


def copy_csv(source: Path, target: Path) -> int:
    with source.open(encoding="utf-8", newline="") as file_handle:
        row_count = sum(1 for _ in csv.DictReader(file_handle))
    shutil.copy2(source, target)
    return row_count


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a smaller HafenCity CityPyo package from the full package."
    )
    parser.add_argument(
        "--target-user",
        default="hafencity_half",
        help="Output CityPyo user folder name.",
    )
    parser.add_argument(
        "--dem-spacing",
        type=int,
        default=1,
        help="DEM point-grid spacing in meters. Use 1 to keep the original DGM1 grid.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    target_package = CITYPYO_ROOT / args.target_user
    if not SOURCE_PACKAGE.exists():
        raise FileNotFoundError(f"Missing source package: {SOURCE_PACKAGE}")

    target_package.mkdir(parents=True, exist_ok=True)
    project_area, half_bounds = half_project_area(
        load_geojson(SOURCE_PACKAGE / "project_area.geojson")
    )
    write_geojson(target_package / "project_area.geojson", project_area)

    summary: dict[str, Any] = {
        "source_package": str(SOURCE_PACKAGE.relative_to(ROOT)),
        "target_package": str(target_package.relative_to(ROOT)),
        "selection": "western half of full project-area bounding box",
        "dem_spacing_meters": args.dem_spacing,
        "half_bounds_epsg25832": {
            "minx": half_bounds[0],
            "miny": half_bounds[1],
            "maxx": half_bounds[2],
            "maxy": half_bounds[3],
        },
        "layers": {
            "project_area.geojson": {"source_features": 1, "exported_features": 1}
        },
    }

    for filename in GEOJSON_LAYERS:
        source_path = SOURCE_PACKAGE / filename
        if not source_path.exists():
            continue
        filtered, source_count, exported_count = filter_collection(
            load_geojson(source_path),
            half_bounds,
        )
        if filename == "dem.geojson":
            filtered, filtered_count, exported_count = downsample_point_collection(
                filtered,
                args.dem_spacing,
            )
            source_count = filtered_count
        write_geojson(target_package / filename, filtered)
        summary["layers"][filename] = {
            "source_features": source_count,
            "exported_features": exported_count,
        }

    atmospheric_rows = copy_csv(
        SOURCE_PACKAGE / "atmospheric_settings.csv",
        target_package / "atmospheric_settings.csv",
    )
    summary["layers"]["atmospheric_settings.csv"] = {
        "source_rows": atmospheric_rows,
        "exported_rows": atmospheric_rows,
    }

    sources_text = "\n".join(
        [
            "# HafenCity Half-Area NM5 Package",
            "",
            "This local CityPyo-style package is derived from",
            "`downloads/hafencity_full/citypyo/hafencity_full`.",
            "",
            "The AOI is the western half of the full HafenCity project-area",
            "bounding box in EPSG:25832. GeoJSON layers are filtered by feature",
            "bounding-box intersection with that AOI. Atmospheric settings are",
            "copied unchanged because they are period-wide model settings.",
            "",
            "Run with:",
            "",
            "- `CITY_PYO=downloads/hafencity_full/citypyo`",
            f"- `city_pyo_user={args.target_user}`",
            "- `NOISE_ENGINE=nm5_full`",
            "",
            f"DEM spacing in this package: `{args.dem_spacing} m`.",
            "",
            "Original data-source documentation remains in the full package",
            "`SOURCES.md` and `docs/hafencity_nm5_data_sources.md`.",
            "",
        ]
    )
    (target_package / "SOURCES.md").write_text(sources_text, encoding="utf-8")
    (target_package / "half_area_summary.json").write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
