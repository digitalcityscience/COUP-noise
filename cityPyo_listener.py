import requests
import json
import os
import time

from noise_analysis.noisemap import perform_noise_calculation

known_hashes = {}

cwd = os.path.dirname(os.path.abspath(__file__))
cityPyoUrl = 'http://localhost:5000/'


# login to cityPyo using the local user_cred_file
# saves the user_id as global variable
def get_city_pyo_user_id(user_cred):
    print("login in to cityPyo")
    response = requests.post(cityPyoUrl + "login", json=user_cred)

    return response.json()['user_id']

# get the noise scenarios from cityPyo
def get_noise_scenarios():
    data = {
        "userid":user_id,
        "layer":"noise_scenario"
        }

    try:
        response = requests.get(cityPyoUrl + "getLayer", json=data)

        if not response.status_code == 200:
            print("could not get from cityPyo")
            print("Error code", response.status_code)
            # todo raise error and return error
            return {}
    # exit on request execption (cityIO down)
    except requests.exceptions.RequestException as e:
        print("CityPyo error. " + str(e))

        return None

    return response.json()



# sends the response to cityPyo, creating a new file as myHash.json
def send_response_to_cityPyo(scenario_hash, res):
    print("\n sending to cityPyo")

    try:
        query = scenario_hash
        data = {
            "userid": user_id,
            "data": res
        }
        response = requests.post(cityPyoUrl + "addLayerData/" + query, json=data)

        if not response.status_code == 200:
            print("could not post to cityPyo")
            print("Error code", response.status_code)
        else:
            print("\n")
            print("result send to cityPyo.", "Result hash is: ", scenario_hash)
            print("waiting for new input...")
        # exit on request exception (cityIO down)
    except requests.exceptions.RequestException as e:
        print("CityPyo error. " + str(e))



# Compute loop to run eternally
if __name__ == "__main__":
    # load cityPyo users from config
    with open(cwd + "/" + "cityPyoUser.json", "r") as city_pyo_users:
        users = json.load(city_pyo_users)

    # get user id's to eternally check for new scenario data for each user
    user_ids = []
    for user_cred in users["users"]:
        user_ids.append(get_city_pyo_user_id(user_cred))

    for user_id in user_ids:
        # init known hashes for user
        known_hashes[user_id] = {}

    # loop forever
    while True:
        for user_id in user_ids:
            # compute results for each scenario
            scenarios = get_noise_scenarios()
            for scenario_id in scenarios.keys():
                compute = False
                try:
                    old_hash = known_hashes[user_id][scenario_id]
                    if old_hash != scenarios[scenario_id]["hash"]:
                        # new hash, recomputation needed
                        compute = True
                except KeyError:
                    # no result hash known for scenario_id. Compute result.
                    compute = True

                if compute:
                    result = perform_noise_calculation(scenarios[scenario_id])
                    send_response_to_cityPyo(scenarios[scenario_id]["hash"], result)
                    known_hashes[user_id][scenario_id] = scenarios[scenario_id]["hash"]

            time.sleep(1)