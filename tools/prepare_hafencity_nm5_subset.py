"""Prepare local HafenCity input subsets for NM5 full-mode experiments.

This script intentionally avoids GDAL/geopandas so it can run in the current
developer environment. It produces AOI-scoped source subsets from files stored
under downloads/hafencity_full.
"""

from __future__ import annotations

import csv
import json
import math
import shutil
import sqlite3
import struct
import unicodedata
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "downloads" / "hafencity_full"
RAW = DATA / "raw"
EXTRACTED = DATA / "extracted"
SUBSET = DATA / "subset"
PROCESSED = DATA / "processed"
CITYPYO_PACKAGE = DATA / "citypyo" / "hafencity_full"
AOI_PATH = ROOT / "fixtures" / "citypyo" / "demo" / "project_area.geojson"
OSM_GPKG = EXTRACTED / "geofabrik_hamburg_latest_free_gpkg" / "hamburg.gpkg"
GTFS_DIR = EXTRACTED / "hvv_gtfs_20260408"

LON_LAT_AOI = AOI_PATH
LO_D2_FILES = [
    SUBSET / "lod2" / "LoD2_32_566_5932_1_HH.xml",
    SUBSET / "lod2" / "LoD2_32_566_5933_1_HH.xml",
    SUBSET / "lod2" / "LoD2_32_567_5932_1_HH.xml",
    SUBSET / "lod2" / "LoD2_32_567_5933_1_HH.xml",
]
DGM_TILE = SUBSET / "dgm1" / "DGM1_32566_5932_2_FHH.xyz"
ALKIS_ZIP = RAW / "alkis_liegenschaftskarte_2026-01-15.zip"
TRAFFIC_COUNTS = EXTRACTED / "verkehrsstaerken_geojson" / "de_hh_up_verkehrsstaerken_dtv_dtvw_EPSG_25832.json"
TRAFFIC_COUNT_YEAR = "2024"
TRAFFIC_ASSIGNMENT_MAX_DISTANCE_M = 40.0
GTFS_RAIL_ASSIGNMENT_MAX_DISTANCE_M = 90.0
GTFS_OPERATING_HOURS_PER_DAY = 18.0
GTFS_RAIL_ROUTE_TYPES = {"0", "1", "2", "109", "400", "401", "402", "403", "405"}

CITYGML_NS = {
    "bldg": "http://www.opengis.net/citygml/building/1.0",
    "gml": "http://www.opengis.net/gml",
}

MOTOR_ROAD_CLASSES = {
    "motorway",
    "motorway_link",
    "trunk",
    "trunk_link",
    "primary",
    "primary_link",
    "secondary",
    "secondary_link",
    "tertiary",
    "tertiary_link",
    "unclassified",
    "residential",
    "living_street",
    "service",
}

RAIL_CLASSES = {"rail", "light_rail", "subway", "tram"}

GROUND_G_BY_CLASS = {
    "allotments": 1.0,
    "cemetery": 0.8,
    "commercial": 0.15,
    "farmland": 1.0,
    "farmyard": 0.5,
    "forest": 1.0,
    "grass": 1.0,
    "heath": 1.0,
    "industrial": 0.05,
    "meadow": 1.0,
    "military": 0.2,
    "nature_reserve": 1.0,
    "orchard": 1.0,
    "park": 1.0,
    "quarry": 0.05,
    "recreation_ground": 0.9,
    "residential": 0.25,
    "retail": 0.05,
    "scrub": 1.0,
    "water": 0.0,
}

ALKIS_G_BY_FEATURE_TYPE = {
    "AX_Bahnverkehr": 0.0,
    "AX_FlaecheBesondererFunktionalerPraegung": 0.2,
    "AX_FlaecheGemischterNutzung": 0.25,
    "AX_Fliessgewaesser": 0.0,
    "AX_IndustrieUndGewerbeflaeche": 0.05,
    "AX_Platz": 0.0,
    "AX_Schiffsverkehr": 0.0,
    "AX_SportFreizeitUndErholungsflaeche": 0.9,
    "AX_Strassenverkehr": 0.0,
    "AX_UnlandVegetationsloseFlaeche": 0.7,
    "AX_Weg": 0.1,
    "AX_WegPfadSteig": 0.2,
    "AX_Wohnbauflaeche": 0.25,
}


def load_aoi_lonlat() -> list[tuple[float, float]]:
    with AOI_PATH.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    return [(float(lon), float(lat)) for lon, lat in payload["features"][0]["geometry"]["coordinates"][0]]


def latlon_to_utm32(lon: float, lat: float) -> tuple[float, float]:
    """WGS84 to UTM zone 32N.

    EPSG:25832 is ETRS89 / UTM zone 32N. For this local extraction the WGS84
    realization difference is below the precision needed to select km tiles.
    """

    semi_major = 6378137.0
    flattening = 1 / 298.257223563
    eccentricity_sq = flattening * (2 - flattening)
    second_ecc_sq = eccentricity_sq / (1 - eccentricity_sq)
    scale = 0.9996
    lon_origin = math.radians(9.0)
    lat_rad = math.radians(lat)
    lon_rad = math.radians(lon)

    sin_lat = math.sin(lat_rad)
    cos_lat = math.cos(lat_rad)
    tan_lat = math.tan(lat_rad)
    radius = semi_major / math.sqrt(1 - eccentricity_sq * sin_lat * sin_lat)
    t = tan_lat * tan_lat
    c = second_ecc_sq * cos_lat * cos_lat
    a_term = cos_lat * (lon_rad - lon_origin)

    meridian_arc = semi_major * (
        (1 - eccentricity_sq / 4 - 3 * eccentricity_sq**2 / 64 - 5 * eccentricity_sq**3 / 256) * lat_rad
        - (3 * eccentricity_sq / 8 + 3 * eccentricity_sq**2 / 32 + 45 * eccentricity_sq**3 / 1024)
        * math.sin(2 * lat_rad)
        + (15 * eccentricity_sq**2 / 256 + 45 * eccentricity_sq**3 / 1024) * math.sin(4 * lat_rad)
        - (35 * eccentricity_sq**3 / 3072) * math.sin(6 * lat_rad)
    )

    easting = scale * radius * (
        a_term
        + (1 - t + c) * a_term**3 / 6
        + (5 - 18 * t + t * t + 72 * c - 58 * second_ecc_sq) * a_term**5 / 120
    ) + 500000
    northing = scale * (
        meridian_arc
        + radius
        * tan_lat
        * (
            a_term**2 / 2
            + (5 - t + 9 * c + 4 * c * c) * a_term**4 / 24
            + (61 - 58 * t + t * t + 600 * c - 330 * second_ecc_sq) * a_term**6 / 720
        )
    )
    return easting, northing


