import unittest

from noise_analysis.palette import NOISE_CLASS_LEGEND, NO_DATA_VALUE, normalize_png_style, rgba_palette


class PaletteTests(unittest.TestCase):
    def test_normalize_png_style_accepts_supported_values(self):
        self.assertEqual(normalize_png_style("palette"), "palette")
        self.assertEqual(normalize_png_style("RAW"), "raw")

    def test_normalize_png_style_rejects_unknown_values(self):
        with self.assertRaises(ValueError):
            normalize_png_style("heatmap")

    def test_palette_contains_all_noise_classes(self):
        self.assertEqual(len(NOISE_CLASS_LEGEND), 8)
        self.assertEqual(sorted(item["idiso"] for item in NOISE_CLASS_LEGEND), list(range(8)))
        self.assertEqual(NO_DATA_VALUE, 255)

    def test_rgba_palette_builds_alpha_channel(self):
        palette = rgba_palette(alpha=123)
        self.assertEqual(palette[0][-1], 123)
        self.assertEqual(len(palette[7]), 4)


if __name__ == "__main__":
    unittest.main()
