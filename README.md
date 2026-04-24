# COUP-noise

COUP-noise is a Flask + Celery + Redis service that wraps traffic-noise calculation engines for downstream clients. It fetches geometry from CityPyo, applies a small set of scenario adjustments, runs the selected engine, clips the result to the project area, and can rasterize the final contour polygons to PNG for visual comparison.

The project started from a legacy embedded NoiseModelling-based workflow and now also ships a headless NoiseModelling 5 integration. This README stays intentionally high level: it explains what the service does and what is currently wired through the COUP-noise API, but it is not meant to be a formal API or engine specification.

## Current NM5 Status

- COUP-noise currently supports both `legacy` and `nm5` behind the same task API.
- `nm5` is the active migration path, but the COUP-noise API still exposes only a compatibility-oriented slice of native NoiseModelling 5.
- Roads are supported.
- Rail is supported through generated `RAIL_SECTIONS` and `RAIL_TRAFFIC` inputs, with defaults and heuristics when source data is sparse.
- DEM support is available on the NM5 path when the selected CityPyo user provides a `dem.geojson` layer.
- `nm5_full` is available for stricter NM5-native runs with DEM, ground absorption, atmospheric settings, optional source directivity, AOI-fenced receiver generation, and exposed NM5 propagation/meshing parameters.
- Building heights are derived from source properties when possible and otherwise fall back to a default height on the NM5 path.
- The built-in `demo` fixtures do not currently include a DEM layer, so the default local demo still runs without terrain.

## Capability Snapshot

This table is intentionally high level. It is for orientation, not as a replacement for the code.

| Area | What the legacy model can theoretically do | What NM5 can theoretically do | What is currently supported through the COUP-noise API |
| --- | --- | --- | --- |
| Buildings and facades | Treat 2D buildings as obstacles in a fixed internal workflow | Use explicit building heights and richer propagation inputs | Buildings are loaded from CityPyo for both engines; legacy uses geometry only, NM5 derives heights when available |
| Road traffic | Compute road noise from a simplified traffic and speed model | Use richer CNOSSOS road inputs, vehicle classes, pavement, slope, and period handling | The API exposes only a small shared setting set; the NM5 adapter fills richer road fields internally |
| Rail traffic | Support a simple rail path mixed into the transport feed | Support dedicated railway track and railway traffic tables | Rail is supported, but only through the existing COUP-noise transport feed plus adapter logic |
| Terrain | No terrain support | Use DEM and terrain-aware propagation | Optional in `nm5`, required in `nm5_full` |
| Ground absorption | Not available | Support dedicated ground absorption polygons | Supported in `nm5_full` through `ground_absorption.geojson` |
| Source directivity | Not available | Support directivity tables and directional emission data | Supported in `nm5_full` through optional `source_directivity.csv/json` |
| Weather and period settings | Not available | Support period-aware atmospheric settings and richer time-period handling | Supported in `nm5_full` through `atmospheric_settings.csv/json` |
| Receiver mesh and propagation tuning | Fixed internal settings | Many meshing and propagation parameters are available natively | `nm5` uses compatibility defaults; `nm5_full` exposes the main NM5 meshing and propagation controls |
| New areas and default suitability | Best understood as the original compatibility workflow for this service | Can support much richer area-specific modelling when the right inputs are available | Current defaults are okay for rough exploratory maps, but for new areas and more defensible NM5 runs the API should eventually expose or enforce richer inputs such as heights, terrain, and better transport detail |
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

## NM5 Input Contract

The current COUP-noise NM5 adapter has two modes:

- `nm5`: compatibility mode. It accepts the original COUP-noise layer set and fills several NM5 fields internally.
- `nm5_full`: stricter NM5-native mode. It requires richer terrain, ground, and weather inputs and passes more NM5 parameters through to the native scripts.

The adapter does not consume raw OSM files, `.pbf` extracts, Overpass JSON,
shapefiles, or GeoTIFF DEMs directly. It expects CityPyo layers, or equivalent
local fixture files, as GeoJSON, JSON, or CSV files in the layer names below.

| File / layer | Required | Geometry | Role |
| --- | --- | --- | --- |
| `project_area.geojson` | yes | `Polygon` or `MultiPolygon` | Area of interest used to clip the final result |
| `upperfloor.geojson` | yes | `Polygon` or `MultiPolygon` | Building footprints used as propagation obstacles |
| `roads.geojson` | yes | `LineString` or `MultiLineString` | Road and optional rail noise sources |
| `dem.geojson` | required in `nm5_full` | 3D `Point` or `MultiPoint` | Terrain elevation input |
| `ground_absorption.geojson` | required in `nm5_full` | `Polygon` or `MultiPolygon` | Ground acoustic absorption polygons with `G` |
| `atmospheric_settings.csv` or `.json` | required in `nm5_full` | table rows | Period-specific weather and wind rose settings |
| `source_directivity.csv` or `.json` | optional | table rows | Source directivity attenuation spectra |

GeoJSON supplied through CityPyo or local fixtures may be in WGS84
(`EPSG:4326`) or the local projected CRS. The service infers the source CRS
and reprojects the data to `EPSG:25832` before running NM5. If files are
prepared directly for the NM5 runner, use `EPSG:25832` because NM5 expects
metric coordinates.

