#!/bin/bash

curl -X POST http://localhost:5000/grouptasks -H 'Content-type: application/json' \
    -d '{"tasks": [{"max_speed": 50,
        "traffic_volume_percent": 80, "hash":"34534536"}]}'