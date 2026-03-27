import argparse
import base64
import json
import sys
import time
from pathlib import Path
from urllib import error, request

WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from noise_analysis.palette import legend_items, normalize_png_style


def _build_auth_header(user: str, password: str) -> str:
    token = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


def _http_json(url: str, method: str, auth_header: str, payload=None):
    body = None
    headers = {"Authorization": auth_header}

    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    http_request = request.Request(url, data=body, headers=headers, method=method)
    try:
        with request.urlopen(http_request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        response_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} for {url}: {response_body}") from exc


def _post_task(base_url: str, auth_header: str, payload):
    response = _http_json(f"{base_url.rstrip('/')}/task", "POST", auth_header, payload)
    return response["taskId"]


def _poll_result(base_url: str, auth_header: str, task_id: str, poll_seconds: float):
    task_url = f"{base_url.rstrip('/')}/tasks/{task_id}"

    while True:
        payload = _http_json(task_url, "GET", auth_header)

        if payload.get("resultReady"):
            return payload

        time.sleep(poll_seconds)


def _submit_and_wait(base_url: str, auth_header: str, payload, poll_seconds: float):
    task_id = _post_task(base_url, auth_header, payload)
    task_result = _poll_result(base_url, auth_header, task_id, poll_seconds)
    return task_id, task_result["result"]


def _write_png(output_path: Path, result_payload):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    png_bytes = base64.b64decode(result_payload["image_base64_string"])
    output_path.write_bytes(png_bytes)

    metadata_path = output_path.with_suffix(output_path.suffix + ".json")
    metadata_path.write_text(json.dumps(result_payload, indent=2), encoding="utf-8")


def _write_geojson(output_path: Path, result_payload):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result_payload, indent=2), encoding="utf-8")


def _geojson_sidecar_path(output_path: Path) -> Path:
    return output_path.with_suffix(".geojson")


def _map_sidecar_path(output_path: Path) -> Path:
    return output_path.with_suffix(".map.html")


def _popup_html(feature):
    properties = feature.get("properties") or {}
    idiso = properties.get("idiso", "n/a")
    cell_id = properties.get("cell_id", "n/a")
    return f"idiso: {idiso}<br>cell_id: {cell_id}"


def _build_map_html(title: str, geojson_payload) -> str:
    legend_payload = legend_items()
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
  <style>
    html, body, #map {{
      height: 100%;
      margin: 0;
    }}
    .legend {{
      background: rgba(255, 255, 255, 0.95);
      border-radius: 6px;
      box-shadow: 0 1px 6px rgba(0, 0, 0, 0.2);
      font: 13px/1.4 sans-serif;
      padding: 10px 12px;
    }}
    .legend h4 {{
      margin: 0 0 8px;
      font-size: 14px;
    }}
    .legend-row {{
      align-items: center;
      display: flex;
      gap: 8px;
      margin: 4px 0;
    }}
    .legend-swatch {{
      border: 1px solid rgba(0, 0, 0, 0.2);
      flex: 0 0 14px;
      height: 14px;
      width: 14px;
    }}
  </style>
</head>
<body>
  <div id="map"></div>
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <script>
    const geojson = {geojson_payload};
    const legend = {legend_payload};
    const map = L.map('map');

    L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
      attribution: '&copy; OpenStreetMap contributors',
      maxZoom: 19
    }}).addTo(map);

    function styleFeature(feature) {{
      const entry = legend.find((item) => item.idiso === feature.properties.idiso);
      return {{
        color: entry ? entry.color : '#555555',
        fillColor: entry ? entry.color : '#555555',
        fillOpacity: 0.55,
        opacity: 0.85,
        weight: 1
      }};
    }}

    const layer = L.geoJSON(geojson, {{
      style: styleFeature,
      onEachFeature: function(feature, layer) {{
        layer.bindPopup({popup_template}(feature));
      }}
    }}).addTo(map);

    if (layer.getBounds().isValid()) {{
      map.fitBounds(layer.getBounds(), {{ padding: [20, 20] }});
    }} else {{
      map.setView([53.55, 10.0], 13);
    }}

    const legendControl = L.control({{ position: 'bottomright' }});
    legendControl.onAdd = function() {{
      const div = L.DomUtil.create('div', 'legend');
      div.innerHTML = '<h4>Noise Classes</h4>' + legend.map((item) =>
        '<div class="legend-row"><span class="legend-swatch" style="background:' + item.color + ';"></span><span>' +
        item.idiso + ': ' + item.label + '</span></div>'
      ).join('');
      return div;
    }};
    legendControl.addTo(map);

    function popup_template(feature) {{
      return 'idiso: ' + feature.properties.idiso + '<br>cell_id: ' + feature.properties.cell_id;
    }}
  </script>