def project_coords(coords: Any) -> Any:
    if not coords:
        return coords
    if isinstance(coords[0], (int, float)):
        return list(latlon_to_utm32(float(coords[0]), float(coords[1])))
    return [project_coords(item) for item in coords]


def bounds(points: Iterable[tuple[float, float]]) -> tuple[float, float, float, float]:
    materialized = list(points)
    xs = [point[0] for point in materialized]
    ys = [point[1] for point in materialized]
    return min(xs), min(ys), max(xs), max(ys)


def bbox_intersects(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> bool:
    return not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3])


def point_in_polygon(x: float, y: float, polygon: list[tuple[float, float]]) -> bool:
    inside = False
    j = len(polygon) - 1
    for i, point in enumerate(polygon):
        xi, yi = point
        xj, yj = polygon[j]
        if (yi > y) != (yj > y):
            x_cross = (xj - xi) * (y - yi) / (yj - yi) + xi
            if x < x_cross:
                inside = not inside
        j = i
    return inside


def geometry_points(coords: Any) -> Iterable[tuple[float, float]]:
    if not coords:
        return
    if isinstance(coords[0], (int, float)):
        yield float(coords[0]), float(coords[1])
        return
    for child in coords:
        yield from geometry_points(child)


def geometry_bbox(geometry: dict[str, Any]) -> tuple[float, float, float, float]:
    return bounds(geometry_points(geometry["coordinates"]))


def geometry_lines(geometry: dict[str, Any]) -> Iterable[list[list[float]]]:
    geometry_type = geometry.get("type")
    if geometry_type == "LineString":
        yield geometry["coordinates"]
    elif geometry_type == "MultiLineString":
        yield from geometry["coordinates"]
    elif geometry_type == "GeometryCollection":
        for item in geometry.get("geometries", []):
            yield from geometry_lines(item)


def point_segment_distance(
    point: tuple[float, float],
    start: list[float],
    end: list[float],
) -> float:
    px, py = point
    ax, ay = float(start[0]), float(start[1])
    bx, by = float(end[0]), float(end[1])
    dx = bx - ax
    dy = by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    ratio = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    ratio = max(0.0, min(1.0, ratio))
    closest_x = ax + ratio * dx
    closest_y = ay + ratio * dy
    return math.hypot(px - closest_x, py - closest_y)


def geometry_distance_to_point(geometry: dict[str, Any], point: tuple[float, float]) -> float:
    distances = []
    for line in geometry_lines(geometry):
        for start, end in zip(line, line[1:]):
            distances.append(point_segment_distance(point, start, end))
    return min(distances) if distances else math.inf


def geometry_distance(a: dict[str, Any], b: dict[str, Any]) -> float:
    distances = []
    for point in geometry_points(a.get("coordinates", [])):
        distances.append(geometry_distance_to_point(b, point))
    for point in geometry_points(b.get("coordinates", [])):
        distances.append(geometry_distance_to_point(a, point))
    return min(distances) if distances else math.inf


def coerce_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    normalized = unicodedata.normalize("NFKD", str(value))
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    return "".join(char.lower() for char in normalized if char.isalnum())


def local_text(element: ET.Element, local_name: str) -> str:
    for child in element.iter():
        if child.tag.split("}", 1)[-1] == local_name and child.text:
            return child.text.strip()
    return ""


def write_feature_collection(path: Path, features: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"type": "FeatureCollection", "features": features}
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, separators=(",", ":"))
        handle.write("\n")


def write_project_area(aoi_utm: list[tuple[float, float]]) -> None:
    path = PROCESSED / "project_area_25832.geojson"
    feature = {
        "type": "Feature",
        "properties": {"name": "hafencity_demo", "source": "fixtures/citypyo/demo/project_area.geojson"},
        "geometry": {"type": "Polygon", "coordinates": [[list(point) for point in aoi_utm]]},
    }
    write_feature_collection(path, [feature])


def parse_poslist(text: str) -> list[tuple[float, float, float]]:
    values = [float(value) for value in text.split()]
    if len(values) % 3 == 0:
        dimension = 3
    else:
        dimension = 2
    points = []
    for index in range(0, len(values), dimension):
        x = values[index]
        y = values[index + 1]
        z = values[index + 2] if dimension == 3 else 0.0
        points.append((x, y, z))
    return points


def ring_area_xy(points: list[tuple[float, float, float]]) -> float:
    if len(points) < 4:
        return 0.0
    area = 0.0
    for left, right in zip(points, points[1:]):
        area += left[0] * right[1] - right[0] * left[1]
    return abs(area) / 2.0


def building_height(building: ET.Element, fallback_points: list[tuple[float, float, float]]) -> float:
    measured = building.find("bldg:measuredHeight", CITYGML_NS)
    if measured is not None and measured.text:
        try:
            return float(measured.text)
        except ValueError:
            pass
    zs = [point[2] for point in fallback_points]
    if zs:
        return max(zs) - min(zs)
    return 10.0


