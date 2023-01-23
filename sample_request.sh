#!/bin/bash

# PLEASE SPECIFY YOUR AUTH TOKEN AND CITYPYO USER ID BELOW

curl --location --request POST 'http://localhost:5001/task' \
--header 'Content-Type: application/json' \
--header 'Authorization: Basic WU9VUl9JRDpZT1VSX1BBU1NXT1JE' \
--data-raw '{
   "max_speed": 42, "traffic_quota": 40, "result_format": "png",
   "city_pyo_user": "YOUR CITY PYO USER ID"
}'