</body>
</html>
""".format(
        title=title,
        geojson_payload=json.dumps(geojson_payload),
        legend_payload=json.dumps(legend_payload),
        popup_template="popup_template",
    )


def _write_map(output_path: Path, title: str, geojson_payload) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(_build_map_html(title, geojson_payload), encoding="utf-8")


def _build_payload(args, result_format: str):
    payload = {
        "max_speed": args.max_speed,
        "traffic_quota": args.traffic_quota,
        "wall_absorption": args.wall_absorption,
        "result_format": result_format,
        "city_pyo_user": args.city_pyo_user,
    }

    if result_format == "png":
        payload["png_style"] = args.png_style

    return payload


def main():
    parser = argparse.ArgumentParser(description="Submit a COUP-noise task and save the visual result.")
    parser.add_argument("--url", default="http://localhost:5001", help="Base URL of the COUP-noise API.")
    parser.add_argument("--user", default="dev", help="HTTP basic auth user.")
    parser.add_argument("--password", default="dev", help="HTTP basic auth password.")
    parser.add_argument("--city-pyo-user", default="demo", help="CityPyo user id or local fixture folder name.")
    parser.add_argument("--result-format", choices=("png", "geojson"), default="png")
    parser.add_argument("--png-style", choices=("raw", "palette"), default="palette", help="PNG rendering style when result-format=png.")
    parser.add_argument("--output", required=True, help="Output file path.")
    parser.add_argument("--max-speed", type=float, required=True)
    parser.add_argument("--traffic-quota", type=float, required=True)
    parser.add_argument("--wall-absorption", type=float, default=0.23)
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    parser.add_argument("--write-geojson", action="store_true", help="Also save a GeoJSON sidecar for inspection.")
    parser.add_argument("--write-map", action="store_true", help="Also generate an interactive Leaflet HTML map.")
    args = parser.parse_args()
    args.png_style = normalize_png_style(args.png_style)

    auth_header = _build_auth_header(args.user, args.password)
    task_id, result_payload = _submit_and_wait(
        args.url,
        auth_header,
        _build_payload(args, args.result_format),
        args.poll_seconds,
    )

    output_path = Path(args.output)
    sidecars = []
    if args.result_format == "png":
        _write_png(output_path, result_payload)
    else:
        _write_geojson(output_path, result_payload)

    geojson_payload = result_payload if args.result_format == "geojson" else None
    geojson_task_id = None
    if args.write_geojson or args.write_map:
        if geojson_payload is None:
            geojson_task_id, geojson_payload = _submit_and_wait(
                args.url,
                auth_header,
                _build_payload(args, "geojson"),
                args.poll_seconds,
            )

        geojson_output_path = _geojson_sidecar_path(output_path)
        _write_geojson(geojson_output_path, geojson_payload)
        sidecars.append(str(geojson_output_path))

        if args.write_map:
            map_output_path = _map_sidecar_path(output_path)
            _write_map(map_output_path, output_path.stem, geojson_payload)
            sidecars.append(str(map_output_path))

    print(
        json.dumps(
            {
                "task_id": task_id,
                "geojson_task_id": geojson_task_id,
                "output": str(output_path),
                "sidecars": sidecars,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
