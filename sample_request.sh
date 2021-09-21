#!/bin/bash

curl -X POST http://localhost:5001/task -H 'Content-type: application/json' \
    -d '{"city_pyo_user": "90af2ace6cb38ae1588547c6c20dcb36"  , "traffic_settings": {"max_speed": 50,
        "traffic_volume_percent": 80}, "result_format": "png"}'