Building features should contain footprint geometry and, ideally, one usable
height attribute. The adapter accepts direct height fields such as `height`,
`HEIGHT`, `building_height`, `roof_height`, `roof_z`, or `z`. It also accepts
floor-count fields such as `floors`, `storeys`, `stories`, `levels`, or
`num_floors`; those are converted using the configured default floor height.
If no usable value is present, NM5 still runs with `NM5_DEFAULT_BUILDING_HEIGHT`
(`10 m` by default).

Road features should contain line geometry and traffic attributes. The minimum
useful fields for road noise are:

- `car_traffic_daily`
- `truck_traffic_daily`
- `max_speed`

Recommended road fields are:

- `road_type`
- `traffic_settings_adjustable`
- `PVMT`
- `JUNC_DIST`
- `JUNC_TYPE`
- `WAY`
- `SLOPE`

The adapter converts these properties into the NM5 `ROADS` schema with
day/evening/night vehicle classes (`LV_D`, `HGV_D`, speed fields, and related
columns). Missing rich road attributes are filled with internal defaults, but
missing traffic or speed data can make the acoustic result non-representative.

Rail sources are currently represented inside `roads.geojson` by setting
`road_type` to `railroad`. Optional rail fields include `train_speed`,
`TRAINSPD`, `trains_per_hour`, `TDAY`, `NTRACK`, `tracks`, `TRACKSPC`,
`ISTUNNEL`, `tunnel`, `TRANSFER`, `ROUGHNESS`, `IMPACT`, `CURVATURE`,
`BRIDGE`, and `TRAINTYPE`. Sparse rail data is accepted, but the adapter then
uses default train type, speed, track count, track spacing, and frequency.

`dem.geojson` is optional in compatibility mode and required in `nm5_full`.
When present, only 3D point-like features are passed to NM5. Example DEM
coordinates should include elevation as the third ordinate:

```json
[565000.0, 5935000.0, 8.4]
```

`ground_absorption.geojson` contains non-overlapping ground polygons with a `G`
property from `0` hard ground to `1` soft ground:

```json
{
  "G": 0.7
}
```

`atmospheric_settings.csv` can use one row per period. The required columns are
`PERIOD`, `TEMPERATURE`, `PRESSURE`, `HUMIDITY`, `GDISC`, `PRIME2520`, and
`WINDROSE_0` through `WINDROSE_15`. JSON input may also provide `windrose` as a
16-value array. Typical periods are `D`, `E`, and `N`.

```csv
PERIOD,TEMPERATURE,PRESSURE,HUMIDITY,GDISC,PRIME2520,WINDROSE_0,WINDROSE_1,WINDROSE_2,WINDROSE_3,WINDROSE_4,WINDROSE_5,WINDROSE_6,WINDROSE_7,WINDROSE_8,WINDROSE_9,WINDROSE_10,WINDROSE_11,WINDROSE_12,WINDROSE_13,WINDROSE_14,WINDROSE_15
D,15,101325,70,true,false,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5
```

`source_directivity.csv` is optional. If provided, it must contain `DIR_ID`,
`THETA`, `PHI`, `HZ63`, `HZ125`, `HZ250`, `HZ500`, `HZ1000`, `HZ2000`,
`HZ4000`, and `HZ8000`.

`nm5_full` also accepts an optional nested `nm5_settings` object in the task
payload. Supported keys are `receiver_height`, `max_cell_dist`, `road_width`,
`building_buffer`, `max_area`, `skip_cell_no_sources_minimal_distance`,
`fence_negative_buffer`, `iso_surface_in_buildings`,
`export_triangles_geometries`, `reflection_order`, `max_source_distance`,
`max_reflection_distance`, `thread_number`, `diff_vertical`,
`diff_horizontal`, `export_source_id`, `humidity`, `temperature`,
`favourable_occurrences`, `rays_name`, `max_error`, `iso_classes`, and
`result_table_field`.

If OSM is the source data, it must first be transformed into the layer contract
above. Typical mapping is: OSM building footprints to `upperfloor.geojson`,
`height` or `building:levels` to height/floor fields, OSM road centerlines to
`roads.geojson`, `maxspeed` to `max_speed`, and an external or manually
assigned traffic model to `car_traffic_daily` and `truck_traffic_daily`.

## HafenCity Data Sources For NM5 Full

For a defensible HafenCity `nm5_full` run, use official Hamburg sources where
possible and use OSM only as a fallback or geometry enrichment source.