def prepare_lod2_buildings(aoi_bbox: tuple[float, float, float, float]) -> int:
    features: list[dict[str, Any]] = []
    source_count = 0
    for citygml_path in LO_D2_FILES:
        tree = ET.parse(citygml_path)
        for building in tree.findall(".//bldg:Building", CITYGML_NS):
            source_count += 1
            ground_lists = building.findall(".//bldg:GroundSurface//gml:posList", CITYGML_NS)
            if not ground_lists:
                ground_lists = building.findall(".//gml:posList", CITYGML_NS)

            parsed_rings = [parse_poslist(item.text or "") for item in ground_lists if item.text]
            parsed_rings = [ring for ring in parsed_rings if ring_area_xy(ring) > 1.0]
            if not parsed_rings:
                continue

            all_points = [point for ring in parsed_rings for point in ring]
            building_bbox = bounds((point[0], point[1]) for point in all_points)
            if not bbox_intersects(building_bbox, aoi_bbox):
                continue

            if not any(aoi_bbox[0] <= point[0] <= aoi_bbox[2] and aoi_bbox[1] <= point[1] <= aoi_bbox[3] for point in all_points):
                continue

            height = building_height(building, all_points)
            polygons = []
            for ring in parsed_rings:
                coords = [[point[0], point[1]] for point in ring]
                if coords[0] != coords[-1]:
                    coords.append(coords[0])
                polygons.append([coords])

            geometry: dict[str, Any]
            if len(polygons) == 1:
                geometry = {"type": "Polygon", "coordinates": polygons[0]}
            else:
                geometry = {"type": "MultiPolygon", "coordinates": polygons}

            feature_id = len(features) + 1
            features.append(
                {
                    "type": "Feature",
                    "id": feature_id,
                    "properties": {
                        "PK": feature_id,
                        "HEIGHT": round(height, 3),
                        "source": "Hamburg LoD2-DE 2023 CityGML",
                        "source_file": citygml_path.name,
                        "source_id": building.attrib.get("{http://www.opengis.net/gml}id"),
                    },
                    "geometry": geometry,
                }
            )

    write_feature_collection(PROCESSED / "buildings_lod2_hafencity.geojson", features)
    return len(features)


def prepare_dem(aoi_utm: list[tuple[float, float]], aoi_bbox: tuple[float, float, float, float]) -> int:
    xyz_path = SUBSET / "dgm1" / "hafencity_dem_points.xyz"
    geojson_path = PROCESSED / "dem_hafencity.geojson"
    count = 0
    first_feature = True
    with DGM_TILE.open(encoding="utf-8") as source, xyz_path.open("w", encoding="utf-8", newline="\n") as xyz_out:
        with geojson_path.open("w", encoding="utf-8", newline="\n") as geojson_out:
            geojson_out.write('{"type":"FeatureCollection","features":[')
            for line in source:
                parts = line.split()
                if len(parts) < 3:
                    continue
                x = float(parts[0])
                y = float(parts[1])
                if x < aoi_bbox[0] or x > aoi_bbox[2] or y < aoi_bbox[1] or y > aoi_bbox[3]:
                    continue
                if not point_in_polygon(x, y, aoi_utm):
                    continue
                z = float(parts[2])
                count += 1
                xyz_out.write(f"{x:.3f} {y:.3f} {z:.3f}\n")
                if not first_feature:
                    geojson_out.write(",")
                first_feature = False
                feature = {
                    "type": "Feature",
                    "id": count,
                    "properties": {"PK": count},
                    "geometry": {"type": "Point", "coordinates": [x, y, z]},
                }
                json.dump(feature, geojson_out, separators=(",", ":"))
            geojson_out.write("]}\n")
    return count


def gpkg_wkb_offset(blob: bytes) -> int:
    flags = blob[3]
    envelope_code = (flags >> 1) & 0b111
    envelope_lengths = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}
    return 8 + envelope_lengths.get(envelope_code, 0)


def parse_wkb(blob: bytes, offset: int = 0) -> tuple[dict[str, Any], int]:
    byte_order = blob[offset]
    endian = "<" if byte_order == 1 else ">"
    geom_type = struct.unpack_from(endian + "I", blob, offset + 1)[0] % 1000
    cursor = offset + 5

    if geom_type == 1:
        x, y = struct.unpack_from(endian + "dd", blob, cursor)
        return {"type": "Point", "coordinates": [x, y]}, cursor + 16
    if geom_type == 2:
        count = struct.unpack_from(endian + "I", blob, cursor)[0]
        cursor += 4
        coords = []
        for _ in range(count):
            x, y = struct.unpack_from(endian + "dd", blob, cursor)
            cursor += 16
            coords.append([x, y])
        return {"type": "LineString", "coordinates": coords}, cursor
    if geom_type == 3:
        ring_count = struct.unpack_from(endian + "I", blob, cursor)[0]
        cursor += 4
        rings = []
        for _ in range(ring_count):
            point_count = struct.unpack_from(endian + "I", blob, cursor)[0]
            cursor += 4
            ring = []
            for _ in range(point_count):
                x, y = struct.unpack_from(endian + "dd", blob, cursor)
                cursor += 16
                ring.append([x, y])
            rings.append(ring)
        return {"type": "Polygon", "coordinates": rings}, cursor
    if geom_type in {4, 5, 6, 7}:
        count = struct.unpack_from(endian + "I", blob, cursor)[0]
        cursor += 4
        geometries = []
        for _ in range(count):
            geometry, cursor = parse_wkb(blob, cursor)
            geometries.append(geometry)
        if geom_type == 4:
            return {"type": "MultiPoint", "coordinates": [g["coordinates"] for g in geometries]}, cursor
        if geom_type == 5:
            return {"type": "MultiLineString", "coordinates": [g["coordinates"] for g in geometries]}, cursor
        if geom_type == 6:
            return {"type": "MultiPolygon", "coordinates": [g["coordinates"] for g in geometries]}, cursor
        return {"type": "GeometryCollection", "geometries": geometries}, cursor
    raise ValueError(f"Unsupported WKB geometry type: {geom_type}")


def read_gpkg_geometry(blob: bytes) -> dict[str, Any]:
    if not blob.startswith(b"GP"):
        raise ValueError("Not a GeoPackage geometry blob")
    geometry, _ = parse_wkb(blob, gpkg_wkb_offset(blob))
    return geometry


