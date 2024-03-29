import json
import os
import numpy
from geomet import wkt
from shapely.geometry import Polygon, mapping
from shapely.ops import cascaded_union

from noise_analysis.RoadInfo import RoadInfo



cwd = os.path.dirname(os.path.abspath(__file__))

# TODO: all coordinates for roads and buildings are currently set to z level 0


# road_type_ids from IffStar NoiseModdeling
road_types_iffstar_noise_modelling = {
    "boulevard": 56,  # in boulevard 70km/h
    "street": 53,  # extra boulevard Street 50km/h
    "alley": 54,  # extra boulevard Street <50km/,
    "railroad": 99  # railroad
}

all_roads = []

def reset_all_roads():
    global all_roads
    all_roads = []


# opens a json from path
def open_geojson(path):
    with open(path) as f:
        return json.load(f)


# extract traffic data from road properties
def get_car_traffic_data(road_properties):
    #  https://d-nb.info/97917323X/34
    # p. 68, assuming a mix of type a) and type b) for car traffic around grasbrook (strong morning peak)
    # most roads in hamburg belong to type a) or b)
    # assuming percentage of daily traffic in peak hour = 11%
    # truck traffic: the percentage of daily traffic in peak hour seems to be around 8%
    # source. https://bast.opus.hbz-nrw.de/opus45-bast/frontdoor/deliver/index/docId/1921/file/SVZHeft29.pdf

    # Sources daily traffic: HafenCity GmbH , Standortanalyse, S. 120

    if road_properties['road_type'] == "railroad":
        return None, None, None

    car_traffic = int(int(road_properties['car_traffic_daily']) * 0.11)
    truck_traffic = int(int(road_properties['truck_traffic_daily']) * 0.08)
    max_speed = int(road_properties['max_speed'])

    return max_speed, car_traffic, truck_traffic

# source for train track data = http://laermkartierung1.eisenbahn-bundesamt.de/mb3/app.php/application/eba
def get_train_track_data(road_properties):
    if not road_properties['road_type'] == "railroad":
        return None, None, None, None

    train_speed = road_properties['train_speed']
    train_per_hour = road_properties['trains_per_hour']
    ground_type = road_properties['ground_type']
    has_anti_vibration = road_properties['has_anti_vibration']

    return train_speed, train_per_hour, ground_type, has_anti_vibration


def apply_traffic_settings_to_design_roads(design_roads, traffic_settings):
    max_speed = traffic_settings["max_speed"]
    traffic_quota = traffic_settings["traffic_quota"]

    for road in design_roads["features"]:
        # only adjust traffic settings of manipulatable roads
        if "traffic_settings_adjustable" in list(road["properties"].keys()) and road["properties"]["traffic_settings_adjustable"]:
            road["properties"]["max_speed"] = max_speed
            road["properties"]["truck_traffic_daily"] = road["properties"]["truck_traffic_daily"] * traffic_quota
            road["properties"]["car_traffic_daily"] = road["properties"]["car_traffic_daily"] * traffic_quota
    
    return design_roads


def get_road_queries(traffic_settings, roads_geojson):
    roads_geojson = apply_traffic_settings_to_design_roads(roads_geojson, traffic_settings)
    road_features = roads_geojson["features"]
    add_third_dimension_to_features(road_features)

    for feature in road_features:
        id = feature['properties']['id']
        road_type = get_road_type(feature['properties'])
        coordinates = feature['geometry']['coordinates']

        # input road type might not be defined. road is not imported # TODO consider using a fallback
        if road_type == 0:
            continue
        if feature['geometry']['type'] == 'MultiLineString':
            # beginning point of the road
            start_point = coordinates[0][0]
            # end point of the road
            end_point = coordinates[-1][-1]
        else:
            # beginning point of the road
            start_point = coordinates[0]
            # end point of the road
            end_point = coordinates[1]
            # build string containing all coordinates

        geom = wkt.dumps(feature['geometry'], decimals=0)

        max_speed, car_traffic, truck_traffic = get_car_traffic_data(feature['properties'])
        train_speed, train_per_hour, ground_type, has_anti_vibration = get_train_track_data(feature['properties'])

        # init new RoadInfo object
        road_info = RoadInfo(id, geom, road_type, start_point, end_point, max_speed, car_traffic,
                                      truck_traffic,
                                      train_speed, train_per_hour, ground_type, has_anti_vibration)
        all_roads.append(road_info)

    nodes = create_nodes(all_roads)
    sql_insert_strings = []
    for road in all_roads:
        sql_insert_string = get_insert_query_for_road(road, nodes)
        sql_insert_strings.append(sql_insert_string)

    return sql_insert_strings


# returns sql queries for the traffic table,
def get_traffic_queries():
    sql_insert_strings_noisy_roads = []
    nodes = create_nodes(all_roads)
    for road in all_roads:
        node_from = get_node_for_point(road.get_start_point(), nodes)
        node_to = get_node_for_point(road.get_end_point(), nodes)

        if road.get_road_type_for_query() == road_types_iffstar_noise_modelling['railroad']:
            # train traffic
            train_speed = road.get_train_speed()
            trains_per_hour = road.get_train_per_hour()
            ground_type = road.get_ground_type_train_track()
            has_anti_vibration = road.is_anti_vibration()

            sql_insert_string = "INSERT INTO roads_traffic (node_from,node_to, train_speed, trains_per_hour, ground_type, has_anti_vibration) " \
                                "VALUES ({0},{1},{2},{3},{4},{5});".format(
                node_from, node_to, train_speed, trains_per_hour, ground_type, has_anti_vibration)
        else:
            # car traffic
            traffic_cars = road.get_car_traffic()
            traffic_trucks = road.get_truck_traffic()
            max_speed = road.get_max_speed()
            load_speed = max_speed * 0.9
            junction_speed = max_speed * 0.85

            sql_insert_string = "INSERT INTO roads_traffic (node_from,node_to,load_speed,junction_speed,max_speed,lightVehicleCount,heavyVehicleCount) " \
                                "VALUES ({0},{1},{2},{3},{4},{5},{6});".format(node_from, node_to, load_speed,
                                                                               junction_speed, max_speed, traffic_cars,
                                                                               traffic_trucks)
        sql_insert_strings_noisy_roads.append(sql_insert_string)

    return sql_insert_strings_noisy_roads


