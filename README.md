# Noise Simulation

The noise module is used for investigating traffic noise patterns. The goal of the module is to identify the areas of the neighborhood exposed to high noise levels. The noise simulation is adapted from the software [NoiseModelling](https://noise-planet.org/noisemodelling.html), a free and open-source tool (GPL 3) for producing environmental noise maps
using a simplified implementation of the French national method NMPB-08.

The software is developed by the French Institute of Science and Technology for Transport, Development and Networks (Ifsttar).

### Simulation Inputs

The inputs for the simulation are buildings and streets. The buildings are represented as 2D building footprints saved as a GeoJSON.

For the street network, a GeoJSON of the streets and rails is needed that includes values for the planned traffic volume and traffic speed. Custom inputs for traffic quota and max speed will be applied to all roads with a property traffic_settings_adjustable: true

#### Traffic Quota

Volume of motorized traffic (cars, trucks). Selecting 100% shows the traffic volume according to current planning assumptions (predicted traffic volume). Selecting 25%, for example, shows 25% of the planned traffic volume specified in the streets geojson.

#### Max speed

Max speed value in [km/h] that will be applied to the streets.

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

## Start

1. ``docker-compose build``
2. ``docker-compose up -d``

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
   "max_speed": 42, "traffic_quota": 40, "result_format": "png",
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