def transform_geometry_to_utm(geometry: dict[str, Any]) -> dict[str, Any]:
    if geometry["type"] == "GeometryCollection":
        return {"type": "GeometryCollection", "geometries": [transform_geometry_to_utm(item) for item in geometry["geometries"]]}
    return {"type": geometry["type"], "coordinates": project_coords(geometry["coordinates"])}


def class_speed(fclass: str) -> int:
    if fclass in {"motorway", "trunk"}:
        return 80
    if fclass in {"motorway_link", "trunk_link", "primary", "primary_link", "secondary", "secondary_link", "tertiary", "tertiary_link"}:
        return 50
    if fclass in {"living_street", "residential", "service"}:
        return 30
    return 50


def class_traffic(fclass: str) -> tuple[int, int]:
    if fclass in {"motorway", "trunk"}:
        return 25000, 2500
    if fclass in {"primary", "primary_link"}:
        return 12000, 900
    if fclass in {"secondary", "secondary_link", "tertiary", "tertiary_link"}:
        return 6000, 300
    if fclass in {"residential", "living_street", "service"}:
        return 1000, 50
    return 3000, 150


def traffic_count_values(feature: dict[str, Any]) -> tuple[int, int, str, float | None] | None:
    properties = feature.get("properties") or {}
    year = TRAFFIC_COUNT_YEAR
    total = coerce_float(properties.get(f"dtv_{year}")) or coerce_float(properties.get(f"dtvw_{year}"))
    if total is None or total <= 0:
        return None

    heavy_share = coerce_float(properties.get(f"sv_am_dtvw_{year}"))
    if heavy_share is None:
        for fallback_year in range(int(year) - 1, 2013, -1):
            heavy_share = coerce_float(properties.get(f"sv_am_dtvw_{fallback_year}"))
            if heavy_share is not None:
                break
    if heavy_share is None:
        heavy_share = 5.0

    heavy_traffic = max(0, int(round(total * heavy_share / 100.0)))
    light_traffic = max(0, int(round(total - heavy_traffic)))
    return light_traffic, heavy_traffic, year, heavy_share


def prepare_traffic_count_subset(aoi_bbox: tuple[float, float, float, float]) -> list[dict[str, Any]]:
    with TRAFFIC_COUNTS.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    features = []
    for feature in payload.get("features", []):
        geometry = feature.get("geometry") or {}
        coords = geometry.get("coordinates") or []
        if geometry.get("type") != "Point" or len(coords) < 2:
            continue
        x, y = float(coords[0]), float(coords[1])
        if aoi_bbox[0] <= x <= aoi_bbox[2] and aoi_bbox[1] <= y <= aoi_bbox[3]:
            features.append(feature)
    write_feature_collection(PROCESSED / "traffic_counts_hafencity.geojson", features)
    return features


