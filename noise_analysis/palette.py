NOISE_CLASS_LEGEND = (
    {"idiso": 0, "label": "< 45 dB(A)", "color": "#e8f5e9"},
    {"idiso": 1, "label": "45-50 dB(A)", "color": "#c8e6c9"},
    {"idiso": 2, "label": "50-55 dB(A)", "color": "#fff9c4"},
    {"idiso": 3, "label": "55-60 dB(A)", "color": "#ffe082"},
    {"idiso": 4, "label": "60-65 dB(A)", "color": "#ffb74d"},
    {"idiso": 5, "label": "65-70 dB(A)", "color": "#ff8a65"},
    {"idiso": 6, "label": "70-75 dB(A)", "color": "#ef5350"},
    {"idiso": 7, "label": "> 75 dB(A)", "color": "#b71c1c"},
)

NO_DATA_VALUE = 255
VALID_PNG_STYLES = ("raw", "palette")


def normalize_png_style(png_style):
    style = (png_style or "raw").lower()
    if style not in VALID_PNG_STYLES:
        raise ValueError("Unsupported png_style value: %s" % png_style)
    return style


def _hex_to_rgb(color):
    color = color.lstrip("#")
    return tuple(int(color[index:index + 2], 16) for index in (0, 2, 4))


def legend_items():
    return [dict(item) for item in NOISE_CLASS_LEGEND]


def rgba_palette(alpha=255):
    palette = {}
    for item in NOISE_CLASS_LEGEND:
        palette[item["idiso"]] = _hex_to_rgb(item["color"]) + (alpha,)
    return palette
