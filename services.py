import json
import hashlib
import os
import re

from noise_analysis.calculation_settings import CalculationSettings

cityPyo = None


def resolve_noise_engine():
    return os.getenv("NOISE_ENGINE", "legacy").lower()


def get_citypyo():
    global cityPyo
    if cityPyo is None:
        import noise_analysis.cityPyo as cp

        cityPyo = cp.CityPyo()
    return cityPyo


def get_calculation_input(complex_task):
    # hash noise scenario settings
    calculation_settings = get_calculation_settings(complex_task)
    scenario_hash = hash_dict(calculation_settings)

    # get buildings and roads
    buildings = get_buildings_geojson_from_cityPyo(complex_task["city_pyo_user"])
    roads = get_roads_geojson_from_cityPyo(complex_task["city_pyo_user"])
    dem = get_dem_geojson_from_cityPyo(complex_task["city_pyo_user"], required=False)
    
    # hash all geometry inputs that can affect a run
    hash = hash_dict({"buildings": buildings, "roads": roads, "dem": dem})

    return scenario_hash, hash, calculation_settings, buildings, roads, complex_task["city_pyo_user"]


def calculate_and_return_result(scenario, buildings, roads, cityPyo_user):
    normalized_scenario = CalculationSettings.from_mapping(
        scenario,
        default_noise_engine=resolve_noise_engine(),
    )
    normalized_payload = normalized_scenario.to_dict()
    engine = normalized_scenario.noise_engine

    if engine == "legacy":
        from noise_analysis.noisemap import noise_calculation as legacy_noise_calculation
        return legacy_noise_calculation(normalized_payload, buildings, roads, cityPyo_user)

    if engine == "nm5":
        from noise_analysis.nm5_runner import noise_calculation as nm5_noise_calculation
        return nm5_noise_calculation(normalized_payload, buildings, roads, cityPyo_user)

    if engine == "auto":
        try:
            from noise_analysis.nm5_runner import noise_calculation as nm5_noise_calculation
            return nm5_noise_calculation(normalized_payload, buildings, roads, cityPyo_user)
        except FileNotFoundError:
            from noise_analysis.noisemap import noise_calculation as legacy_noise_calculation
            return legacy_noise_calculation(normalized_payload, buildings, roads, cityPyo_user)

    raise ValueError("Unsupported NOISE_ENGINE value: %s" % engine)


def get_calculation_settings(scenario):
    return CalculationSettings.from_mapping(
        scenario,
        default_noise_engine=resolve_noise_engine(),
    ).to_dict()

def get_buildings_geojson_from_cityPyo(cityPyo_user_id):
    return get_citypyo().get_buildings_for_user(cityPyo_user_id)

def get_roads_geojson_from_cityPyo(cityPyo_user_id):
    return get_citypyo().get_roads_for_user(cityPyo_user_id)

def get_dem_geojson_from_cityPyo(cityPyo_user_id, required=False):
    return get_citypyo().get_dem_for_user(cityPyo_user_id, required=required)


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
