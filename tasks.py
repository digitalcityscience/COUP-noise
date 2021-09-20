from celery import signals
from celery.utils.log import get_task_logger

from cache import Cache
from mycelery import app
from services import get_buildings_geojson_from_cityPyo, hash_dict, get_result, get_cache_key, is_valid_md5, get_calculation_input

logger = get_task_logger(__name__)
cache = Cache()


@app.task()
def compute_task(scenario_hash, buildings_hash, scenario, buildings) -> dict:
    print("computing for scenario hash %s and building hash %s" %
          (scenario_hash, buildings_hash))

    return get_result(scenario, buildings)


@app.task()
def receive_task(complex_task: dict) -> dict:
    # hash noise scenario settings
    calculation_input = get_calculation_input(complex_task)
    scenario_hash = hash_dict(calculation_input)

    # hash buildings geojson
    buildings = get_buildings_geojson_from_cityPyo(
        complex_task["city_pyo_user"])
    buildings_hash = hash_dict(buildings)

    # create key of unique calculation constellation of scenario settings and buildings
    key = scenario_hash + "_" + buildings_hash

    # Check cache. If cached, return result from cache.
    result = cache.retrieve(key=key)
    print("result from cache %s" % result)
    if not result == {}:
        return result

    result = compute_task.delay(
        scenario_hash, buildings_hash, calculation_input, buildings)

    return result


@signals.task_postrun.connect
def task_postrun_handler(task_id, task, *args, **kwargs):
    state = kwargs.get('state')
    args = kwargs.get('args')
    result = kwargs.get('retval')

    # only cache the "compute_task" task where the first 2 arguments are hashes
    if is_valid_md5(args[0]) and is_valid_md5(args[1]):
        # Cache only succeeded tasks
        if state == "SUCCESS":
            key = get_cache_key(scenario_hash=args[0], buildings_hash=args[1])
            cache.save(key=key, value=result)
            print("cached result with key %s" % key)
