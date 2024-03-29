from celery import signals
from celery.utils.log import get_task_logger

from cache import Cache
from celery_app import app
from services import calculate_and_return_result, get_cache_key_compute_task, is_valid_md5

logger = get_task_logger(__name__)
cache = Cache()


@app.task()
def compute_task(scenario_hash, buildings_and_roads_hash, scenario, buildings, roads, cityPyo_user) -> dict:
    # create key of unique calculation constellation of scenario settings and buildings
    key = scenario_hash + "_" + buildings_and_roads_hash
    
    # Check cache. If cached, return result from cache.
    result = cache.retrieve(key=key)
    print("key %s" % key)
    print("result from cache %s" % result)
    if not result == {}:
        return result

    print("computing for scenario hash %s and building_and_roads hash %s" %
          (scenario_hash, buildings_and_roads_hash))

    return calculate_and_return_result(scenario, buildings, roads, cityPyo_user)


@signals.task_postrun.connect
def task_postrun_handler(task_id, task, *args, **kwargs):
    state = kwargs.get('state')
    args = kwargs.get('args')
    result = kwargs.get('retval')

    # only cache the "compute_task" task where the first 2 arguments are hashes
    if is_valid_md5(args[0]) and is_valid_md5(args[1]):
        # Cache only succeeded tasks
        if state == "SUCCESS":
            key = get_cache_key_compute_task(scenario_hash=args[0], buildings_and_roads_hash=args[1])
            cache.save(key=key, value=result)
            print("cached result with key %s" % key)
