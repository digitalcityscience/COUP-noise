#!/bin/bash

curl -X POST http://localhost:5001/task -H 'Content-type: application/json' \
    -d '{"city_pyo_user": "2180cc50b1b3b639c145e87204ebd1af"  , "traffic_settings": {"max_speed": 50,
        "traffic_volume_percent": 80}, "result_format": "png"}'
