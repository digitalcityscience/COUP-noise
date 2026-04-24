import unittest
from tempfile import TemporaryDirectory
from pathlib import Path

from noise_analysis.calculation_settings import TrafficSettings
from noise_analysis.schema_adapter import (
    DEFAULT_BUILDING_HEIGHT,
    adapt_buildings_geojson,
    adapt_atmospheric_settings_table,
    adapt_ground_absorption_geojson,
    adapt_roads_geojson,
    prepare_nm5_input_files,
)


def _polygon(x_offset):
    return {
        "type": "Polygon",
        "coordinates": [
            [
                [x_offset, 0],
                [x_offset + 1, 0],
                [x_offset + 1, 1],
                [x_offset, 1],
                [x_offset, 0],
            ]
        ],
    }


def _line(x_offset):
    return {
        "type": "LineString",
        "coordinates": [
            [x_offset, 0],
            [x_offset + 1, 1],
        ],
    }


class SchemaAdapterTests(unittest.TestCase):
    def test_adapt_buildings_geojson_derives_height_and_tracks_default_usage(self):
        buildings_geojson = {
            "type": "FeatureCollection",
            "features": [
                {"type": "Feature", "geometry": _polygon(0), "properties": {"height": 12}},
                {"type": "Feature", "geometry": _polygon(2), "properties": {"floors": 4}},
                {"type": "Feature", "geometry": _polygon(4), "properties": {}},
            ],
        }

        adapted_geojson, metadata = adapt_buildings_geojson(buildings_geojson)
        heights = [feature["properties"]["HEIGHT"] for feature in adapted_geojson["features"]]

        self.assertEqual(heights, [12.0, 12.0, DEFAULT_BUILDING_HEIGHT])
        self.assertEqual(metadata["used_default_height"], 1)
        self.assertEqual(metadata["exported_features"], 3)

    def test_adapt_roads_geojson_preserves_current_traffic_adjustment_and_skips_rail(self):
        roads_geojson = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": _line(0),
                    "properties": {
                        "road_type": "street",
                        "car_traffic_daily": 10,
                        "truck_traffic_daily": 5,
                        "max_speed": 30,
                        "traffic_settings_adjustable": True,
                    },
                },
                {
                    "type": "Feature",
                    "geometry": _line(2),
                    "properties": {
                        "road_type": "railroad",
                        "car_traffic_daily": 0,
                        "truck_traffic_daily": 0,
                        "max_speed": 0,
                    },
                },
            ],
        }

        adapted_geojson, metadata = adapt_roads_geojson(
            roads_geojson,
            TrafficSettings(max_speed=42, traffic_quota=40),
        )
        properties = adapted_geojson["features"][0]["properties"]

        self.assertEqual(metadata["exported_features"], 1)
        self.assertEqual(metadata["skipped_rail_features"], 1)
        self.assertEqual(properties["LV_D"], int((10 * 40) * 0.11))
        self.assertEqual(properties["HGV_N"], int((5 * 40) * 0.08))
        self.assertEqual(properties["LV_SPD_E"], 42)
        self.assertEqual(properties["PVMT"], "DEF")
        self.assertEqual(properties["WAY"], 3)

    def test_adapt_ground_absorption_geojson_keeps_polygons_with_g(self):
        ground_geojson = {
            "type": "FeatureCollection",
            "features": [
                {"type": "Feature", "geometry": _polygon(0), "properties": {"G": 0.7}},
                {"type": "Feature", "geometry": _polygon(2), "properties": {}},
            ],
        }

        adapted_geojson, metadata = adapt_ground_absorption_geojson(ground_geojson)

        self.assertEqual(metadata["exported_features"], 1)
        self.assertEqual(metadata["skipped_missing_g"], 1)
        self.assertEqual(adapted_geojson["features"][0]["properties"]["G"], 0.7)

    def test_adapt_atmospheric_settings_accepts_windrose_list(self):
        rows, metadata = adapt_atmospheric_settings_table(
            [
                {
                    "period": "d",
                    "temperature": 12,
                    "pressure": 101325,
                    "humidity": 80,
                    "gdisc": True,
                    "prime2520": False,
                    "windrose": [0.5] * 16,
                }
            ]
        )

        self.assertEqual(metadata["exported_rows"], 1)
        self.assertEqual(rows[0]["PERIOD"], "D")
        self.assertEqual(rows[0]["WINDROSE_15"], 0.5)

    def test_prepare_nm5_input_files_full_contract_requires_full_layers(self):
        buildings_geojson = {
            "type": "FeatureCollection",
            "features": [{"type": "Feature", "geometry": _polygon(0), "properties": {"height": 12}}],
        }
        roads_geojson = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": _line(0),
                    "properties": {
                        "road_type": "street",
                        "car_traffic_daily": 10,
                        "truck_traffic_daily": 5,
                        "max_speed": 30,
                    },
                }
            ],
        }

        with TemporaryDirectory() as temp_dir:
            with self.assertRaises(ValueError):
                prepare_nm5_input_files(
                    Path(temp_dir),
                    buildings_geojson,
                    roads_geojson,
                    TrafficSettings(max_speed=30, traffic_quota=1),
                    full_contract=True,
                )


if __name__ == "__main__":
    unittest.main()
