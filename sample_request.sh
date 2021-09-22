#!/bin/bash

curl -X POST http://localhost:5001/task -H 'Content-type: application/json' \
    -d '{"city_pyo_user": "90af2ace6cb38ae1588547c6c20dcb36", "max_speed": 50,
        "traffic_quota": 0.78, "result_format": "png"}'