| Need | Recommended source | Notes |
| --- | --- | --- |
| AOI boundary | Hamburg Geoportal or a project-approved HafenCity polygon | Replace the demo rectangle with an approved boundary |
| Building footprints and heights | [3D-Gebäudemodell LoD2-DE Hamburg](https://suche.transparenz.hamburg.de/dataset/3d-gebaeudemodell-lod2-de-hamburg) | CityGML LoD2; derive footprint and `HEIGHT` |
| Alternative cadastral geometry / land use | [ALKIS - ausgewählte Daten Hamburg](https://suche.transparenz.hamburg.de/dataset/alkis-ausgewaehlte-daten-hamburg5) | Includes selected cadastral data, buildings, and actual use classes |
| Road / rail geometry fallback | [Geofabrik Hamburg OSM extract](https://download.geofabrik.de/europe/germany/hamburg.html) | Use `.osm.pbf`, GeoPackage, or Shapefile as raw geometry source; still needs traffic enrichment |
| Road traffic counts | [Verkehrsstärken Hamburg](https://suche.transparenz.hamburg.de/dataset/35b7dfe1-02c4-4cd1-92f8-0548cb92e2e8) and the [Kfz traffic-strength page](https://www.hamburg.de/politik-und-verwaltung/behoerden/bvm/verkehrsstaerken-kfz-193324) | Provides DTV/DTVw and WFS/Excel resources; map counts to road segments |
| Terrain | [Digitales Höhenmodell Hamburg DGM 1](https://suche.transparenz.hamburg.de/dataset/digitales-hoehenmodell-hamburg-dgm-1) | Convert raster/grid data to 3D DEM points for `dem.geojson` |
| Ground absorption / land cover | [ALKIS actual use](https://suche.transparenz.hamburg.de/dataset/alkis-ausgewaehlte-daten-hamburg5) and [Copernicus Urban Atlas 2021](https://land.copernicus.eu/en/products/urban-atlas/urban-atlas-2021) | Convert land-use classes to NM5 `G` values; inspect hardscape/water/green areas manually for HafenCity |
| Weather / wind rose | [DWD Climate Data Center](https://www.dwd.de/EN/ourservices/cdc/cdc_ueberblick-klimadaten_en.html) | Use Hamburg-area stations for temperature, humidity, pressure, wind direction and wind speed statistics |
| Public transport rail schedules | [hvv GTFS](https://suche.transparenz.hamburg.de/dataset/hvv-fahrplandaten-gtfs-april-2026-bis-dezember-2026) | Can estimate U/S/regional train frequencies where relevant; still needs mapping to NM5 train types |
| Railway infrastructure fallback | [OpenRailwayMap / OSM](https://wiki.openstreetmap.org/wiki/OpenRailwayMap) | Useful for track geometry and tags; validate before acoustic use |

Directivity is usually not a public city dataset. For normal road sources,
omnidirectional/direct model defaults are usually used. For rail, NM5 can use
its built-in train directivity defaults unless a project-specific directivity
table is supplied.

## Data Quality Guidance

This is still intentionally practical rather than exhaustive. The goal is to show what data is merely enough to run and what data is actually useful if you want NM5 to behave well on a new area.

| Layer | Minimum needed to run | Strongly recommended for NM5 | What happens if data is missing or sparse |
| --- | --- | --- | --- |
| Buildings (`upperfloor`) | Building polygons | Height-related attributes such as explicit building height, roof height, or floor count | Legacy still runs with geometry only. NM5 derives height when possible and otherwise falls back to a default building height |
| Roads (`roads`) | Line geometry plus enough attributes for road noise to exist at all | `road_type`, `car_traffic_daily`, `truck_traffic_daily`, `max_speed`, and where available `PVMT`, `JUNC_DIST`, `JUNC_TYPE`, `WAY`, `SLOPE` | Missing rich road attributes do not necessarily stop NM5, but the adapter fills several values internally, which can make results less area-specific |
| Rail in transport feed | Rail geometries identified in the same transport layer | `road_type=railroad` and, where available, train speed, train frequency, track count, spacing, tunnel or bridge flags, roughness, transfer, impact, curvature, and train type | Rail can still run through adapter defaults and heuristics, but sparse source rail data increases the chance of non-representative results |
| Project area (`project_area`) | Polygon geometry | A clipping area that matches the intended study area | Without it, COUP-noise cannot clip the final result to the requested area |
| Terrain (`dem`) | Not required for `legacy` or compatibility `nm5`; required for `nm5_full` | A high-quality DEM layer for HafenCity terrain, bridges, embankments, and quay edges | If no DEM is present, compatibility `nm5` still runs but terrain effects are absent; `nm5_full` rejects the run |
| Ground absorption (`ground_absorption`) | Required for `nm5_full` | Non-overlapping polygons with `G` values derived from land use or surface material | Missing ground absorption causes `nm5_full` to reject the run |
| Atmospheric settings (`atmospheric_settings`) | Required for `nm5_full` | Period-specific temperature, pressure, humidity, and 16-sector wind rose | Missing atmospheric settings causes `nm5_full` to reject the run |
| Directivity (`source_directivity`) | Optional | Project-specific source directivity spectra when sources reference `DIR_ID` values | If absent, NM5 uses its default behavior, including built-in rail directivity where applicable |

For quick exploratory maps, the current defaults are usually acceptable. For new areas where you want more defensible NM5 output, richer source data is strongly preferred over relying on adapter defaults.

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
- `NOISE_ENGINE=legacy|nm5|nm5_full|auto`
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
- `NOISE_ENGINE=nm5_full` uses the same runner with stricter NM5-native input requirements and exposed advanced settings

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
