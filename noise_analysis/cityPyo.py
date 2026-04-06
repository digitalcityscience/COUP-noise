import json
import os
import re
import time
from pathlib import Path

import geopandas
import requests

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
        self.local_root = self._resolve_local_root(self.url)

    def _resolve_local_root(self, location):
        if location.startswith("file://"):
            local_root = Path(location[7:]).expanduser()
        else:
            candidate = Path(location).expanduser()
            if not candidate.exists():
                return None
            local_root = candidate

        if not local_root.exists():
            raise FileNotFoundError("CITY_PYO local fixture path does not exist: %s" % local_root)
        if not local_root.is_dir():
            raise NotADirectoryError("CITY_PYO local fixture path is not a directory: %s" % local_root)

        return local_root


    # login to cityPyo using the local user_cred_file
    # saves the user_id as global variable
    def login_and_get_user_id(self, user_cred):
        if self.local_root:
            return user_cred.get("user_id") or user_cred.get("userid") or "demo"
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
            raise FileNotFoundError("could not find buildings on %s for user %s" % (self.url, user_id))

        # keep properties so the NM5 adapter can derive building heights
        return self.reproject_to_utm(buildings, keep_properties=True)


    # returns roads geojson 
    def get_roads_for_user(self, user_id):
        roads = self.get_layer_for_user(user_id, "roads")
        if not roads:
            # no roads no calculation :p
            raise FileNotFoundError("could not find roads on %s for user %s" % (self.url, user_id))

        # return geojson containing only geometries, converted to utm
        return self.reproject_to_utm(roads, keep_properties=True)


    def get_project_area_for_user(self, user_id):
        project_area = self.get_layer_for_user(user_id, "project_area")
        if not project_area:
            raise FileNotFoundError("could not find project_area on %s for user %s" % (self.url, user_id))

        return self.reproject_to_utm(project_area, keep_properties=True)


    def get_dem_for_user(self, user_id, required=False):
        dem = self.get_layer_for_user(user_id, "dem", quiet=not required)
        if not dem:
            if required:
                raise FileNotFoundError("could not find dem on %s for user %s" % (self.url, user_id))
            return None

        return self.reproject_to_utm(dem, keep_properties=True)


    def _local_layer_paths(self, user_id, layer_name):
        return [
            self.local_root / str(user_id) / (layer_name + ".geojson"),
            self.local_root / (layer_name + ".geojson"),
        ]


    def _load_local_layer(self, user_id, layer_name, quiet=False):
        for layer_path in self._local_layer_paths(user_id, layer_name):
            if layer_path.exists():
                with layer_path.open(encoding="utf-8") as file_handle:
                    return json.load(file_handle)

        if not quiet:
            print("could not get from local CityPyo fixtures")
            print("wanted to get layer: ", layer_name)
            print("searched in", [str(path) for path in self._local_layer_paths(user_id, layer_name)])
        return None


    def get_layer_for_user(self, user_id, layer_name, recursive_iteration=0, quiet=False):
        if self.local_root:
            return self._load_local_layer(user_id, layer_name, quiet=quiet)

        data = {
            "userid": user_id,
            "layer": layer_name
        }

        try:
            response = requests.get(self.url + "/getLayer", json=data)

            if response.status_code == 200:
                return response.json()
            else:
                if not quiet:
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

            return self.get_layer_for_user(user_id, layer_name, recursive_iteration, quiet=quiet)

    def _infer_geojson_crs(self, geojson):
        crs = geojson.get("crs")
        if isinstance(crs, dict):
            crs_name = crs.get("properties", {}).get("name") or crs.get("name")
            if isinstance(crs_name, str):
                epsg_match = re.search(r"EPSG[:/](\d+)", crs_name, re.IGNORECASE)
                if epsg_match:
                    return "EPSG:%s" % epsg_match.group(1)
                if crs_name.isdigit():
                    return "EPSG:%s" % crs_name

        first_position = self._first_position_from_features(geojson.get("features", []))
        if first_position:
            x_coord, y_coord = first_position
            if abs(x_coord) <= 180 and abs(y_coord) <= 90:
                return "EPSG:4326"
            return "EPSG:25832"

        return "EPSG:4326"


    def _first_position_from_features(self, features):
        for feature in features:
            geometry = feature.get("geometry") or {}
            position = self._first_position_from_coordinates(geometry.get("coordinates"))
            if position:
                return position
        return None


    def _first_position_from_coordinates(self, coordinates):
        if not isinstance(coordinates, list) or not coordinates:
            return None
        if isinstance(coordinates[0], (int, float)) and len(coordinates) >= 2:
            return float(coordinates[0]), float(coordinates[1])
        return self._first_position_from_coordinates(coordinates[0])


    def reproject_to_utm(self, geojson, keep_properties=True) -> dict:
        return self.reproject_geojson(geojson, "EPSG:25832", keep_properties=keep_properties)


    def reproject_geojson(self, geojson, target_crs, keep_properties=True) -> dict:
        if not geojson.get("features"):
            return {"type": "FeatureCollection", "features": []}

        gdf_cols = ["geometry"]

        # Include the union of property keys so mixed feature types do not lose fields
        # during reprojection when later features contain keys not present on the first one.
        if keep_properties:
            property_keys = set()
            for feature in geojson["features"]:
                property_keys.update((feature.get("properties") or {}).keys())
            gdf_cols.extend(sorted(property_keys))

        source_crs = self._infer_geojson_crs(geojson)
        gdf = geopandas.GeoDataFrame.from_features(geojson["features"], crs=source_crs, columns=gdf_cols)
        if str(gdf.crs).upper() != target_crs.upper():
            gdf = gdf.to_crs(target_crs)

        return json.loads(gdf.to_json())
