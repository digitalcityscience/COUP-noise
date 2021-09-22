import time
import requests
import os
import json
import geopandas

cwd = os.getcwd()


class CityPyo:
    """Class to handle CityPyo communication and users
        - Logs in all users listed in config and saves their user ids.
        - Gets data from cityPyo
        - Posts data to cityPyo
    """
    def __init__(self):
        self.url = os.getenv('CITY_PYO')
        if not self.url:
            raise Exception("Please specify CITY_PYO environment variable")
        

    # login to cityPyo using the local user_cred_file
    # saves the user_id as global variable
    def login_and_get_user_id(self, user_cred):
        print("login in to cityPyo")
        response = requests.post(self.url + "/login", json=user_cred)
        return response.json()['user_id']


    # returns buildings geometries as geojson (properties are ignored, as irrelevant for noise calc)
    def get_buildings_for_user(self, user_id):
        """ # prioritize a buildings.json
        buildings = self.get_layer_for_user(user_id, "upperfloor")
        if not buildings:
            # else try upperfloor """
        # HOTFIX: use upperfloor as "buildings.json" seems to cause problems to H2GIS
        buildings = self.get_layer_for_user(user_id, "upperfloor")
        if not buildings:
            # no buildings no calculation :p
            raise FileNotFoundError("could not find buildings on %s for user %s" % (self.url, self.user_id))

        # return geojson containing only geometries, converted to utm
        return self.reproject_to_utm_and_delete_all_properties(buildings)


    def get_layer_for_user(self, user_id, layer_name, recursive_iteration=0):
        data = {
            "userid": user_id,
            "layer": layer_name
        }

        try:
            response = requests.get(self.url + "/getLayer", json=data)

            if response.status_code == 200:
                return response.json()
            else:
                print("could not get from cityPyo")
                print("wanted to get layer: ", layer_name)
                print("Error code", response.status_code)
                return None
        # exit on request exception (cityIO down)
        except requests.exceptions.RequestException as e:
            print("CityPyo error. " + str(e))

            if recursive_iteration > 10:
                raise requests.exceptions.RequestException

            time.sleep(30 * recursive_iteration)
            recursive_iteration += 1

            return self.get_layer_for_user(user_id, layer_name, recursive_iteration)

    def reproject_to_utm_and_delete_all_properties(self, geojson) -> dict:
        gdf_cols = ["geometry"]

        gdf = geopandas.GeoDataFrame.from_features(geojson["features"], crs="EPSG:4326", columns=gdf_cols)
        gdf = gdf.to_crs("EPSG:25832")  # reproject to utm coords

        print(gdf)
        print(json.loads(gdf.to_json())["features"][0])
        return json.loads(gdf.to_json())