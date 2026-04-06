# COUP-noise

COUP-noise is a Flask + Celery + Redis service that wraps traffic-noise calculation engines for downstream clients. It fetches geometry from CityPyo, applies a small set of scenario adjustments, runs the selected engine, clips the result to the project area, and can rasterize the final contour polygons to PNG for visual comparison.

The project started from a legacy embedded NoiseModelling-based workflow and now also ships a headless NoiseModelling 5 integration. This README stays intentionally high level: it explains what the service does and what is currently wired through the COUP-noise API, but it is not meant to be a formal API or engine specification.

## Current NM5 Status

- COUP-noise currently supports both `legacy` and `nm5` behind the same task API.
- `nm5` is the active migration path, but the COUP-noise API still exposes only a compatibility-oriented slice of native NoiseModelling 5.
- Roads are supported.
- Rail is supported through generated `RAIL_SECTIONS` and `RAIL_TRAFFIC` inputs, with defaults and heuristics when source data is sparse.
- DEM support is available on the NM5 path when the selected CityPyo user provides a `dem.geojson` layer.
- Ground absorption, source directivity, and atmospheric settings are not exposed through the public COUP-noise API yet.
- Building heights are derived from source properties when possible and otherwise fall back to a default height on the NM5 path.
- The built-in `demo` fixtures do not currently include a DEM layer, so the default local demo still runs without terrain.

## Capability Snapshot

This table is intentionally high level. It is for orientation, not as a replacement for the code.

| Area | What the legacy model can theoretically do | What NM5 can theoretically do | What is currently supported through the COUP-noise API |
| --- | --- | --- | --- |
| Buildings and facades | Treat 2D buildings as obstacles in a fixed internal workflow | Use explicit building heights and richer propagation inputs | Buildings are loaded from CityPyo for both engines; legacy uses geometry only, NM5 derives heights when available |
| Road traffic | Compute road noise from a simplified traffic and speed model | Use richer CNOSSOS road inputs, vehicle classes, pavement, slope, and period handling | The API exposes only a small shared setting set; the NM5 adapter fills richer road fields internally |
| Rail traffic | Support a simple rail path mixed into the transport feed | Support dedicated railway track and railway traffic tables | Rail is supported, but only through the existing COUP-noise transport feed plus adapter logic |
| Terrain | No terrain support | Use DEM and terrain-aware propagation | Optional on the NM5 path when a `dem.geojson` layer exists |
| Ground absorption | Not available | Support dedicated ground absorption polygons | Not currently exposed |
| Source directivity | Not available | Support directivity tables and directional emission data | Not currently exposed |
| Weather and period settings | Not available | Support period-aware atmospheric settings and richer time-period handling | Not currently exposed |
| Receiver mesh and propagation tuning | Fixed internal settings | Many meshing and propagation parameters are available natively | COUP-noise keeps compatibility-oriented internal defaults rather than exposing these knobs |
| Native outputs | Final contour polygons for the service response | Intermediate and final tables such as sources, receivers, levels, and contours | The COUP-noise API returns clipped GeoJSON contours or PNG overlays, not raw engine tables |

## What The Service Consumes

The service expects a CityPyo user or local fixture folder. COUP-noise then loads:

- buildings from `upperfloor.geojson`
- transport features from `roads.geojson`
- the clipping area from `project_area.geojson`
- optionally `dem.geojson` for terrain on the NM5 path

Common request-side adjustments:

- `traffic_quota`: a scalar multiplier applied to adjustable roads. In practice, examples such as `1.0` keep source traffic and `0.5` halves it.
- `max_speed`: a speed override applied to adjustable roads.
- `wall_absorption`: an acoustic tuning value used by the selected engine.

## Results

The API returns contour polygons classified into eight `idiso` buckets after clipping to the project area. Results can be returned directly as GeoJSON or converted to PNG for visual comparison and map overlays. Palette PNGs include legend metadata in the response.

## Technical Setup

This project uses Celery to process tasks asynchronously. Redis is used as both the broker and the result backend. Flask provides the HTTP API, and Docker Compose is used for local orchestration.

## Design

Tasks are submitted through `POST /task`.

The client receives a task id and polls `GET /tasks/<task_id>` until the result is ready.

## Caching

After a task has been processed successfully, the result is cached together with the normalized scenario and geometry inputs. Identical follow-up requests can therefore return from cache instead of recomputing the noise map.

## Tech Stack

- Python
- Celery
- Redis
- Flask
- Docker

## Environment Variables

Specify these in `docker-compose.yml` or in your environment:

- `REDIS_HOST=redis`
- `REDIS_PORT=6379`
- `REDIS_PASS=YOUR_PASS`
- `CITY_PYO=YOUR_CITYPYO_URL`
- `CLIENT_ID=YOUR_ID`
- `CLIENT_PASSWORD=YOUR_PASSWORD`
- `NOISE_ENGINE=legacy|nm5|auto`
- `CELERY_QUEUE=noise`

For local testing, `docker-compose.yml` ships with safe defaults:

- `REDIS_PASS=devredis`
- `CLIENT_ID=dev`
- `CLIENT_PASSWORD=dev`
- `CITY_PYO=/app/fixtures/citypyo`

That local fixture source includes a built-in `demo` user with:

- `upperfloor.geojson`
- `roads.geojson`
- `project_area.geojson`

You only need real CityPyo values if you want to test against a live upstream dataset.

## Start

1. `docker compose build`
2. `docker compose up -d`