def assign_traffic_counts_to_roads(
    transport_features: list[dict[str, Any]],
    traffic_features: list[dict[str, Any]],
) -> int:
    rows = []
    assigned = 0
    road_features = [
        feature
        for feature in transport_features
        if feature.get("properties", {}).get("road_type") == "road"
    ]

    for traffic_feature in traffic_features:
        traffic_values = traffic_count_values(traffic_feature)
        if traffic_values is None:
            continue
        point = tuple(float(value) for value in traffic_feature["geometry"]["coordinates"][:2])
        traffic_properties = traffic_feature.get("properties") or {}
        traffic_name = traffic_properties.get("bezeichnung", "")
        normalized_traffic_name = normalize_text(traffic_name)

        candidates = []
        for road_feature in road_features:
            road_properties = road_feature["properties"]
            road_name = road_properties.get("name") or ""
            distance = geometry_distance_to_point(road_feature["geometry"], point)
            name_bonus = 0.0
            normalized_road_name = normalize_text(road_name)
            if normalized_road_name and normalized_road_name in normalized_traffic_name:
                name_bonus = -15.0
            road_class = road_properties.get("fclass")
            class_penalty = 8.0 if road_class == "service" else 0.0
            candidates.append((distance + name_bonus + class_penalty, distance, road_feature))

        if not candidates:
            continue

        _score, distance, selected_road = min(candidates, key=lambda item: item[0])
        if distance > TRAFFIC_ASSIGNMENT_MAX_DISTANCE_M:
            continue

        light_traffic, heavy_traffic, year, heavy_share = traffic_values
        selected_properties = selected_road["properties"]
        selected_properties["car_traffic_daily"] = light_traffic
        selected_properties["truck_traffic_daily"] = heavy_traffic
        selected_properties["traffic_count_source"] = "Hamburg Verkehrsstärken"
        selected_properties["traffic_count_year"] = int(year)
        selected_properties["traffic_count_station"] = traffic_properties.get("zaehlstelle")
        selected_properties["traffic_count_name"] = traffic_name
        selected_properties["traffic_count_total_daily"] = light_traffic + heavy_traffic
        selected_properties["traffic_count_heavy_share_percent"] = round(heavy_share, 2)
        selected_properties["traffic_count_assignment_distance_m"] = round(distance, 2)
        assigned += 1
        rows.append(
            {
                "traffic_count_station": traffic_properties.get("zaehlstelle"),
                "traffic_count_name": traffic_name,
                "road_pk": selected_properties.get("PK"),
                "road_name": selected_properties.get("name"),
                "road_class": selected_properties.get("fclass"),
                "distance_m": round(distance, 2),
                "light_traffic_daily": light_traffic,
                "heavy_traffic_daily": heavy_traffic,
                "heavy_share_percent": round(heavy_share, 2),
            }
        )

    assignment_path = PROCESSED / "traffic_count_assignments_hafencity.csv"
    with assignment_path.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = [
            "traffic_count_station",
            "traffic_count_name",
            "road_pk",
            "road_name",
            "road_class",
            "distance_m",
            "light_traffic_daily",
            "heavy_traffic_daily",
            "heavy_share_percent",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return assigned


def gtfs_train_type(route_types: set[str]) -> str:
    if "402" in route_types or "109" in route_types:
        return "Z50000-7U1"
    if "2" in route_types:
        return "FLIRT-4U1"
    return "Z50000-7U1"


def gtfs_train_speed(route_types: set[str]) -> int:
    if "402" in route_types:
        return 60
    if "109" in route_types:
        return 80
    if "2" in route_types:
        return 100
    return 80


def prepare_gtfs_rail_shapes(aoi_lonlat_bbox: tuple[float, float, float, float]) -> list[dict[str, Any]]:
    routes_path = GTFS_DIR / "routes.txt"
    trips_path = GTFS_DIR / "trips.txt"
    calendar_path = GTFS_DIR / "calendar.txt"
    shapes_path = GTFS_DIR / "shapes.txt"
    if not all(path.exists() for path in [routes_path, trips_path, calendar_path, shapes_path]):
        write_feature_collection(PROCESSED / "gtfs_rail_shapes_hafencity.geojson", [])
        return []

    route_by_id: dict[str, dict[str, str]] = {}
    with routes_path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            route_type = str(row.get("route_type", ""))
            if route_type in GTFS_RAIL_ROUTE_TYPES:
                route_by_id[row["route_id"]] = row

    weekday_services = set()
    weekdays = ("monday", "tuesday", "wednesday", "thursday", "friday")
    with calendar_path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if any(row.get(day) == "1" for day in weekdays):
                weekday_services.add(row["service_id"])

    shape_info: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "weekday_trips": 0,
            "route_types": set(),
            "routes": set(),
        }
    )
    with trips_path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            route = route_by_id.get(row.get("route_id", ""))
            shape_id = row.get("shape_id")
            if not route or not shape_id or row.get("service_id") not in weekday_services:
                continue
            info = shape_info[shape_id]
            info["weekday_trips"] += 1
            info["route_types"].add(str(route.get("route_type", "")))
            route_name = route.get("route_short_name") or route.get("route_long_name") or row.get("route_id")
            if route_name:
                info["routes"].add(route_name)

    lon_buffer = 0.04
    lat_buffer = 0.03
    expanded_bbox = (
        aoi_lonlat_bbox[0] - lon_buffer,
        aoi_lonlat_bbox[1] - lat_buffer,
        aoi_lonlat_bbox[2] + lon_buffer,
        aoi_lonlat_bbox[3] + lat_buffer,
    )
    shape_points: dict[str, list[tuple[int, list[float]]]] = defaultdict(list)
    with shapes_path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            shape_id = row.get("shape_id")
            if shape_id not in shape_info:
                continue
            lat = coerce_float(row.get("shape_pt_lat"))
            lon = coerce_float(row.get("shape_pt_lon"))
            if lat is None or lon is None:
                continue
            if not (expanded_bbox[0] <= lon <= expanded_bbox[2] and expanded_bbox[1] <= lat <= expanded_bbox[3]):
                continue
            sequence = int(row.get("shape_pt_sequence") or len(shape_points[shape_id]))
            x, y = latlon_to_utm32(lon, lat)
            shape_points[shape_id].append((sequence, [x, y]))

    features = []
    for shape_id, sequence_points in sorted(shape_points.items()):
        if len(sequence_points) < 2:
            continue
        info = shape_info[shape_id]
        route_types = set(info["route_types"])
        coordinates = [point for _sequence, point in sorted(sequence_points)]
        weekday_trips = int(info["weekday_trips"])
        trains_per_hour = round(max(0.25, weekday_trips / GTFS_OPERATING_HOURS_PER_DAY), 2)
        feature_id = len(features) + 1
        features.append(
            {
                "type": "Feature",
                "id": feature_id,
                "properties": {
                    "PK": feature_id,
                    "shape_id": shape_id,
                    "routes": ";".join(sorted(info["routes"])),
                    "route_types": ";".join(sorted(route_types)),
                    "weekday_trips": weekday_trips,
                    "trains_per_hour": trains_per_hour,
                    "train_speed": gtfs_train_speed(route_types),
                    "TRAINTYPE": gtfs_train_type(route_types),
                    "source": "hvv GTFS 20260408",
                },
                "geometry": {"type": "LineString", "coordinates": coordinates},
            }
        )

    write_feature_collection(PROCESSED / "gtfs_rail_shapes_hafencity.geojson", features)
    return features


