import copy
import csv
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

from noise_analysis.calculation_settings import TrafficSettings


DEFAULT_BUILDING_HEIGHT = float(os.getenv("NM5_DEFAULT_BUILDING_HEIGHT", "10"))
DEFAULT_FLOOR_HEIGHT = float(os.getenv("NM5_DEFAULT_FLOOR_HEIGHT", "3"))
DEFAULT_RAIL_TRACK_COUNT = int(os.getenv("NM5_DEFAULT_RAIL_TRACK_COUNT", "1"))
DEFAULT_RAIL_SPEED = float(os.getenv("NM5_DEFAULT_RAIL_SPEED", "80"))
DEFAULT_TRAINS_PER_HOUR = float(os.getenv("NM5_DEFAULT_TRAINS_PER_HOUR", "2"))
DEFAULT_RAIL_TRANSFER = os.getenv("NM5_DEFAULT_RAIL_TRANSFER", "SNCF4")
DEFAULT_RAIL_ROUGHNESS = os.getenv("NM5_DEFAULT_RAIL_ROUGHNESS", "SNCF1")
DEFAULT_RAIL_IMPACT = os.getenv("NM5_DEFAULT_RAIL_IMPACT", "")
DEFAULT_RAIL_CURVATURE = int(os.getenv("NM5_DEFAULT_RAIL_CURVATURE", "0"))
DEFAULT_RAIL_BRIDGE = os.getenv("NM5_DEFAULT_RAIL_BRIDGE", "")
DEFAULT_RAIL_TRACK_SPACING = float(os.getenv("NM5_DEFAULT_RAIL_TRACK_SPACING", "4"))
DEFAULT_RAIL_TRAIN_TYPE = os.getenv("NM5_DEFAULT_TRAIN_TYPE", "FRET")

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
RAIL_TRAFFIC_FIELDNAMES = (
    "IDTRAFFIC",
    "IDSECTION",
    "TRAINTYPE",
    "TRAINSPD",
    "TDAY",
    "TEVENING",
    "TNIGHT",
)
DIRECTIVITY_FIELDNAMES = (
    "DIR_ID",
    "THETA",
    "PHI",
    "HZ63",
    "HZ125",
    "HZ250",
    "HZ500",
    "HZ1000",
    "HZ2000",
    "HZ4000",
    "HZ8000",
)
ATMOSPHERIC_WINDROSE_FIELDNAMES = tuple(f"WINDROSE_{index}" for index in range(16))
ATMOSPHERIC_SETTINGS_FIELDNAMES = (
    "PERIOD",
    "TEMPERATURE",
    "PRESSURE",
    "HUMIDITY",
    "GDISC",
    "PRIME2520",
) + ATMOSPHERIC_WINDROSE_FIELDNAMES
DEFAULT_ATMOSPHERIC_PRESSURE = float(os.getenv("NM5_DEFAULT_ATMOSPHERIC_PRESSURE", "101325"))


@dataclass
class PreparedNm5Inputs:
    project_area_path: Optional[Path]
    buildings_path: Path
    roads_path: Optional[Path]
    rail_sections_path: Optional[Path]
    rail_traffic_path: Optional[Path]
    dem_path: Optional[Path]
    ground_absorption_path: Optional[Path]
    source_directivity_path: Optional[Path]
    atmospheric_settings_path: Optional[Path]
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


def _coerce_bool(value: Any, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)

    normalized_value = str(value).strip().lower()
    if normalized_value in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized_value in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _normalize_rail_code(value: Any, default: str = "", default_prefix: str = "SNCF") -> str:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return default

    normalized_value = str(value).strip()
    if not normalized_value:
        return default
    if normalized_value.isdigit():
        numeric_value = int(normalized_value)
        if numeric_value <= 0:
            return default
        return f"{default_prefix}{numeric_value}"

    return normalized_value


def _feature_collection(features):
    return {"type": "FeatureCollection", "features": features}


def _coordinate_dimension(coordinates: Any) -> int:
    if not isinstance(coordinates, list) or not coordinates:
        return 0
    if isinstance(coordinates[0], (int, float)):
        return len(coordinates)
    return _coordinate_dimension(coordinates[0])


def _geometry_has_z(geometry: Mapping[str, Any]) -> bool:
    return _coordinate_dimension(geometry.get("coordinates")) >= 3


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