# get sql queries for the buildings
def make_building_queries(buildings_geojson):
    # A multipolygon containing all buildings
    buildings = merge_adjacent_buildings(buildings_geojson)
    sql_insert_strings_all_buildings = []

    for feature in buildings['features']:
        if not "coordinates" in feature['geometry']:
            continue
        for polygon in feature['geometry']['coordinates']:
            polygon_string = ''
            if not isinstance(polygon[0][0], float):
                # multiple line strings in polygon (i.e. has holes)
                for coordinates_list in polygon:
                    line_string_coordinates = ''
                    try:
                        for coordinate_pair in coordinates_list:
                            # append 0 to all coordinates for mock third dimension
                            coordinate_string = str(coordinate_pair[0]) + ' ' + str(coordinate_pair[1]) + ' ' + str(0) + ','
                            line_string_coordinates += coordinate_string
                            # remove trailing comma of last coordinate
                        line_string_coordinates = line_string_coordinates[:-1]
                    except Exception as e:
                        print("invalid json")
                        print(e)
                        print(coordinates_list, coordinate_pair, len(polygon[0]), polygon[0])
                        print(feature)
                        exit()
                        return ""
                    # create a string containing a list of coordinates lists per linestring
                    #   ('PolygonWithHole', 'POLYGON((0 0, 10 0, 10 10, 0 10, 0 0),(1 1, 1 2, 2 2, 2 1, 1 1))'),
                    polygon_string += '(' + line_string_coordinates + '),'
            else:
                # only one linestring in polygon (i.e. no holes)
                line_string_coordinates = ''
                try:
                    for coordinate_pair in polygon:
                        # append 0 to all coordinates for mock third dimension
                        coordinate_string = str(coordinate_pair[0]) + ' ' + str(coordinate_pair[1]) + ' ' + str(0) + ','
                        line_string_coordinates += coordinate_string
                        # remove trailing comma of last coordinate
                    line_string_coordinates = line_string_coordinates[:-1]
                except Exception as e:
                    print("invalid json")
                    print(e)
                    print(feature)
                    return ""
                # create a string containing a list of coordinates lists per linestring
                polygon_string += '(' + line_string_coordinates + '),'
            # remove trailing comma of last line string
            polygon_string = polygon_string[:-1]
            sql_insert_string = "'POLYGON (" + polygon_string + ")'"
            sql_insert_strings_all_buildings.append(sql_insert_string)

    return sql_insert_strings_all_buildings


# merges adjacent buildings and creates a multipolygon containing all buildings
def merge_adjacent_buildings(geo_json):
    polygons = []
    for feature in geo_json["features"]:
        if feature["geometry"]["type"] == "MultiPolygon":
            for polygon in feature['geometry']['coordinates'][0]:
                polygons.append(Polygon(polygon))
        else:
            polygons.append(Polygon(feature['geometry']['coordinates'][0]))
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "geometry": mapping(cascaded_union(polygons)),
                "properties": {}
            }
        ]
    }


# create nodes for all roads - nodes are connection points of roads
def create_nodes(all_roads):
    nodes = []
    for road in all_roads:
        coordinates_start_point = road.get_start_point()
        nodes.append(coordinates_start_point)
        coordinates_end_point = road.get_end_point()
        nodes.append(coordinates_end_point)
    unique_nodes = []

    # filter for duplicates
    for node in nodes:
        if not any(numpy.array_equal(node, unique_node) for unique_node in unique_nodes):
            unique_nodes.append(node)
    return unique_nodes


def get_node_for_point(point, nodes):
    dict_of_nodes = {i: nodes[i] for i in range(0, len(nodes))}
    for node_id, node in dict_of_nodes.items():
        if point == node:
            return node_id
    print('could not find node for point', point)
    exit()


def get_road_type(road_properties):
    # if not in road types continue
    for output_road_type in road_types_iffstar_noise_modelling.keys():
        if road_properties['road_type'] == output_road_type:
            return road_types_iffstar_noise_modelling[output_road_type]

    print('no matching noise road_type_found for', road_properties['road_type'])
    return 0


def get_insert_query_for_road(road, nodes):
    node_from = get_node_for_point(road.get_start_point(), nodes)
    node_to = get_node_for_point(road.get_end_point(), nodes)

    sql_insert_string = "INSERT INTO roads_geom (the_geom,NUM,node_from,node_to,road_type) " \
                        "VALUES (ST_GeomFromText('{0}'),{1},{2},{3},{4});".format(road.get_geom(), road.get_road_id(),
                                                                                  node_from, node_to,
                                                                                  road.get_road_type_for_query())
    return sql_insert_string


def add_third_dimension_to_features(features):
    for feature in features:
        if feature['geometry']['type'] == 'LineString':
            add_third_dimension_to_line_feature(feature)
        if feature['geometry']['type'] == 'MultiLineString':
            add_third_dimension_to_multi_line_feature(feature)
        # TODO use this for buildings as well


def add_third_dimension_to_multi_line_feature(feature):
    for pointList in feature['geometry']['coordinates']:
        for point in pointList:
            point.append(0)


def add_third_dimension_to_line_feature(feature):
    for point in feature['geometry']['coordinates']:
        point.append(0)
