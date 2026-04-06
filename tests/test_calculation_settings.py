import os
import unittest
from unittest import mock

from noise_analysis.calculation_settings import CalculationSettings, TrafficSettings
from services import get_calculation_settings


class CalculationSettingsTests(unittest.TestCase):
    def test_from_flat_payload_normalizes_png_style_and_engine(self):
        settings = CalculationSettings.from_mapping(
            {
                "max_speed": 30,
                "traffic_quota": 0.5,
                "wall_absorption": 0.3,
                "result_format": "PNG",
                "png_style": "PALETTE",
            },
            default_noise_engine="NM5",
        )

        self.assertEqual(settings.result_format, "png")
        self.assertEqual(settings.noise_engine, "nm5")
        self.assertEqual(settings.png_style, "palette")
        self.assertEqual(settings.traffic_settings.max_speed, 30.0)
        self.assertEqual(settings.calculation_settings.wall_absorption, 0.3)

    def test_from_nested_payload_ignores_png_style_for_geojson(self):
        settings = CalculationSettings.from_mapping(
            {
                "traffic_settings": {
                    "max_speed": 42,
                    "traffic_quota": 40,
                },
                "calculation_settings": {
                    "wall_absorption": 0.23,
                },
                "result_format": "geojson",
                "noise_engine": "legacy",
                "png_style": "palette",
            }
        )

        self.assertEqual(settings.result_format, "geojson")
        self.assertIsNone(settings.png_style)

    def test_from_mapping_uses_env_default_png_style(self):
        with mock.patch.dict(os.environ, {"NOISE_PNG_STYLE": "palette"}, clear=False):
            settings = CalculationSettings.from_mapping(
                {
                    "max_speed": 30,
                    "traffic_quota": 0.5,
                    "result_format": "png",
                }
            )

        self.assertEqual(settings.png_style, "palette")

    def test_from_mapping_rejects_invalid_wall_absorption(self):
        with self.assertRaises(ValueError):
            CalculationSettings.from_mapping(
                {
                    "max_speed": 30,
                    "traffic_quota": 0.5,
                    "wall_absorption": 2,
                    "result_format": "png",
                }
            )

    def test_get_calculation_settings_builds_canonical_nested_payload(self):
        with mock.patch.dict(os.environ, {"NOISE_ENGINE": "nm5"}, clear=False):
            settings = get_calculation_settings(
                {
                    "max_speed": 10,
                    "traffic_quota": 1,
                    "wall_absorption": 0.69,
                    "result_format": "png",
                    "png_style": "RAW",
                    "city_pyo_user": "demo",
                }
            )

        self.assertEqual(
            settings,
            {
                "traffic_settings": {
                    "max_speed": 10.0,
                    "traffic_quota": 1.0,
                },
                "calculation_settings": {
                    "wall_absorption": 0.69,
                },
                "result_format": "png",
                "noise_engine": "nm5",
                "png_style": "raw",
            },
        )

    def test_traffic_settings_rejects_boolean_values(self):
        with self.assertRaises(ValueError):
            TrafficSettings.from_mapping(
                {
                    "max_speed": True,
                    "traffic_quota": 1,
                }
            )


if __name__ == "__main__":
    unittest.main()