def adapt_dem_geojson(dem_geojson: Mapping[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    features = []
    skipped_non_point_features = 0
    skipped_non_3d_features = 0

    for source_feature in dem_geojson.get("features", []):
        geometry = source_feature.get("geometry")
        if not geometry or geometry.get("type") not in {"Point", "MultiPoint"}:
            skipped_non_point_features += 1
            continue
        if not _geometry_has_z(geometry):
            skipped_non_3d_features += 1
            continue

        feature_id = len(features) + 1
        properties = dict(source_feature.get("properties") or {})
        properties.setdefault("PK", feature_id)
        features.append(
            {
                "type": "Feature",
                "id": feature_id,
                "geometry": geometry,
                "properties": properties,
            }
        )

    metadata = {
        "total_source_features": len(dem_geojson.get("features", [])),
        "exported_features": len(features),
        "skipped_non_point_features": skipped_non_point_features,
        "skipped_non_3d_features": skipped_non_3d_features,
    }

    return _feature_collection(features), metadata


def adapt_project_area_geojson(project_area_geojson: Mapping[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    features = []
    skipped_non_polygon_features = 0

    for source_feature in project_area_geojson.get("features", []):
        geometry = source_feature.get("geometry")
        if not geometry or geometry.get("type") not in {"Polygon", "MultiPolygon"}:
            skipped_non_polygon_features += 1
            continue

        feature_id = len(features) + 1
        features.append(
            {
                "type": "Feature",
                "id": feature_id,
                "geometry": geometry,
                "properties": {
                    "PK": feature_id,
                },
            }
        )

    metadata = {
        "total_source_features": len(project_area_geojson.get("features", [])),
        "exported_features": len(features),
        "skipped_non_polygon_features": skipped_non_polygon_features,
    }

    return _feature_collection(features), metadata


def adapt_ground_absorption_geojson(ground_geojson: Mapping[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    features = []
    skipped_non_polygon_features = 0
    skipped_missing_g = 0

    for source_feature in ground_geojson.get("features", []):
        geometry = source_feature.get("geometry")
        if not geometry or geometry.get("type") not in {"Polygon", "MultiPolygon"}:
            skipped_non_polygon_features += 1
            continue

        source_properties = source_feature.get("properties") or {}
        absorption = _coerce_float(source_properties.get("G") if "G" in source_properties else source_properties.get("g"))
        if absorption is None:
            skipped_missing_g += 1
            continue

        absorption = max(0.0, min(1.0, absorption))
        feature_id = len(features) + 1
        features.append(
            {
                "type": "Feature",
                "id": feature_id,
                "geometry": geometry,
                "properties": {
                    "PK": feature_id,
                    "G": absorption,
                },
            }
        )

    metadata = {
        "total_source_features": len(ground_geojson.get("features", [])),
        "exported_features": len(features),
        "skipped_non_polygon_features": skipped_non_polygon_features,
        "skipped_missing_g": skipped_missing_g,
    }

    return _feature_collection(features), metadata


def _lookup_case_insensitive(row: Mapping[str, Any], field_name: str, default: Any = None) -> Any:
    if field_name in row:
        return row[field_name]
    lower_field_name = field_name.lower()
    for key, value in row.items():
        if str(key).lower() == lower_field_name:
            return value
    return default


def _extract_table_rows(payload: Any) -> List[Mapping[str, Any]]:
    if payload is None:
        return []

    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, Mapping)]

    if not isinstance(payload, Mapping):
        return []

    if isinstance(payload.get("rows"), list):
        return [row for row in payload["rows"] if isinstance(row, Mapping)]

    if payload.get("type") == "FeatureCollection":
        return [
            feature.get("properties") or {}
            for feature in payload.get("features", [])
            if isinstance(feature, Mapping)
        ]

    return [payload]


def adapt_directivity_table(payload: Any) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    rows = []
    skipped_incomplete_rows = 0

    for source_row in _extract_table_rows(payload):
        normalized_row: Dict[str, Any] = {}
        missing_field = False
        for field_name in DIRECTIVITY_FIELDNAMES:
            value = _lookup_case_insensitive(source_row, field_name)
            if value in (None, ""):
                missing_field = True
                break
            if field_name == "DIR_ID":
                normalized_row[field_name] = _coerce_int(value)
            else:
                coerced_value = _coerce_float(value)
                if coerced_value is None:
                    missing_field = True
                    break
                normalized_row[field_name] = coerced_value

        if missing_field:
            skipped_incomplete_rows += 1
            continue
        rows.append(normalized_row)

    metadata = {
        "total_source_rows": len(_extract_table_rows(payload)),
        "exported_rows": len(rows),
        "skipped_incomplete_rows": skipped_incomplete_rows,
    }

    return rows, metadata


def _parse_windrose(value: Any) -> Optional[List[float]]:
    if isinstance(value, list):
        values = value
    elif isinstance(value, str):
        normalized_value = value.strip().strip("[]")
        values = [item.strip() for item in normalized_value.split(",") if item.strip()]
    else:
        return None

    windrose = []
    for item in values:
        coerced_item = _coerce_float(item)
        if coerced_item is None:
            return None
        windrose.append(coerced_item)

    if len(windrose) != 16:
        return None

    return windrose


def _windrose_from_row(row: Mapping[str, Any]) -> Optional[List[float]]:
    windrose = _parse_windrose(_lookup_case_insensitive(row, "WINDROSE"))
    if windrose is not None:
        return windrose

    indexed_windrose = []
    for field_name in ATMOSPHERIC_WINDROSE_FIELDNAMES:
        value = _lookup_case_insensitive(row, field_name)
        coerced_value = _coerce_float(value)
        if coerced_value is None:
            return None
        indexed_windrose.append(coerced_value)

    return indexed_windrose


def adapt_atmospheric_settings_table(payload: Any) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    rows = []
    skipped_incomplete_rows = 0

    for source_row in _extract_table_rows(payload):
        period = _lookup_case_insensitive(source_row, "PERIOD")
        temperature = _coerce_float(_lookup_case_insensitive(source_row, "TEMPERATURE"))
        humidity = _coerce_float(_lookup_case_insensitive(source_row, "HUMIDITY"))
        pressure = _coerce_float(_lookup_case_insensitive(source_row, "PRESSURE", DEFAULT_ATMOSPHERIC_PRESSURE))
        windrose = _windrose_from_row(source_row)

        if period in (None, "") or temperature is None or humidity is None or pressure is None or windrose is None:
            skipped_incomplete_rows += 1
            continue

        normalized_row: Dict[str, Any] = {
            "PERIOD": str(period).upper(),
            "TEMPERATURE": temperature,
            "PRESSURE": pressure,
            "HUMIDITY": humidity,
            "GDISC": _coerce_bool(_lookup_case_insensitive(source_row, "GDISC", True), default=True),
            "PRIME2520": _coerce_bool(_lookup_case_insensitive(source_row, "PRIME2520", False), default=False),
        }
        for index, value in enumerate(windrose):
            normalized_row[f"WINDROSE_{index}"] = value
        rows.append(normalized_row)

    metadata = {
        "total_source_rows": len(_extract_table_rows(payload)),
        "exported_rows": len(rows),
        "skipped_incomplete_rows": skipped_incomplete_rows,
    }

    return rows, metadata


def _apply_traffic_settings_to_roads(
    roads_geojson: Mapping[str, Any],
    traffic_settings: TrafficSettings,
) -> Dict[str, Any]:
    adjusted_geojson = copy.deepcopy(roads_geojson)
    max_speed = traffic_settings.max_speed
    traffic_quota = traffic_settings.traffic_quota

    for road in adjusted_geojson.get("features", []):
        properties = road.get("properties") or {}
        if properties.get("traffic_settings_adjustable"):
            properties["max_speed"] = max_speed
            properties["truck_traffic_daily"] = properties["truck_traffic_daily"] * traffic_quota
            properties["car_traffic_daily"] = properties["car_traffic_daily"] * traffic_quota

    return adjusted_geojson


def _build_nm5_road_properties(source_properties: Mapping[str, Any], pk: int) -> Dict[str, Any]:
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


def _rail_track_count(source_properties: Mapping[str, Any]) -> int:
    for field_name in ("NTRACK", "ntrack", "tracks", "TRACKS"):
        track_count = _coerce_int(source_properties.get(field_name))
        if track_count > 0:
            return track_count
    return DEFAULT_RAIL_TRACK_COUNT


def _rail_speed(source_properties: Mapping[str, Any]) -> float:
    for field_name in ("TRACKSPD", "track_speed", "train_speed", "TRAINSPD", "max_speed"):
        speed = _coerce_float(source_properties.get(field_name))
        if speed is not None and speed > 0:
            return speed
    return DEFAULT_RAIL_SPEED


def _rail_trains_per_hour(source_properties: Mapping[str, Any]) -> float:
    for field_name in ("trains_per_hour", "TRAINS_PER_HOUR", "TDAY", "tday"):
        trains_per_hour = _coerce_float(source_properties.get(field_name))
        if trains_per_hour is not None and trains_per_hour > 0:
            return trains_per_hour
    return DEFAULT_TRAINS_PER_HOUR


def _rail_bridge(source_properties: Mapping[str, Any]) -> str:
    for field_name in ("BRIDGE", "bridge_type"):
        bridge_code = _normalize_rail_code(source_properties.get(field_name), default=DEFAULT_RAIL_BRIDGE)
        if bridge_code:
            return bridge_code
    return DEFAULT_RAIL_BRIDGE


def _rail_track_spacing(source_properties: Mapping[str, Any]) -> float:
    for field_name in ("TRACKSPC", "track_spacing", "trackspc"):
        track_spacing = _coerce_float(source_properties.get(field_name))
        if track_spacing is not None and track_spacing > 0:
            return track_spacing
    return DEFAULT_RAIL_TRACK_SPACING


def _rail_tunnel(source_properties: Mapping[str, Any]) -> int:
    if _coerce_bool(source_properties.get("ISTUNNEL")):
        return 1
    if _coerce_bool(source_properties.get("tunnel")):
        return 1
    return 0


def _build_nm5_rail_section_properties(source_properties: Mapping[str, Any], pk: int) -> Dict[str, Any]:
    track_speed = _rail_speed(source_properties)
    tunnel_flag = _rail_tunnel(source_properties)

    return {
        "PK": pk,
        "IDSECTION": pk,
        "NTRACK": _rail_track_count(source_properties),
        "TRACKSPD": track_speed,
        "TRANSFER": _normalize_rail_code(source_properties.get("TRANSFER"), default=DEFAULT_RAIL_TRANSFER),
        "ROUGHNESS": _normalize_rail_code(source_properties.get("ROUGHNESS"), default=DEFAULT_RAIL_ROUGHNESS),
        "IMPACT": _normalize_rail_code(source_properties.get("IMPACT"), default=DEFAULT_RAIL_IMPACT),
        "CURVATURE": _coerce_int(source_properties.get("CURVATURE"), default=DEFAULT_RAIL_CURVATURE),
        "BRIDGE": _rail_bridge(source_properties),
        "COMSPD": track_speed,
        "TRACKSPC": _rail_track_spacing(source_properties),
        "ISTUNNEL": tunnel_flag,
    }


def _build_nm5_rail_traffic_row(source_properties: Mapping[str, Any], pk: int) -> Dict[str, Any]:
    trains_per_hour = _rail_trains_per_hour(source_properties)
    train_speed = _rail_speed(source_properties)
    train_type = source_properties.get("TRAINTYPE") or source_properties.get("train_type") or DEFAULT_RAIL_TRAIN_TYPE

    return {
        "IDTRAFFIC": pk,
        "IDSECTION": pk,
        "TRAINTYPE": str(train_type),
        "TRAINSPD": train_speed,
        "TDAY": trains_per_hour,
        "TEVENING": trains_per_hour,
        "TNIGHT": trains_per_hour,
    }


def adapt_transport_geojson(
    roads_geojson: Mapping[str, Any],
    traffic_settings: TrafficSettings,
) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any], List[Dict[str, Any]], Dict[str, Any]]:
    road_features = []
    rail_section_features = []
    rail_traffic_rows: List[Dict[str, Any]] = []
    skipped_non_line_features = 0
    adjusted_roads = _apply_traffic_settings_to_roads(roads_geojson, traffic_settings)
    source_pk = 1
    rail_source_count = 0
    road_source_count = 0

    for feature in adjusted_roads.get("features", []):
        geometry = feature.get("geometry")
        if not geometry or geometry.get("type") not in {"LineString", "MultiLineString"}:
            skipped_non_line_features += 1
            continue

        source_properties = feature.get("properties") or {}
        if source_properties.get("road_type") == ROAD_TYPE_RAILROAD:
            rail_section_features.append(
                {
                    "type": "Feature",
                    "id": source_pk,
                    "geometry": geometry,
                    "properties": _build_nm5_rail_section_properties(source_properties, source_pk),
                }
            )
            rail_traffic_rows.append(_build_nm5_rail_traffic_row(source_properties, source_pk))
            rail_source_count += 1
        else:
            road_features.append(
                {
                    "type": "Feature",
                    "id": source_pk,
                    "geometry": geometry,
                    "properties": _build_nm5_road_properties(source_properties, source_pk),
                }
            )
            road_source_count += 1

        source_pk += 1

    road_metadata = {
        "total_source_features": len(adjusted_roads.get("features", [])),
        "exported_features": len(road_features),
        "skipped_rail_features": rail_source_count,
        "skipped_non_line_features": skipped_non_line_features,
    }
    rail_metadata = {
        "total_source_features": len(adjusted_roads.get("features", [])),
        "exported_sections": len(rail_section_features),
        "exported_traffic_rows": len(rail_traffic_rows),
        "default_train_type": DEFAULT_RAIL_TRAIN_TYPE,
        "default_track_count": DEFAULT_RAIL_TRACK_COUNT,
        "default_track_speed": DEFAULT_RAIL_SPEED,
        "default_track_spacing": DEFAULT_RAIL_TRACK_SPACING,
        "default_trains_per_hour": DEFAULT_TRAINS_PER_HOUR,
        "exported_road_features": road_source_count,
    }

    return (
        _feature_collection(road_features),
        road_metadata,
        _feature_collection(rail_section_features),
        rail_traffic_rows,
        rail_metadata,
    )


def adapt_roads_geojson(
    roads_geojson: Mapping[str, Any],
    traffic_settings: TrafficSettings,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    road_payload, road_metadata, _, _, _ = adapt_transport_geojson(roads_geojson, traffic_settings)
    return road_payload, road_metadata


def write_geojson(path: Path, payload: Mapping[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as file_handle:
        json.dump(payload, file_handle)


def write_csv_rows(path: Path, fieldnames: Tuple[str, ...], rows: List[Dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as file_handle:
        writer = csv.DictWriter(file_handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def prepare_nm5_input_files(
    output_dir: Path,
    buildings_geojson: Mapping[str, Any],
    roads_geojson: Mapping[str, Any],
    traffic_settings: TrafficSettings,
    project_area_geojson: Optional[Mapping[str, Any]] = None,
    dem_geojson: Optional[Mapping[str, Any]] = None,
    ground_absorption_geojson: Optional[Mapping[str, Any]] = None,
    source_directivity: Any = None,
    atmospheric_settings: Any = None,
    full_contract: bool = False,
) -> PreparedNm5Inputs:
    output_dir.mkdir(parents=True, exist_ok=True)

    project_area_payload = None
    project_area_metadata = {
        "total_source_features": 0,
        "exported_features": 0,
        "skipped_non_polygon_features": 0,
    }
    if project_area_geojson is not None:
        project_area_payload, project_area_metadata = adapt_project_area_geojson(project_area_geojson)

    buildings_payload, buildings_metadata = adapt_buildings_geojson(buildings_geojson)
    (
        roads_payload,
        roads_metadata,
        rail_sections_payload,
        rail_traffic_rows,
        rail_metadata,
    ) = adapt_transport_geojson(roads_geojson, traffic_settings)
    dem_payload = None
    dem_metadata = {
        "total_source_features": 0,
        "exported_features": 0,
        "skipped_non_point_features": 0,
        "skipped_non_3d_features": 0,
    }
    if dem_geojson is not None:
        dem_payload, dem_metadata = adapt_dem_geojson(dem_geojson)

    ground_absorption_payload = None
    ground_absorption_metadata = {
        "total_source_features": 0,
        "exported_features": 0,
        "skipped_non_polygon_features": 0,
        "skipped_missing_g": 0,
    }
    if ground_absorption_geojson is not None:
        ground_absorption_payload, ground_absorption_metadata = adapt_ground_absorption_geojson(
            ground_absorption_geojson
        )

    source_directivity_rows, source_directivity_metadata = adapt_directivity_table(source_directivity)
    atmospheric_settings_rows, atmospheric_settings_metadata = adapt_atmospheric_settings_table(
        atmospheric_settings
    )

    if full_contract:
        missing_layers = []
        if dem_metadata["exported_features"] == 0:
            missing_layers.append("dem.geojson")
        if ground_absorption_metadata["exported_features"] == 0:
            missing_layers.append("ground_absorption.geojson")
        if atmospheric_settings_metadata["exported_rows"] == 0:
            missing_layers.append("atmospheric_settings.csv/json")
        if missing_layers:
            raise ValueError(
                "NM5 full mode requires richer input layers: %s" % ", ".join(missing_layers)
            )

    project_area_path = output_dir / "project_area.geojson" if project_area_metadata["exported_features"] else None
    buildings_path = output_dir / "buildings.geojson"
    roads_path = output_dir / "roads.geojson" if roads_metadata["exported_features"] else None
    rail_sections_path = output_dir / "rail_sections.geojson" if rail_metadata["exported_sections"] else None
    rail_traffic_path = output_dir / "rail_traffic.csv" if rail_traffic_rows else None
    dem_path = output_dir / "dem.geojson" if dem_metadata["exported_features"] else None
    ground_absorption_path = (
        output_dir / "ground_absorption.geojson"
        if ground_absorption_metadata["exported_features"]
        else None
    )
    source_directivity_path = (
        output_dir / "source_directivity.csv"
        if source_directivity_metadata["exported_rows"]
        else None
    )
    atmospheric_settings_path = (
        output_dir / "atmospheric_settings.csv"
        if atmospheric_settings_metadata["exported_rows"]
        else None
    )
    metadata_path = output_dir / "metadata.json"

    if project_area_path is not None and project_area_payload is not None:
        write_geojson(project_area_path, project_area_payload)
    write_geojson(buildings_path, buildings_payload)
    if roads_path is not None:
        write_geojson(roads_path, roads_payload)
    if rail_sections_path is not None:
        write_geojson(rail_sections_path, rail_sections_payload)
    if rail_traffic_path is not None:
        write_csv_rows(rail_traffic_path, RAIL_TRAFFIC_FIELDNAMES, rail_traffic_rows)
    if dem_path is not None and dem_payload is not None:
        write_geojson(dem_path, dem_payload)
    if ground_absorption_path is not None and ground_absorption_payload is not None:
        write_geojson(ground_absorption_path, ground_absorption_payload)
    if source_directivity_path is not None:
        write_csv_rows(source_directivity_path, DIRECTIVITY_FIELDNAMES, source_directivity_rows)
    if atmospheric_settings_path is not None:
        write_csv_rows(
            atmospheric_settings_path,
            ATMOSPHERIC_SETTINGS_FIELDNAMES,
            atmospheric_settings_rows,
        )

    write_geojson(
        metadata_path,
        {
            "project_area": project_area_metadata,
            "buildings": buildings_metadata,
            "roads": roads_metadata,
            "rail": rail_metadata,
            "dem": dem_metadata,
            "ground_absorption": ground_absorption_metadata,
            "source_directivity": source_directivity_metadata,
            "atmospheric_settings": atmospheric_settings_metadata,
        },
    )

    return PreparedNm5Inputs(
        project_area_path=project_area_path,
        buildings_path=buildings_path,
        roads_path=roads_path,
        rail_sections_path=rail_sections_path,
        rail_traffic_path=rail_traffic_path,
        dem_path=dem_path,
        ground_absorption_path=ground_absorption_path,
        source_directivity_path=source_directivity_path,
        atmospheric_settings_path=atmospheric_settings_path,
        metadata={
            "project_area": project_area_metadata,
            "buildings": buildings_metadata,
            "roads": roads_metadata,
            "rail": rail_metadata,
            "dem": dem_metadata,
            "ground_absorption": ground_absorption_metadata,
            "source_directivity": source_directivity_metadata,
            "atmospheric_settings": atmospheric_settings_metadata,
            "metadata_path": str(metadata_path),
        },
    )
