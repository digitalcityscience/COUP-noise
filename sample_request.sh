#!/bin/bash

# PLEASE SPECIFY YOUR AUTH TOKEN AND CITYPYO USER ID BELOW

curl --location --request POST 'http://localhost:5001/task' \
--header 'Content-Type: application/json' \
--header 'Authorization: Basic WU9VUl9JRDpZT1VSX1BBU1NXT1JE' \
--data-raw '{
   "max_speed": 10, "traffic_quota": 0.5, "wall_absorption": 0.69, "result_format": "png",
   "city_pyo_user": "d71c87c15ec68e64bf6bc65382852b05"
}'