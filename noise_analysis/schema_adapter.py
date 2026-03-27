import copy
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Tuple


DEFAULT_BUILDING_HEIGHT = float(os.getenv("NM5_DEFAULT_BUILDING_HEIGHT", "10"))
DEFAULT_FLOOR_HEIGHT = float(os.getenv("NM5_DEFAULT_FLOOR_HEIGHT", "3"))

DIRECT_HEIGHT_FIELDS = (
    "height",
    "HEIGHT",
    "building_height",
    "BUILDING_HEIGHT",
    "measured_height",
    "MEASURED_HEIGHT",
    "roof_height",
    "ROOF_HEIGHT",
    "roof_z",
    "ROOF_Z",
    "z",
    "Z",
)

FLOOR_COUNT_FIELDS = (
    "floors",
    "FLOORS",
    "storeys",
    "STOREYS",
    "stories",
    "STORIES",
    "levels",
    "LEVELS",
    "num_floors",
    "NUM_FLOORS",
    "floor_count",
    "FLOOR_COUNT",
)

ROAD_PERIOD_SUFFIXES = ("D", "E", "N")
ROAD_TYPE_RAILROAD = "railroad"
CAR_TRAFFIC_FACTOR = 0.11
TRUCK_TRAFFIC_FACTOR = 0.08


@dataclass
class PreparedNm5Inputs:
    buildings_path: Path
    roads_path: Path
    metadata: Dict[str, Any]


def _coerce_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_int(value: Any, default: int = 0) -> int:
    coerced = _coerce_float(value)
    if coerced is None:
        return default
    return int(coerced)


def _feature_collection(features):
    return {"type": "FeatureCollection", "features": features}


def _derive_building_height(properties: Mapping[str, Any]) -> Tuple[float, str]:
    for field_name in DIRECT_HEIGHT_FIELDS:
        height = _coerce_float(properties.get(field_name))
        if height is not None and height > 0:
            return height, field_name

    for field_name in FLOOR_COUNT_FIELDS:
        floor_count = _coerce_float(properties.get(field_name))
        if floor_count is not None and floor_count > 0:
            return floor_count * DEFAULT_FLOOR_HEIGHT, field_name

    return DEFAULT_BUILDING_HEIGHT, "default"