def assign_gtfs_to_rails(
    transport_features: list[dict[str, Any]],
    gtfs_shapes: list[dict[str, Any]],
) -> int:
    if not gtfs_shapes:
        return 0

    rows = []
    assigned = 0
    for rail_feature in transport_features:
        rail_properties = rail_feature.get("properties") or {}
        if rail_properties.get("road_type") != "railroad":
            continue

        candidates = []
        rail_class = rail_properties.get("fclass")
        for gtfs_shape in gtfs_shapes:
            gtfs_properties = gtfs_shape["properties"]
            route_types = set(str(gtfs_properties.get("route_types", "")).split(";"))
            distance = geometry_distance(rail_feature["geometry"], gtfs_shape["geometry"])
            compatible = not (
                (rail_class == "subway" and "402" not in route_types)
                or (rail_class != "subway" and "402" in route_types)
            )
            type_penalty = 0.0 if compatible else 75.0
            candidates.append((distance + type_penalty, distance, compatible, gtfs_shape))

        if not candidates:
            continue

        compatible_candidates = [
            (distance, gtfs_shape)
            for _score, distance, compatible, gtfs_shape in candidates
            if compatible and distance <= 25.0
        ]
        if not compatible_candidates:
            _score, distance, _compatible, selected_gtfs = min(candidates, key=lambda item: item[0])
            if distance > GTFS_RAIL_ASSIGNMENT_MAX_DISTANCE_M:
                continue
            compatible_candidates = [(distance, selected_gtfs)]

        nearest_distance = min(distance for distance, _gtfs_shape in compatible_candidates)
        if nearest_distance > GTFS_RAIL_ASSIGNMENT_MAX_DISTANCE_M:
            continue

        route_types: set[str] = set()
        routes: set[str] = set()
        shape_ids: list[str] = []
        weekday_trips = 0
        trains_per_hour = 0.0
        for _distance, gtfs_shape in compatible_candidates:
            gtfs_properties = gtfs_shape["properties"]
            shape_ids.append(str(gtfs_properties["shape_id"]))
            route_types.update(str(gtfs_properties.get("route_types", "")).split(";"))
            routes.update(route for route in str(gtfs_properties.get("routes", "")).split(";") if route)
            weekday_trips += int(gtfs_properties.get("weekday_trips") or 0)
            trains_per_hour += float(gtfs_properties.get("trains_per_hour") or 0.0)

        train_type = gtfs_train_type(route_types)
        train_speed = gtfs_train_speed(route_types)
        rail_properties["trains_per_hour"] = round(max(0.25, trains_per_hour), 2)
        rail_properties["train_speed"] = train_speed
        rail_properties["TRAINTYPE"] = train_type
        rail_properties["train_type"] = train_type
        rail_properties["gtfs_source"] = "hvv GTFS 20260408"
        rail_properties["gtfs_shape_id"] = ";".join(sorted(set(shape_ids)))
        rail_properties["gtfs_routes"] = ";".join(sorted(routes))
        rail_properties["gtfs_route_types"] = ";".join(sorted(route_type for route_type in route_types if route_type))
        rail_properties["gtfs_weekday_trips"] = weekday_trips
        rail_properties["gtfs_assignment_distance_m"] = round(nearest_distance, 2)
        assigned += 1
        rows.append(
            {
                "rail_pk": rail_properties.get("PK"),
                "rail_class": rail_properties.get("fclass"),
                "gtfs_shape_id": rail_properties["gtfs_shape_id"],
                "gtfs_routes": rail_properties["gtfs_routes"],
                "distance_m": round(nearest_distance, 2),
                "trains_per_hour": rail_properties["trains_per_hour"],
                "train_speed": rail_properties["train_speed"],
                "train_type": rail_properties["TRAINTYPE"],
            }
        )

    assignment_path = PROCESSED / "gtfs_rail_assignments_hafencity.csv"
    with assignment_path.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = [
            "rail_pk",
            "rail_class",
            "gtfs_shape_id",
            "gtfs_routes",
            "distance_m",
            "trains_per_hour",
            "train_speed",
            "train_type",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return assigned


def prepare_osm_transport_and_ground(
    aoi_lonlat_bbox: tuple[float, float, float, float],
    traffic_features: list[dict[str, Any]],
    gtfs_rail_shapes: list[dict[str, Any]],
) -> tuple[int, int, int, int, int]:
    transport_features: list[dict[str, Any]] = []
    ground_features: list[dict[str, Any]] = []

    with sqlite3.connect(OSM_GPKG) as connection:
        for row in connection.execute(
            "select geom, osm_id, fclass, name, maxspeed, oneway, bridge, tunnel from gis_osm_roads_free"
        ):
            geom_blob, osm_id, fclass, name, maxspeed, oneway, bridge, tunnel = row
            if fclass not in MOTOR_ROAD_CLASSES:
                continue
            geometry = read_gpkg_geometry(geom_blob)
            if not bbox_intersects(geometry_bbox(geometry), aoi_lonlat_bbox):
                continue
            speed = int(maxspeed) if isinstance(maxspeed, int) and maxspeed > 0 else class_speed(fclass)
            car_traffic, truck_traffic = class_traffic(fclass)
            feature_id = len(transport_features) + 1
            transport_features.append(
                {
                    "type": "Feature",
                    "id": feature_id,
                    "properties": {
                        "PK": feature_id,
                        "road_type": "road",
                        "osm_id": osm_id,
                        "fclass": fclass,
                        "name": name,
                        "max_speed": speed,
                        "car_traffic_daily": car_traffic,
                        "truck_traffic_daily": truck_traffic,
                        "traffic_settings_adjustable": True,
                        "PVMT": "DEF",
                        "WAY": 3,
                        "JUNC_DIST": 0,
                        "JUNC_TYPE": 0,
                        "source": "Geofabrik Hamburg OSM GeoPackage",
                    },
                    "geometry": transform_geometry_to_utm(geometry),
                }
            )

        for row in connection.execute(
            "select geom, osm_id, fclass, name, bridge, tunnel from gis_osm_railways_free"
        ):
            geom_blob, osm_id, fclass, name, bridge, tunnel = row
            if fclass not in RAIL_CLASSES:
                continue
            geometry = read_gpkg_geometry(geom_blob)
            if not bbox_intersects(geometry_bbox(geometry), aoi_lonlat_bbox):
                continue
            feature_id = len(transport_features) + 1
            transport_features.append(
                {
                    "type": "Feature",
                    "id": feature_id,
                    "properties": {
                        "PK": feature_id,
                        "road_type": "railroad",
                        "osm_id": osm_id,
                        "fclass": fclass,
                        "name": name,
                        "train_speed": 60 if fclass in {"tram", "subway"} else 80,
                        "trains_per_hour": 4 if fclass in {"tram", "subway"} else 2,
                        "tracks": 2,
                        "tunnel": str(tunnel).upper() in {"T", "TRUE", "1", "YES"},
                        "bridge_type": bridge,
                        "source": "Geofabrik Hamburg OSM GeoPackage",
                    },
                    "geometry": transform_geometry_to_utm(geometry),
                }
            )

        for table_name, source_label in [
            ("gis_osm_landuse_a_free", "landuse"),
            ("gis_osm_natural_a_free", "natural"),
            ("gis_osm_water_a_free", "water"),
        ]:
            for row in connection.execute(f"select geom, osm_id, fclass, name from {table_name}"):
                geom_blob, osm_id, fclass, name = row
                geometry = read_gpkg_geometry(geom_blob)
                if not bbox_intersects(geometry_bbox(geometry), aoi_lonlat_bbox):
                    continue
                feature_id = len(ground_features) + 1
                ground_features.append(
                    {
                        "type": "Feature",
                        "id": feature_id,
                        "properties": {
                            "PK": feature_id,
                            "G": GROUND_G_BY_CLASS.get(fclass, 0.5),
                            "osm_id": osm_id,
                            "fclass": fclass,
                            "name": name,
                            "source": f"Geofabrik Hamburg OSM GeoPackage {source_label}",
                        },
                        "geometry": transform_geometry_to_utm(geometry),
                    }
                )

    traffic_assignment_count = assign_traffic_counts_to_roads(transport_features, traffic_features)
    gtfs_assignment_count = assign_gtfs_to_rails(transport_features, gtfs_rail_shapes)

    write_feature_collection(PROCESSED / "roads_osm_hafencity.geojson", transport_features)
    write_feature_collection(PROCESSED / "ground_absorption_osm_hafencity.geojson", ground_features)
    rail_count = sum(1 for feature in transport_features if feature["properties"].get("road_type") == "railroad")
    return len(transport_features) - rail_count, rail_count, len(ground_features), traffic_assignment_count, gtfs_assignment_count


def alkis_poslists(feature: ET.Element) -> Iterable[list[tuple[float, float]]]:
    for element in feature.iter():
        if element.tag.endswith("posList") and element.text:
            values = [float(value) for value in element.text.split()]
            if len(values) < 4:
                continue
            dimension = int(element.attrib.get("srsDimension", "2"))
            coords = []
            for index in range(0, len(values), dimension):
                coords.append((values[index], values[index + 1]))
            if coords:
                yield coords


def local_name(element: ET.Element) -> str:
    return element.tag.split("}", 1)[-1]


def first_child_by_local_name(element: ET.Element, name: str) -> ET.Element | None:
    for child in list(element):
        if local_name(child) == name:
            return child
    return None


def assemble_alkis_ring(ring: ET.Element) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for coords in alkis_poslists(ring):
        for point in coords:
            if not points or math.hypot(points[-1][0] - point[0], points[-1][1] - point[1]) > 0.001:
                points.append(point)
    if len(points) >= 3 and math.hypot(points[0][0] - points[-1][0], points[0][1] - points[-1][1]) > 0.001:
        points.append(points[0])
    return points


def alkis_polygon_rings(feature: ET.Element) -> Iterable[list[tuple[float, float]]]:
    for patch in feature.iter():
        if local_name(patch) != "PolygonPatch":
            continue
        exterior = first_child_by_local_name(patch, "exterior")
        if exterior is None:
            continue
        for descendant in exterior.iter():
            if local_name(descendant) == "Ring":
                ring = assemble_alkis_ring(descendant)
                if len(ring) >= 4:
                    yield ring
                break


def gml_id(element: ET.Element) -> str:
    return element.attrib.get("{http://www.opengis.net/gml/3.2}id") or element.attrib.get("{http://www.opengis.net/gml}id") or ""


def prepare_alkis_index(aoi_bbox: tuple[float, float, float, float]) -> tuple[int, Counter[str], int]:
    rows: list[dict[str, str]] = []
    geometry_features: list[dict[str, Any]] = []
    ground_features: list[dict[str, Any]] = []
    type_counter: Counter[str] = Counter()
    member_tag = "{http://www.opengis.net/wfs/2.0}member"

    with zipfile.ZipFile(ALKIS_ZIP) as archive:
        names = [name for name in archive.namelist() if name.lower().endswith(".xml")]
        for name in names:
            with archive.open(name) as handle:
                for _event, member in ET.iterparse(handle, events=("end",)):
                    if member.tag != member_tag:
                        continue
                    children = list(member)
                    if not children:
                        member.clear()
                        continue
                    feature = children[0]
                    feature_type = feature.tag.split("}", 1)[-1]
                    feature_id = gml_id(feature)
                    funktion = local_text(feature, "funktion")
                    name_value = local_text(feature, "name") or local_text(feature, "zweitname")
                    matched_geometries: list[tuple[str, list[tuple[float, float]]]] = []
                    for coords in alkis_polygon_rings(feature):
                        geom_bbox = bounds(coords)
                        if bbox_intersects(geom_bbox, aoi_bbox):
                            matched_geometries.append(("Polygon", coords))
                    if not matched_geometries:
                        for coords in alkis_poslists(feature):
                            geom_bbox = bounds(coords)
                            if bbox_intersects(geom_bbox, aoi_bbox):
                                matched_geometries.append(("LineString", coords))
                    if matched_geometries:
                        rows.append(
                            {
                                "source_file": name,
                                "feature_type": feature_type,
                                "gml_id": feature_id,
                                "geometry_count": str(len(matched_geometries)),
                            }
                        )
                        type_counter[feature_type] += 1
                        for geometry_type, coords in matched_geometries:
                            feature_index = len(geometry_features) + 1
                            ring = [[x, y] for x, y in coords]
                            if geometry_type == "Polygon" and len(ring) >= 4:
                                geometry = {"type": "Polygon", "coordinates": [ring]}
                            else:
                                geometry = {"type": "LineString", "coordinates": ring}
                            geometry_features.append(
                                {
                                    "type": "Feature",
                                    "id": feature_index,
                                    "properties": {
                                        "source_file": name,
                                        "feature_type": feature_type,
                                        "gml_id": feature_id,
                                        "funktion": funktion,
                                        "name": name_value,
                                    },
                                    "geometry": geometry,
                                }
                            )
                            if geometry["type"] == "Polygon" and feature_type in ALKIS_G_BY_FEATURE_TYPE:
                                ground_index = len(ground_features) + 1
                                ground_features.append(
                                    {
                                        "type": "Feature",
                                        "id": ground_index,
                                        "properties": {
                                            "PK": ground_index,
                                            "G": ALKIS_G_BY_FEATURE_TYPE[feature_type],
                                            "feature_type": feature_type,
                                            "funktion": funktion,
                                            "name": name_value,
                                            "gml_id": feature_id,
                                            "source": "Hamburg ALKIS selected data 2026-01-15",
                                        },
                                        "geometry": geometry,
                                    }
                                )
                    member.clear()

    index_path = SUBSET / "alkis" / "alkis_hafencity_feature_index.csv"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    with index_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["source_file", "feature_type", "gml_id", "geometry_count"])
        writer.writeheader()
        writer.writerows(rows)
    write_feature_collection(PROCESSED / "alkis_hafencity_geometries.geojson", geometry_features)
    write_feature_collection(PROCESSED / "ground_absorption_alkis_hafencity.geojson", ground_features)
    with (SUBSET / "alkis" / "alkis_hafencity_feature_counts.json").open("w", encoding="utf-8") as handle:
        json.dump(type_counter, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return len(rows), type_counter, len(ground_features)


def write_citypyo_package(ground_absorption_path: Path) -> None:
    CITYPYO_PACKAGE.mkdir(parents=True, exist_ok=True)
    copies = {
        PROCESSED / "project_area_25832.geojson": CITYPYO_PACKAGE / "project_area.geojson",
        PROCESSED / "buildings_lod2_hafencity.geojson": CITYPYO_PACKAGE / "upperfloor.geojson",
        PROCESSED / "roads_osm_hafencity.geojson": CITYPYO_PACKAGE / "roads.geojson",
        PROCESSED / "dem_hafencity.geojson": CITYPYO_PACKAGE / "dem.geojson",
        ground_absorption_path: CITYPYO_PACKAGE / "ground_absorption.geojson",
        PROCESSED / "atmospheric_settings_01975_recent.csv": CITYPYO_PACKAGE / "atmospheric_settings.csv",
        PROCESSED / "traffic_counts_hafencity.geojson": CITYPYO_PACKAGE / "traffic_counts_reference.geojson",
        PROCESSED / "alkis_hafencity_geometries.geojson": CITYPYO_PACKAGE / "alkis_reference.geojson",
    }
    for source, destination in copies.items():
        if source.exists():
            shutil.copyfile(source, destination)

    sources_path = CITYPYO_PACKAGE / "SOURCES.md"
    sources_path.write_text(
        "\n".join(
            [
                "# HafenCity NM5 Local Package Sources",
                "",
                "This folder is a CityPyo-style local input package for `nm5_full`.",
                "",
                "Use with:",
                "",
                "- `CITY_PYO=downloads/hafencity_full/citypyo`",
                "- `city_pyo_user=hafencity_full`",
                "- `NOISE_ENGINE=nm5_full`",
                "",
                "Layer provenance:",
                "",
                "| File | Source |",
                "| --- | --- |",
                "| `project_area.geojson` | repo fixture `fixtures/citypyo/demo/project_area.geojson`, projected to `EPSG:25832` |",
                "| `upperfloor.geojson` | Hamburg LoD2-DE CityGML, 2023-04-01 package |",
                "| `roads.geojson` | Geofabrik Hamburg OSM road and rail geometry enriched with Hamburg traffic counts and hvv GTFS where matched |",
                "| `dem.geojson` | Hamburg DGM1 2020 2x2 km XYZ tile `DGM1_32566_5932_2_FHH.xyz`, clipped to the AOI |",
                "| `ground_absorption.geojson` | Hamburg ALKIS actual-use polygons mapped to NM5 `G` values; OSM fallback exists in `processed/ground_absorption_osm_hafencity.geojson` |",
                "| `atmospheric_settings.csv` | DWD station `01975` Hamburg-Fuhlsbuettel recent hourly observations |",
                "| `traffic_counts_reference.geojson` | Hamburg traffic-count points clipped to the AOI; assignments are stored in `processed/traffic_count_assignments_hafencity.csv` |",
                "| `alkis_reference.geojson` | Hamburg ALKIS 2026-01 AOI-intersecting geometries |",
                "",
                "Detailed source URLs and caveats are tracked in",
                "`docs/hafencity_nm5_data_sources.md` and in",
                "`downloads/hafencity_full/manifest.md`.",
                "",
            ]
        ),
        encoding="utf-8",
    )


def main() -> None:
    PROCESSED.mkdir(parents=True, exist_ok=True)
    SUBSET.mkdir(parents=True, exist_ok=True)

    aoi_lonlat = load_aoi_lonlat()
    aoi_utm = [latlon_to_utm32(lon, lat) for lon, lat in aoi_lonlat]
    aoi_utm_bbox = bounds(aoi_utm)
    aoi_lonlat_bbox = bounds(aoi_lonlat)

    write_project_area(aoi_utm)
    building_count = prepare_lod2_buildings(aoi_utm_bbox)
    dem_count = prepare_dem(aoi_utm, aoi_utm_bbox)
    traffic_features = prepare_traffic_count_subset(aoi_utm_bbox)
    gtfs_rail_shapes = prepare_gtfs_rail_shapes(aoi_lonlat_bbox)
    road_count, rail_count, ground_count, traffic_assignment_count, gtfs_assignment_count = prepare_osm_transport_and_ground(
        aoi_lonlat_bbox,
        traffic_features,
        gtfs_rail_shapes,
    )
    alkis_count, alkis_counter, alkis_ground_count = prepare_alkis_index(aoi_utm_bbox)
    ground_absorption_path = (
        PROCESSED / "ground_absorption_alkis_hafencity.geojson"
        if alkis_ground_count
        else PROCESSED / "ground_absorption_osm_hafencity.geojson"
    )
    write_citypyo_package(ground_absorption_path)

    summary = {
        "aoi_utm_bbox": {
            "min_x": aoi_utm_bbox[0],
            "min_y": aoi_utm_bbox[1],
            "max_x": aoi_utm_bbox[2],
            "max_y": aoi_utm_bbox[3],
        },
        "project_area": str(PROCESSED / "project_area_25832.geojson"),
        "lod2_buildings": building_count,
        "dgm_points": dem_count,
        "osm_road_features": road_count,
        "osm_rail_features": rail_count,
        "osm_ground_absorption_features": ground_count,
        "traffic_count_points": len(traffic_features),
        "traffic_count_assignments": traffic_assignment_count,
        "gtfs_rail_shapes": len(gtfs_rail_shapes),
        "gtfs_rail_assignments": gtfs_assignment_count,
        "alkis_matching_features": alkis_count,
        "alkis_feature_types": dict(alkis_counter),
        "alkis_ground_absorption_features": alkis_ground_count,
        "citypyo_package": str(CITYPYO_PACKAGE),
        "citypyo_ground_absorption_source": str(ground_absorption_path),
    }
    with (PROCESSED / "subset_summary.json").open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
