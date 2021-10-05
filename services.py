import json
import hashlib
import re

import noise_analysis.cityPyo as cp
from noise_analysis.noisemap import noise_calculation

cityPyo = cp.CityPyo() ## put cityPyo container here


def get_calculation_input(complex_task):
    # hash noise scenario settings
    calculation_settings = get_calculation_settings(complex_task)
    scenario_hash = hash_dict(calculation_settings)

    # get buildings and roads
    buildings = get_buildings_geojson_from_cityPyo(complex_task["city_pyo_user"])
    roads = get_roads_geojson_from_cityPyo(complex_task["city_pyo_user"])
    
    # hash buildings and roads geojson
    hash = hash_dict({"buildings": buildings, "roads": roads})

    return scenario_hash, hash, calculation_settings, buildings, roads


def calculate_and_return_result(scenario, buildings, roads):
    return noise_calculation(scenario, buildings, roads)


def get_calculation_settings(scenario):
    print("scenario", scenario)

    return {
        "traffic_settings": {"max_speed": scenario["max_speed"], "traffic_quota": scenario["traffic_quota"]},
        "result_format": scenario["result_format"]
    }

def get_buildings_geojson_from_cityPyo(cityPyo_user_id):
    return cityPyo.get_buildings_for_user(cityPyo_user_id)

def get_roads_geojson_from_cityPyo(cityPyo_user_id):
    return cityPyo.get_roads_for_user(cityPyo_user_id)


def hash_dict(dict_to_hash):
    dict_string = json.dumps(dict_to_hash, sort_keys=True)
    hash_buildings = hashlib.md5(dict_string.encode())

    return hash_buildings.hexdigest()

def is_valid_md5(checkme):
    if type(checkme) == str:
        if re.findall(r"([a-fA-F\d]{32})", checkme):
            return True

    return False

def get_cache_key_compute_task(**kwargs):
    return kwargs["scenario_hash"] + "_" + kwargs["buildings_and_roads_hash"]

