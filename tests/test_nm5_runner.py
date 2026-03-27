import importlib.util
import unittest

HAS_GEOPANDAS = importlib.util.find_spec("geopandas") is not None

if HAS_GEOPANDAS:
    from noise_analysis.nm5_runner import normalize_nm5_result_geojson
else:
    normalize_nm5_result_geojson = None


@unittest.skipUnless(HAS_GEOPANDAS, "geopandas is not installed in this interpreter")
class Nm5RunnerTests(unittest.TestCase):
    def test_normalize_nm5_result_geojson_prefers_day_period_and_renames_fields(self):
        exported_geojson = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [
                            [
                                [500000, 5800000],
                                [500010, 5800000],
                                [500010, 5800010],
                                [500000, 5800010],
                                [500000, 5800000],
                            ]
                        ],
                    },
                    "properties": {
                        "PERIOD": "E",
                        "ISOLVL": 5,
                        "CELL_ID": 101,
                    },
                },
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [
                            [
                                [500020, 5800000],
                                [500030, 5800000],
                                [500030, 5800010],
                                [500020, 5800010],
                                [500020, 5800000],
                            ]
                        ],
                    },
                    "properties": {
                        "PERIOD": "D",
                        "ISOLVL": 3,
                        "CELL_ID": 99,
                    },
                },
            ],
        }

        normalized = normalize_nm5_result_geojson(exported_geojson)

        self.assertEqual(len(normalized["features"]), 1)
        self.assertEqual(normalized["features"][0]["properties"]["idiso"], 3)
        self.assertEqual(normalized["features"][0]["properties"]["cell_id"], 99)


if __name__ == "__main__":
    unittest.main()