def adapt_buildings_geojson(buildings_geojson: Mapping[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    features = []
    used_default_height = 0

    for index, feature in enumerate(buildings_geojson.get("features", []), start=1):
        geometry = feature.get("geometry")
        if not geometry or geometry.get("type") not in {"Polygon", "MultiPolygon"}:
            continue

        height, height_source = _derive_building_height(feature.get("properties") or {})
        if height_source == "default":
            used_default_height += 1

        features.append(
            {
                "type": "Feature",
                "id": index,
                "geometry": geometry,
                "properties": {
                    "PK": index,
                    "HEIGHT": height,
                },
            }
        )

    metadata = {
        "total_source_features": len(buildings_geojson.get("features", [])),
        "exported_features": len(features),
        "used_default_height": used_default_height,
        "default_height": DEFAULT_BUILDING_HEIGHT,
        "default_floor_height": DEFAULT_FLOOR_HEIGHT,
    }

    return _feature_collection(features), metadata


def _apply_traffic_settings_to_roads(roads_geojson: Mapping[str, Any], traffic_settings: Mapping[str, Any]) -> Dict[str, Any]:
    adjusted_geojson = copy.deepcopy(roads_geojson)
    max_speed = traffic_settings["max_speed"]
    traffic_quota = traffic_settings["traffic_quota"]

    for road in adjusted_geojson.get("features", []):
        properties = road.get("properties") or {}
        if properties.get("traffic_settings_adjustable"):
            properties["max_speed"] = max_speed
            properties["truck_traffic_daily"] = properties["truck_traffic_daily"] * traffic_quota
            properties["car_traffic_daily"] = properties["car_traffic_daily"] * traffic_quota

    return adjusted_geojson


def _build_nm5_road_properties(source_properties: Mapping[str, Any], pk: int) -> Optional[Dict[str, Any]]:
    if source_properties.get("road_type") == ROAD_TYPE_RAILROAD:
        return None

    max_speed = _coerce_int(source_properties.get("max_speed"))
    light_vehicle_count = int(_coerce_int(source_properties.get("car_traffic_daily")) * CAR_TRAFFIC_FACTOR)
    heavy_vehicle_count = int(_coerce_int(source_properties.get("truck_traffic_daily")) * TRUCK_TRAFFIC_FACTOR)
    pavement = source_properties.get("PVMT") or source_properties.get("pvmt") or "DEF"
    junction_distance = _coerce_float(source_properties.get("JUNC_DIST"))
    junction_type = _coerce_int(source_properties.get("JUNC_TYPE"))
    way = _coerce_int(source_properties.get("WAY"), default=3)
    slope = _coerce_float(source_properties.get("SLOPE"))

    nm5_properties = {
        "PK": pk,
        "IDSOURCE": pk,
        "PVMT": pavement,
        "JUNC_DIST": junction_distance if junction_distance is not None else 0.0,
        "JUNC_TYPE": junction_type,
        "WAY": way,
    }

    if slope is not None:
        nm5_properties["SLOPE"] = slope

    for period in ROAD_PERIOD_SUFFIXES:
        nm5_properties[f"LV_{period}"] = light_vehicle_count
        nm5_properties[f"MV_{period}"] = 0
        nm5_properties[f"HGV_{period}"] = heavy_vehicle_count
        nm5_properties[f"WAV_{period}"] = 0
        nm5_properties[f"WBV_{period}"] = 0
        nm5_properties[f"LV_SPD_{period}"] = max_speed
        nm5_properties[f"MV_SPD_{period}"] = max_speed
        nm5_properties[f"HGV_SPD_{period}"] = max_speed
        nm5_properties[f"WAV_SPD_{period}"] = max_speed
        nm5_properties[f"WBV_SPD_{period}"] = max_speed

    return nm5_properties


def adapt_roads_geojson(roads_geojson: Mapping[str, Any], traffic_settings: Mapping[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    features = []
    skipped_rail_features = 0
    adjusted_roads = _apply_traffic_settings_to_roads(roads_geojson, traffic_settings)

    for index, feature in enumerate(adjusted_roads.get("features", []), start=1):
        geometry = feature.get("geometry")
        if not geometry or geometry.get("type") not in {"LineString", "MultiLineString"}:
            continue

        nm5_properties = _build_nm5_road_properties(feature.get("properties") or {}, index)
        if nm5_properties is None:
            skipped_rail_features += 1
            continue

        features.append(
            {
                "type": "Feature",
                "id": index,
                "geometry": geometry,
                "properties": nm5_properties,
            }
        )

    metadata = {
        "total_source_features": len(adjusted_roads.get("features", [])),
        "exported_features": len(features),
        "skipped_rail_features": skipped_rail_features,
    }

    return _feature_collection(features), metadata


def write_geojson(path: Path, payload: Mapping[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as file_handle:
        json.dump(payload, file_handle)


def prepare_nm5_input_files(
    output_dir: Path,
    buildings_geojson: Mapping[str, Any],
    roads_geojson: Mapping[str, Any],
    traffic_settings: Mapping[str, Any],
) -> PreparedNm5Inputs:
    output_dir.mkdir(parents=True, exist_ok=True)

    buildings_payload, buildings_metadata = adapt_buildings_geojson(buildings_geojson)
    roads_payload, roads_metadata = adapt_roads_geojson(roads_geojson, traffic_settings)

    buildings_path = output_dir / "buildings.geojson"
    roads_path = output_dir / "roads.geojson"
    metadata_path = output_dir / "metadata.json"

    write_geojson(buildings_path, buildings_payload)
    write_geojson(roads_path, roads_payload)
    write_geojson(
        metadata_path,
        {
            "buildings": buildings_metadata,
            "roads": roads_metadata,
        },
    )

    return PreparedNm5Inputs(
        buildings_path=buildings_path,
        roads_path=roads_path,
        metadata={
            "buildings": buildings_metadata,
            "roads": roads_metadata,
            "metadata_path": str(metadata_path),
        },
    )
