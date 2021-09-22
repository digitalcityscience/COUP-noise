import json
import hashlib
import re
import geopandas

from noise_analysis.cityPyo import CityPyo
from celery import group
from celery.result import GroupResult

import noise_analysis.cityPyo as cp
from noise_analysis.noisemap import noise_calculation

cityPyo = cp.CityPyo() ## put cityPyo container here


def get_calculation_input(complex_task):
    # hash noise scenario settings
    calculation_settings = get_calculation_settings(complex_task)
    scenario_hash = hash_dict(calculation_settings)

    # hash buildings geojson
    buildings = get_buildings_geojson_from_cityPyo(complex_task["city_pyo_user"])
    buildings_hash = hash_dict(buildings)

    return scenario_hash, buildings_hash, calculation_settings, buildings

def calculate_and_return_result(scenario, buildings):
    return noise_calculation(scenario, buildings)


def get_calculation_settings(scenario):
    print("scenario", scenario)

    return {
        "traffic_settings": {"max_speed": scenario["max_speed"], "traffic_quota": scenario["traffic_quota"]},
        "result_format": scenario["result_format"]
    }

def get_buildings_geojson_from_cityPyo(cityPyo_user_id):
    return cityPyo.get_buildings_for_user(cityPyo_user_id)


def hash_dict(dict_to_hash):
    dict_string = json.dumps(dict_to_hash, sort_keys=True)
    hash_buildings = hashlib.md5(dict_string.encode())

    return hash_buildings.hexdigest()

def is_valid_md5(checkme):
    if type(checkme) == str:
        if re.findall(r"([a-fA-F\d]{32})", checkme):
            return True

    return False

def get_cache_key(**kwargs):
    return kwargs["scenario_hash"] + "_" + kwargs["buildings_hash"]

