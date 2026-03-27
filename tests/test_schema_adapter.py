import unittest

from noise_analysis.schema_adapter import (
    DEFAULT_BUILDING_HEIGHT,
    adapt_buildings_geojson,
    adapt_roads_geojson,
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
            {
                "max_speed": 42,
                "traffic_quota": 40,
            },
        )
        properties = adapted_geojson["features"][0]["properties"]

        self.assertEqual(metadata["exported_features"], 1)
        self.assertEqual(metadata["skipped_rail_features"], 1)
        self.assertEqual(properties["LV_D"], int((10 * 40) * 0.11))
        self.assertEqual(properties["HGV_N"], int((5 * 40) * 0.08))
        self.assertEqual(properties["LV_SPD_E"], 42)
        self.assertEqual(properties["PVMT"], "DEF")
        self.assertEqual(properties["WAY"], 3)


if __name__ == "__main__":
    unittest.main()