For the built-in local dataset, submit tasks with `city_pyo_user=demo` and use `dev` / `dev` as the basic-auth credentials.

## Compare Workflow

The repository can run two calculation engines behind the same task API:

- `NOISE_ENGINE=legacy` uses the original embedded engine in this repo
- `NOISE_ENGINE=nm5` uses the headless NoiseModelling 5 runner plus the local adapter pipeline

For honest comparison, run them explicitly one after the other. Do not use `NOISE_ENGINE=auto` for visual assessment because it may fall back to legacy if the NM5 runner is unavailable.

If you do not have a CityPyo server, use the built-in local `demo` fixtures. The commands below assume that default setup.

1. Build the image once:

```bash
docker compose build
```

2. Start the legacy stack:

```bash
NOISE_ENGINE=legacy CELERY_QUEUE=noise_legacy docker compose up -d
```

3. Save a legacy PNG result and also generate a sidecar GeoJSON plus an interactive HTML map:

```bash
python tools/save_noise_result.py \
  --url http://localhost:5001 \
  --result-format png \
  --png-style palette \
  --write-geojson \
  --write-map \
  --max-speed 10 \
  --traffic-quota 0.5 \
  --wall-absorption 0.69 \
  --output outputs/legacy.png
```

4. Stop the stack:

```bash
docker compose down
```

5. Start the NM5 stack:

```bash
NOISE_ENGINE=nm5 CELERY_QUEUE=noise_nm5 docker compose up -d
```

6. Save an NM5 PNG result and also generate a sidecar GeoJSON plus an interactive HTML map:

```bash
python tools/save_noise_result.py \
  --url http://localhost:5001 \
  --result-format png \
  --png-style palette \
  --write-geojson \
  --write-map \
  --max-speed 10 \
  --traffic-quota 0.5 \
  --wall-absorption 0.69 \
  --output outputs/nm5.png
```

The PNG metadata is saved next to the image as `.json`. With `--write-geojson` and `--write-map` the tool also writes `.geojson` and `.map.html` files for inspection on a basemap.

### Why Separate Queues Matter

The Celery queue name can be set with `CELERY_QUEUE`. Use different values such as `noise_legacy` and `noise_nm5` if you compare engines. This prevents tasks from being consumed by the wrong worker set.

## Usage

### Create a Task

Submit a representative scenario payload. In normal use you request either `geojson` or `png` output.

Common fields:

- `max_speed` in km/h
- `traffic_quota` as a scalar multiplier, for example `0.5`
- `wall_absorption` as an optional acoustic tuning value
- `city_pyo_user` for the CityPyo user or local fixture folder
- `result_format` as `geojson` or `png`
- `png_style` optionally when `result_format=png`

Example request:

```bash
curl --location --request POST 'http://localhost:5001/task' \
--header 'Content-Type: application/json' \
--header 'Authorization: Basic YOUR_AUTH_TOKEN' \
--data-raw '{
  "max_speed": 10,
  "traffic_quota": 0.5,
  "wall_absorption": 0.69,
  "result_format": "png",
  "city_pyo_user": "demo"
}'
```

Example response:

```json
{
  "taskId": "110fbbca-cd8c-4e57-9cdc-8a02cdc71ee7"
}
```

### Get Task Result

```bash
curl -X GET http://localhost:5001/tasks/110fbbca-cd8c-4e57-9cdc-8a02cdc71ee7 \
  --header 'Authorization: Basic YOUR_AUTH_TOKEN'
```

Representative GeoJSON result envelope:

```json
{
  "resultReady": true,
  "taskId": "98b34861-ba4d-441e-8493-05e465a998c1",
  "taskState": "SUCCESS",
  "taskSucceeded": true,
  "result": {
    "type": "FeatureCollection",
    "features": [
      {
        "type": "Feature",
        "properties": {
          "cell_id": 0,
          "idiso": 3
        },
        "geometry": {
          "type": "Polygon",
          "coordinates": [ ... ]
        }
      }
    ]
  }
}
```

Representative PNG result envelope:

```json
{
  "resultReady": true,
  "taskId": "98b34861-ba4d-441e-8493-05e465a998c1",
  "taskState": "SUCCESS",
  "taskSucceeded": true,
  "result": {
    "bbox_coordinates": [ ... ],
    "bbox_sw_corner": [ ... ],
    "img_width": 1200,
    "img_height": 800,
    "image_base64_string": "iVBORw0KGgoAAAANSUhEUg...",
    "png_style": "palette",
    "legend": [ ... ]
  }
}
```

## Commands

### Start worker

`celery -A tasks worker --loglevel=info`

### Monitoring Redis

List tasks:

- `redis-cli -h HOST -p PORT -n DATABASE_NUMBER llen QUEUE_NAME`

List queues:

- `redis-cli -h HOST -p PORT -n DATABASE_NUMBER keys *`

## How It Works

### CityPyo

CityPyo is the upstream geometry source used by the service. COUP-noise reads the selected user's buildings, transport features, project area, and optional terrain layer from there or from the local fixture directory.

### Apply Request Settings

The obtained transport GeoJSON is normalized and modified with the requested `max_speed` and `traffic_quota` values before calculation.

### Engines

- `legacy` starts the original embedded H2GIS-based workflow used by this repository.
- `nm5` materializes normalized inputs and runs the bundled headless NoiseModelling 5 scripts.

Both paths are wrapped by the same Celery task flow and end in project-area clipping plus optional PNG conversion.
