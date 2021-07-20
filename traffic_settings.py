import json
from config_loader import get_config


traffic_settings = {
    "full_traffic_50": {
        "max_speed": 50,
        "traffic_percent": 0.75
    },
    "full_traffic_30": {
        "max_speed": 30,
        "traffic_percent": 0.75
    },
    "reduced_traffic_50": {
        "max_speed": 50,
        "traffic_percent": 0.75
    },
    "reduced_traffic_30": {
        "max_speed": 30,
        "traffic_percent": 0.75
    },
    "half_traffic_50": {
        "max_speed": 50,
        "traffic_percent": 0.50
    },
    "half_traffic_30": {
        "max_speed": 30,
        "traffic_percent": 0.50
    },
    "limited_traffic_50": {
        "max_speed": 50,
        "traffic_percent": 0.25
    },
    "limited_traffic_30": {
        "max_speed": 30,
        "traffic_percent": 0.25
    },
    "no_traffic": {
        "max_speed": 30,
        "traffic_percent": 0.0
    }
}


# opens a json from path
def open_geojson(path):
    with open(path) as f:
        return json.load(f)


def get_traffic_settings(key):
    scenario = traffic_settings[key]

    return scenario['max_speed'], scenario['traffic_percent']


if __name__ == "__main__":
    for settings_key in traffic_settings.keys():

        max_speed, traffic_quota = get_traffic_settings(settings_key)

        local_road_design =  open_geojson(get_config()['NOISE_SETTINGS']['INPUT_JSON_ROAD_NETWORK'])

        for feature in local_road_design['features']:
            # only for local streets inside grasbrook (hauptsammelstrassen)
            if feature['properties']['name'] == 'hauptsammelstrasse':
                feature['properties']['max_speed'] = max_speed
                feature['properties']['car_traffic_daily'] = int(feature['properties']['car_traffic_daily'] * traffic_quota)
                feature['properties']['truck_traffic_daily'] =  int(feature['properties']['truck_traffic_daily'] * traffic_quota)

        # save geojson
        file_path = get_config()['NOISE_SETTINGS']['INPUT_JSON_ROAD_NETWORK'][:-5]
        file_path += "_" + settings_key + ".json"

        with open(file_path, 'wb') as f:
            json.dump(local_road_design, f)












