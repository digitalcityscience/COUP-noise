import base64
import os
import numpy as np
import math
from io import BytesIO
from PIL import Image
import json

import rasterio.features
import rasterio.warp
import geopandas

from shapely.geometry import Polygon, Point
from pyproj import Transformer
from shapely.ops import transform

transformer_to_wgs = Transformer.from_crs(25832, 4326, always_xy=False).transform


def geojson_to_png(geojson, property_to_burn, resolution):
    geom_value_pairs = [(feature["geometry"], feature["properties"][property_to_burn]) for feature in geojson["features"]]

    image_data = rasterio.features.rasterize(shapes=geom_value_pairs, fill=0, dtype='float64', out_shape=resolution)

    # map image data to ints from 0-255 (for png), idiso value has 8 steps, including 0
    # set NaN as 0
    image_data = [
        [int(round(x * (255/7))) if not math.isnan(x) else 0 for x in image_line]
        for image_line in image_data
    ]
    # create a np array from image data
    np_values = np.array(image_data, dtype="uint8")

    # create a pillow image, save it and convert to base64 string
    im = Image.fromarray(np_values)
    output_buffer = BytesIO()
    im.save(output_buffer, format='PNG')
    byte_data = output_buffer.getvalue()
    base64_bytes = base64.b64encode(byte_data)
    base64_string = base64_bytes.decode('utf-8')
    img_width, img_height = im.size

    return base64_string, img_width, img_height


def make_gdf_from_geojson(geojson, crs) -> geopandas.GeoDataFrame:
    gdf_cols = ["geometry"]

    # add all properties to gdf cols
    for property_key in geojson["features"][0]["properties"].keys():
        gdf_cols.append(property_key)

    gdf = geopandas.GeoDataFrame.from_features(geojson["features"], crs=crs, columns=gdf_cols)

    return gdf


def reproject_coords(input_coords):
    output_epsg = 4326
    input_epsg = 25832

    # reproject all points in bulk
    transformer = Transformer.from_crs(input_epsg, output_epsg, always_xy=True)
    output_coords = transformer.itransform(input_coords)

    return output_coords


def get_bounds_coordinates(gdf_bounds):
    left, bottom, right, top = gdf_bounds
    bounds_utm = Polygon([
        [left, bottom],
        [right, bottom],
        [right, top],
        [left, top],
        [left, bottom]
    ]
    )

    bound_wgs = transform(transformer_to_wgs, bounds_utm)

    return list(bound_wgs.exterior.coords)


def convert_result_to_png(geojson=None):
    cwd = os.path.dirname(os.path.abspath(__file__))

    if not geojson:
        with open(cwd + "/results/result.geojson") as fp:
            geojson = json.load(fp)

    gdf = make_gdf_from_geojson(geojson, "EPSG:4326")
    gdf = gdf.to_crs("EPSG:25832")  # reproject to utm coords

    with open(cwd + "/project_area_utm.geojson") as fp:
        project_area = json.load(fp)
        project_area_gdf = make_gdf_from_geojson(project_area, "EPSG:25832")

    # clip input dataset to project area
    gdf = geopandas.clip(gdf, project_area_gdf)

    # get total bounds of original dataset (to position image on cityScope later)
    gdf_total_bounds = gdf.total_bounds
    bounds_coordinates = get_bounds_coordinates(gdf_total_bounds)
    south_west_corner_pt = transform(transformer_to_wgs, Point([gdf_total_bounds[0], gdf_total_bounds[1]]))
    south_west_corner_coords = list(south_west_corner_pt.coords)

    #  Translate geometry to start at 0,0
    gdf.geometry = gdf.translate(-gdf_total_bounds[0], -gdf_total_bounds[1])

    # calculate resolution of picture
    resolution_x = math.ceil(gdf_total_bounds[2] - gdf_total_bounds[0])
    resolution_y = math.ceil(gdf_total_bounds[3] - gdf_total_bounds[1])

    # rasterize data
    base64_string, img_width, img_height = geojson_to_png(json.loads(gdf.to_json()), "idiso",
                                                             [resolution_x, resolution_y])

    return [{
        "bbox_sw_corner": south_west_corner_coords,
        "img_width": img_width,
        "img_height": img_height,
        "bbox_coordinates": bounds_coordinates,
        "image_base64_string": base64_string
    }]


# rasterize geojson  https://gis.stackexchange.com/questions/316626/rasterio-features-rastersize
if __name__ == '__main__':
    convert_result_to_png()
