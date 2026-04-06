# Noise Simulation

The noise module is used for investigating traffic noise patterns. The goal of the module is to identify the areas of the neighborhood exposed to high noise levels. The noise simulation is adapted from the software [NoiseModelling](https://noise-planet.org/noisemodelling.html), a free and open-source tool (GPL 3) for producing environmental noise maps
using a simplified implementation of the French national method NMPB-08.

The software is developed by the French Institute of Science and Technology for Transport, Development and Networks (Ifsttar).

In general each simulation module (noise, wind, water, ..) is realized by a celery-based app using 3 containers each: api,worker, redis. The api container excepts requests and creates tasks in the redis db. Workers look for tasks in the redis db, calculate result and publish it in redis. Results (also cached ones) can be accessed via the api container that get’s the result from the redis db.

### Simulation Inputs

The inputs for the simulation are buildings and streets. The buildings are represented as 2D building footprints saved as a GeoJSON.

For the street network, a GeoJSON of the streets and rails is needed that includes values for the planned traffic volume and traffic speed. Custom inputs for traffic quota and max speed will be applied to all roads with a property traffic_settings_adjustable: true

#### Traffic Quota

Volume of motorized traffic (cars, trucks). Selecting 100% shows the traffic volume according to current planning assumptions (predicted traffic volume). Selecting 25%, for example, shows 25% of the planned traffic volume specified in the streets geojson.

#### Max speed

Max speed value in [km/h] that will be applied to the streets.

#### Wall absorption

["wall_absorption"] float value between 0-1 to indicate wall absorption qualities. The higher the more absorption.

#### Grasbrook use case

For Grasbrook, this file is generated from the BIM to geospatial conversion
process.  We generated the street network manually, based on drawings provided for the Grasbrook. Default values are used for additional street parameters, such as surface types.

### Results

Noise levels are divided into 8 categories. Specified in the "idiso" property.

EU treshold for "relevant" noise is 55db

 < 45 dB(A) ’ WHERE IDISO=0

 45 <> 50 dB(A) ’ WHERE IDISO=1

 50 <> 55 dB(A) ’ WHERE IDISO=2

 55 <> 60 dB(A) ’ WHERE IDISO=3

 60 <> 65 dB(A) ’ WHERE IDISO=4

 65 <> 70 dB(A) ’ WHERE IDISO=5

 70 <> 75 dB(A) ’ WHERE IDISO=6

 '>' 75 dB(A) ’ WHERE IDISO=7

# Technical Setup

This project uses Celery to process tasks asynchronously.
Using Celery, this tech stack offers high scalability.

For ease of installation,
Redis is used here. Through Redis the tasks are distributed to the workers and also the results are stored on Redis.

Wrapped with an API (Flask), the stack provides an interface for other services.
The whole thing is then deployed with Docker Compose.

## Design

The tasks are commissioned via a endpoint (``POST, /task``) (see Usage).
The client receives a response with a Task-Id .
Using polling, the client can query the status of a Task (``GET, /tasks/<task_id>``).

## Caching

After a task has been successfully processed, the result is cached on Redis along with the input parameters. The result is then returned when a (different) task has the same input parameters and is requested.

## TechStack

- Python
- Celery
- Redis
- Flask
- Docker

## Environment Variables

Specify these in your docker-compose.yml

- REDIS_HOST=redis  #  the redis container or URL of your redis endpoint
- REDIS_PORT=6379
- REDIS_PASS=YOUR_PASS
- CITY_PYO=YOUR_CITYO_URL # host your own citypyo or use the HCU one
- CLIENT_ID=YOUR_ID # Protect your noise api by basic auth
- CLIENT_PASSWORD=YOUR_PASSWORD  # Protect your noise api by basic auth

For local testing, `docker-compose.yml` now ships with safe defaults:

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

1. ``docker-compose build``
2. ``docker-compose up -d``

For the built-in local dataset, submit tasks with ``city_pyo_user=demo`` and use ``dev`` / ``dev`` as the basic-auth credentials.

## Visual Assessment

The repository now supports two calculation engines behind the same API:

- ``NOISE_ENGINE=legacy`` uses the existing embedded engine
- ``NOISE_ENGINE=nm5`` uses the new NoiseModelling 5 runner

For honest comparison, run them explicitly one after the other. Do **not** use ``NOISE_ENGINE=auto`` for visual assessment because it may fall back to legacy if the NM5 runner is unavailable.

### NM5 Status

The current NM5 migration slice is **not the full migration** yet:

- roads are supported
- railroad features are supported through generated ``RAIL_SECTIONS`` and ``RAIL_TRAFFIC`` inputs
- rail parameters still use heuristics when the source data only contains generic railway tags
- DEM is now supported when a ``dem.geojson`` layer is available for the selected CityPyo user
- ground absorption is still not wired yet
- building heights are derived from source properties when possible and otherwise fall back to a default height

### Recommended Compare Workflow

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

The PNG metadata is saved next to the image as ``.json``. With ``--write-geojson`` and ``--write-map`` the tool also writes ``.geojson`` and ``.map.html`` files for inspection on a basemap.

### Why Separate Queues Matter

The Celery queue name can now be set with ``CELERY_QUEUE``. Use different values such as ``noise_legacy`` and ``noise_nm5`` if you compare engines. This prevents tasks from being consumed by the wrong worker set.

## Usage

### Create a Task

specify your inputs.

Results will be returned as geojson by default. If requested results are returned as png encoded as base-64 string.

> "max_speed" in km/h
>
> "traffic_quota" in %
>
> "city_pyo_user": YOUR_CITYPYO_USER_ID
>
> "result_format": "geojson" | "png"

Request:

```
curl --location --request POST 'http://localhost:5001\task' \
--header 'Content-Type: application/json' \
--header 'Authorization: Basic YOUR_AUTH_TOKEN' \
--data-raw '{
   "max_speed": 42, "traffic_quota": 40, "wall_absorption": 0.23", "result_format": "png",
   "city_pyo_user": YOUR_USER
}
```

Response:

```json
{
  "taskId": "110fbbca-cd8c-4e57-9cdc-8a02cdc71ee7"
}
```

### Get Task-Result

Request:

```
curl -X GET http://localhost:5001/tasks/110fbbca-cd8c-4e57-9cdc-8a02cdc71ee7 --header 'Authorization: Basic YOUR_AUTH_TOKEN' \
```

Response:

*result format = geojson*

```json
 {
  "resultReady": true,
  "taskId": "98b34861-ba4d-441e-8493-05e465a998c1",
  "taskState": "SUCCESS",
  "taskSucceeded": true,
  "result": {
    "features": [
{
        "geometry": {
          "coordinates": [
            [
              [
                10.015742554695208,
                53.52879082871648
              ],
              ...
            ]
          ],
          "type": "Polygon"
        },
        "id": "192",
        "properties": {
          "cell_id": 0,
          "idiso": 3
        },
        "type": "Feature"
      },
	,...
     ]
   }
}
```

*result format = png*

```json
{

 "resultReady": true,
  "taskId": "98b34861-ba4d-441e-8493-05e465a998c1",
  "taskState": "SUCCESS",
  "taskSucceeded": true,
  "result": {
    "bbox_coordinates":  spatial coordinates of the pngs 4 corners,
    "bbox_sw_corner": the coordinates of the south west corner of the png
    "image_base64_string": "iVBORw0KGgoAAAANSUhEUgAABVQAAAVGCAAAAABUcW9oAACJCklEQVR4nO2d17ajOBQFD76h5/+/tqOZB8AGlKUjkKBqrZm+ToAJ5a3IMAoA...."

}
```

Response:

```json
{
  "result": {
    "bbox_coordinates": [
      [
        10.000852899017993,
        53.535469701309005
      ],
      [
        10.021210412010495,
        53.535297575247135
      ],
      [
        10.020915561498251,
        53.5230399813127
      ],
      [
        10.000563923844467,
        53.52321203082786
      ],
      [
        10.000852899017993,
        53.535469701309005
      ]
    ],
    "bbox_sw_corner": [
      [
        10.000563923844467,
        53.52321203082786
      ]
    ],
    "image_base64_string": "iVBORw0KGgoAAAANSUhEUgAABVQAAAVGCAAAAABUcW9oAACJCklEQVR4nO2d17ajOBQFD76h5/+/tqOZB8AGlKUjkKBqrZm+ToAJ5a3IMAoA" 
}
```

## Commands

### Start worker

``celery -A tasks worker --loglevel=info``

### Monitoring Redis

List Tasks:

- ``redis-cli -h HOST -p PORT -n DATABASE_NUMBER llen QUEUE_NAME``

List Queues:

- ``redis-cli -h HOST -p PORT -n DATABASE_NUMBER keys \*``

## How does it work?

### CityPyo

CityPyo is a file database providing the buildings and streets geojsons that are the basic calculation inputs. The script automatically connects to CityPyo to obtain these files for the specified user.

### Apply request settings

The obtained streets geojson will be modified by setting the "max_speed" and "traffic_quota" values specified in the request, before performing the calculation.

### Noise Modelling

Based on the IFSTTAR NoiseModelling software.

And run in "python mode"  via psycopg2 , as described [here](https://github.com/Universite-Gustave-Eiffel/NoiseModelling/blob/master_stale/wiki/11-Scripting-with-Python.md)

Each worker starts a h2gis instance in a subprocess, performs the calculation there and terminates the h2gis instance again.
