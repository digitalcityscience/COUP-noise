#!/bin/bash

# Default local demo credentials:
# auth token = dev:dev
# city_pyo_user = demo

curl --location --request POST 'http://localhost:5001/task' \
--header 'Content-Type: application/json' \
--header 'Authorization: Basic ZGV2OmRldg==' \
--data-raw '{
   "max_speed": 10, "traffic_quota": 0.5, "wall_absorption": 0.69, "result_format": "png",
   "city_pyo_user": "demo"
}'
