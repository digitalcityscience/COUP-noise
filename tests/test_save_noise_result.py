import json
import unittest

from tools.save_noise_result import _build_map_html


class SaveNoiseResultTests(unittest.TestCase):
    def test_build_map_html_embeds_geojson_and_legend(self):
        geojson_payload = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[[10.0, 53.5], [10.1, 53.5], [10.1, 53.6], [10.0, 53.6], [10.0, 53.5]]],
                    },
                    "properties": {"idiso": 3, "cell_id": 12},
                }
            ],
        }

        html = _build_map_html("demo", geojson_payload)

        self.assertIn("Noise Classes", html)
        self.assertIn("\"idiso\": 3", html)
        self.assertIn("OpenStreetMap contributors", html)
        self.assertIn("55-60 dB(A)", html)


if __name__ == "__main__":
    unittest.main()
