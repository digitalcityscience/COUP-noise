import unittest
from unittest import mock

try:
    from noise_analysis.calculation_settings import CalculationSettings
    from noise_analysis.nm5_runner import _noise_level_parameters, normalize_nm5_result_geojson
except ModuleNotFoundError:
    CalculationSettings = None
    _noise_level_parameters = None
    normalize_nm5_result_geojson = None
    HAS_NM5_RUNNER_DEPS = False
else:
    HAS_NM5_RUNNER_DEPS = True


@unittest.skipUnless(HAS_NM5_RUNNER_DEPS, "NM5 runner dependencies are not installed in this interpreter")
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

    def test_noise_level_parameters_use_request_thread_number(self):
        settings = CalculationSettings.from_mapping(
            {
                "max_speed": 42,
                "traffic_quota": 1,
                "result_format": "geojson",
                "noise_engine": "nm5_full",
                "nm5_settings": {
                    "thread_number": 6,
                },
            }
        )

        with mock.patch.dict("os.environ", {"NM5_THREAD_NUMBER": "2"}, clear=False):
            parameters = _noise_level_parameters(
                settings,
                wall_absorption=0.23,
                has_dem=False,
                has_ground_absorption=False,
                has_source_directivity=False,
                has_atmospheric_settings=False,
                has_rail_sources=False,
            )

        self.assertEqual(parameters["confThreadNumber"], 6)

    def test_noise_level_parameters_use_env_thread_number_when_request_omits_it(self):
        settings = CalculationSettings.from_mapping(
            {
                "max_speed": 42,
                "traffic_quota": 1,
                "result_format": "geojson",
                "noise_engine": "nm5",
            }
        )

        with mock.patch.dict("os.environ", {"NM5_THREAD_NUMBER": "4"}, clear=False):
            parameters = _noise_level_parameters(
                settings,
                wall_absorption=0.23,
                has_dem=False,
                has_ground_absorption=False,
                has_source_directivity=False,
                has_atmospheric_settings=False,
                has_rail_sources=False,
            )

        self.assertEqual(parameters["confThreadNumber"], 4)


if __name__ == "__main__":
    unittest.main()
