# COUP-noise Model Input Contract

This document describes the inputs currently accepted by the COUP-noise service for the implemented `legacy`, `nm5`, and `nm5_full` engines.

Scope note: this is the COUP-noise adapter contract, not a complete catalog of every input that native NoiseModelling can theoretically use. Native NM5 supports more tables and parameters than this service exposes.

## Engine Summary

| Area | `legacy` | `nm5` | `nm5_full` |
| --- | --- | --- | --- |
| Engine selected by | `noise_engine="legacy"` or `NOISE_ENGINE=legacy` | `noise_engine="nm5"` or `NOISE_ENGINE=nm5` | `noise_engine="nm5_full"` or `NOISE_ENGINE=nm5_full` |
| Buildings | Required, geometry only | Required, geometry plus derived height | Required, geometry plus derived height |
| Roads | Required | Required for road sources unless only rail exists | Required for road sources unless only rail exists |
| Rail in `roads.geojson` | Supported through legacy tramway/rail function | Supported through generated railway section and traffic tables | Supported through generated railway section and traffic tables |
| Project area | Required for final clipping | Required for final clipping | Required for final clipping and receiver fencing |
| DEM terrain | Ignored | Optional, used when available | Required |
| Ground absorption | Ignored | Loaded if present, not passed to compatibility propagation | Required and used |
| Atmospheric settings | Ignored | Loaded if present, not passed to compatibility propagation | Required and used |
| Source directivity | Ignored | Loaded if present, not passed to compatibility propagation | Optional and used when present |
| Exposed propagation parameters | Only `wall_absorption`; other values are hard-coded | Limited NM5 settings | Full NM5 settings object |
| Output CRS | `EPSG:4326` | `EPSG:4326` | `EPSG:4326` |

## Input Delivery

The API task payload does not directly contain all geometry. It contains scenario controls and a `city_pyo_user`. COUP-noise then loads layer files for that user from CityPyo or from a local CityPyo-style folder.

### Remote CityPyo

When `CITY_PYO` is a URL, the service calls `/getLayer` with:

```json
{
  "userid": "<city_pyo_user>",
  "layer": "<layer_name>"
}
```

Geometry layers and table-like data are expected as JSON responses.

### Local CityPyo-Style Folder

When `CITY_PYO` points to a local directory, COUP-noise searches in this order:

| Layer type | Search paths |
| --- | --- |
| Geometry layer | `<CITY_PYO>/<city_pyo_user>/<layer>.geojson`, then `<CITY_PYO>/<layer>.geojson` |
| Table/data layer | `<CITY_PYO>/<city_pyo_user>/<layer>.geojson`, `.json`, `.csv`, then `<CITY_PYO>/<layer>.geojson`, `.json`, `.csv` |

Geometry layers are:

- `upperfloor.geojson`
- `roads.geojson`
- `project_area.geojson`
- `dem.geojson`
- `ground_absorption.geojson`

Table/data layers are:

- `source_directivity.geojson`, `.json`, or `.csv`
- `atmospheric_settings.geojson`, `.json`, or `.csv`

### CRS Handling

GeoJSON inputs may include a `crs` object. If no CRS is present, COUP-noise infers CRS from the first coordinate:

- longitude/latitude-looking coordinates are treated as `EPSG:4326`
- projected-looking coordinates are treated as `EPSG:25832`

All layers are reprojected to `EPSG:25832` before engine execution. Final contour outputs are returned in `EPSG:4326`.

## Task JSON

The task JSON is submitted to `POST /task` and must include `city_pyo_user`, `result_format`, `max_speed`, and `traffic_quota`. `noise_engine` is optional if `NOISE_ENGINE` is set in the environment.

Flat payload:

```json
{
  "city_pyo_user": "demo",
  "result_format": "geojson",
  "noise_engine": "nm5_full",
  "max_speed": 50,
  "traffic_quota": 1.0,
  "wall_absorption": 0.69,
  "nm5_settings": {
    "reflection_order": 0,
    "max_source_distance": 250
  }
}
```

Nested payload:

```json
{
  "city_pyo_user": "demo",
  "result_format": "png",
  "png_style": "palette",
  "noise_engine": "legacy",
  "traffic_settings": {
    "max_speed": 30,
    "traffic_quota": 0.5
  },
  "calculation_settings": {
    "wall_absorption": 0.23
  }
}
```

### Task Fields

| Field | Type | Required | Engines | Values/defaults | Meaning |
| --- | --- | --- | --- | --- | --- |
| `city_pyo_user` | string | Yes | all | No default | CityPyo user or local package folder to load. |
| `result_format` | string enum | Yes | all | `geojson` or `png` | Selects response payload type. Case-insensitive. |
| `png_style` | string enum | Only used for PNG | all | `raw` or `palette`; default from `NOISE_PNG_STYLE` or `raw` | `raw` burns `idiso` values into a grayscale PNG. `palette` renders RGBA classes plus legend metadata. Ignored for `geojson`. |
| `noise_engine` | string enum | Optional | all | `legacy`, `nm5`, `nm5_full`, `auto`; default from `NOISE_ENGINE` or `legacy` | Selects engine. `auto` tries NM5 and falls back to legacy only when the NM5 runner is unavailable. |
| `max_speed` | number | Yes, unless nested under `traffic_settings` | all | Must be `>= 0` | Speed override in km/h for roads where `traffic_settings_adjustable` is true. Boolean values are rejected. |
| `traffic_quota` | number | Yes, unless nested under `traffic_settings` | all | Must be `>= 0` | Multiplier applied to `car_traffic_daily` and `truck_traffic_daily` for adjustable roads. |
| `wall_absorption` | number | Optional | all | `0-1`; default `0.23` in both engines | Wall absorption/acoustic alpha value. Legacy currently treats `0` as unset because its override check is truthy. |
| `traffic_settings` | object | Alternative to flat fields | all | See above | Nested location for `max_speed` and `traffic_quota`. |
| `calculation_settings` | object | Optional | all | See above | Nested location for `wall_absorption`. |
| `nm5_settings` | object | Optional | `nm5`, `nm5_full` | See NM5 settings table | Native NM5 meshing, propagation, and contour settings exposed by the adapter. Ignored by legacy. |

## Geometry Layer Formats

All geometry layers are GeoJSON `FeatureCollection` objects:

```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "properties": {},
      "geometry": {
        "type": "Polygon",
        "coordinates": []
      }
    }
  ]
}
```

### `project_area.geojson`

| Item | Contract |
| --- | --- |
| Required by | `legacy`, `nm5`, `nm5_full` |
| Geometry types | `Polygon`, `MultiPolygon` |
| Properties | Ignored by all engines |
| Purpose | Clips final contours. In `nm5_full`, also passed as the receiver generation fence. |
| Invalid features | Non-polygon geometries are skipped by the NM5 adapter. Legacy clipping expects valid polygonal geometry. |

### `upperfloor.geojson`

| Item | `legacy` | `nm5` and `nm5_full` |
| --- | --- | --- |
| Required | Yes | Yes |
| Geometry types | `Polygon`, `MultiPolygon` | `Polygon`, `MultiPolygon` |
| Properties used | None | Height fields listed below |
| Invalid features | Legacy may fail if geometry is malformed | Non-polygon features skipped |

Legacy merges all building polygons into one obstacle geometry and forces Z to `0`.

NM5 writes a `BUILDINGS` table with `PK` and `HEIGHT`. Height is derived in this order:

| Accepted property names | Type | Behavior |
| --- | --- | --- |
| `height`, `HEIGHT`, `building_height`, `BUILDING_HEIGHT`, `measured_height`, `MEASURED_HEIGHT`, `roof_height`, `ROOF_HEIGHT`, `roof_z`, `ROOF_Z`, `z`, `Z` | number or numeric string | First positive value is used directly as meters. |
| `floors`, `FLOORS`, `storeys`, `STOREYS`, `stories`, `STORIES`, `levels`, `LEVELS`, `num_floors`, `NUM_FLOORS`, `floor_count`, `FLOOR_COUNT` | number or numeric string | First positive value is multiplied by `NM5_DEFAULT_FLOOR_HEIGHT`, default `3`. |
| none usable | none | Uses `NM5_DEFAULT_BUILDING_HEIGHT`, default `10`. |

### `roads.geojson`

| Item | Contract |
| --- | --- |
| Required by | `legacy`, `nm5`, `nm5_full` |
| Geometry types | `LineString`, `MultiLineString` |
| CRS | Reprojected to `EPSG:25832` |
| Routing of features | `road_type == "railroad"` is treated as rail. All other lines are road sources in NM5. Legacy only accepts known road types. |

#### Common Traffic Adjustment Fields

These fields are interpreted before both engines build their source tables:

| Property | Type | Required | Meaning |
| --- | --- | --- | --- |
| `traffic_settings_adjustable` | boolean-like | Optional | If true, the request `max_speed` replaces feature `max_speed`, and request `traffic_quota` multiplies `car_traffic_daily` and `truck_traffic_daily`. |
| `max_speed` | number or numeric string | Meaningful for road sources | Road speed in km/h. |
| `car_traffic_daily` | number or numeric string | Meaningful for road sources | Daily light vehicle count. Legacy and NM5 convert this to a period/hour-like count using factor `0.11`. |
| `truck_traffic_daily` | number or numeric string | Meaningful for road sources | Daily heavy vehicle count. Legacy and NM5 convert this using factor `0.08`. |

Important: if `traffic_settings_adjustable` is true, `car_traffic_daily`, `truck_traffic_daily`, and `max_speed` must be present and numeric enough for multiplication. Missing adjustable traffic fields can fail before engine execution.

#### Legacy Road Source Fields

Legacy uses `noise_analysis/sql_query_builder.py`.

| Property | Type | Required | Accepted values/defaults | Meaning |
| --- | --- | --- | --- | --- |
| `id` | integer-like | Yes | No default | Inserted as road `NUM`. |
| `road_type` | string enum | Yes | `boulevard`, `street`, `alley`, `railroad` | Mapped to legacy IFFSTAR road type ids `56`, `53`, `54`, and `99`. Unknown values are skipped. |
| `max_speed` | integer-like | Required for non-rail | No default | Road speed in km/h. Legacy also computes `load_speed = max_speed * 0.9` and `junction_speed = max_speed * 0.85`. |
| `car_traffic_daily` | integer-like | Required for non-rail | No default | Converted to `lightVehicleCount = int(value * 0.11)`. |
| `truck_traffic_daily` | integer-like | Required for non-rail | No default | Converted to `heavyVehicleCount = int(value * 0.08)`. |
| `train_speed` | number | Required for `railroad` | No default | Speed passed to legacy rail/tram source function. |
| `trains_per_hour` | number | Required for `railroad` | No default | Train frequency. |
| `ground_type` | integer-like | Required for `railroad` | No default | Track ground type passed to legacy rail/tram source function. |
| `has_anti_vibration` | boolean-like | Required for `railroad` | No default | Track anti-vibration flag. |

Legacy does not consume DEM, building heights, ground absorption, directivity, atmospheric settings, pavement, slope, or NM5 period fields.

#### NM5 Road Source Fields

NM5 treats every non-rail line as a road source. The adapter writes the same derived values for periods `D`, `E`, and `N`.

| Property | Type | Required for meaningful road source | Default/coercion | NM5 output field(s) |
| --- | --- | --- | --- | --- |
| `max_speed` | integer-like | Yes | Invalid/missing becomes `0` | `LV_SPD_D/E/N`, `MV_SPD_D/E/N`, `HGV_SPD_D/E/N`, `WAV_SPD_D/E/N`, `WBV_SPD_D/E/N` |
| `car_traffic_daily` | integer-like | Yes | Invalid/missing becomes `0` | `LV_D/E/N = int(value * 0.11)` |
| `truck_traffic_daily` | integer-like | Yes | Invalid/missing becomes `0` | `HGV_D/E/N = int(value * 0.08)` |
| `PVMT` or `pvmt` | string | Optional | `DEF` | `PVMT` |
| `JUNC_DIST` | number | Optional | `0.0` | `JUNC_DIST` |
| `JUNC_TYPE` | integer-like | Optional | `0` | `JUNC_TYPE` |
| `WAY` | integer-like | Optional | `3` | `WAY` |
| `SLOPE` | number | Optional | Omitted when invalid/missing | `SLOPE` |

The adapter currently sets medium vehicle, powered two-wheeler, and bus/van classes to zero:

- `MV_D/E/N = 0`
- `WAV_D/E/N = 0`
- `WBV_D/E/N = 0`

#### NM5 Rail Source Fields

Set `road_type` exactly to `railroad` to route a line feature into generated `RAIL_SECTIONS` and `RAIL_TRAFFIC` tables.

| Property | Type | Required | Default/coercion | NM5 output field |
| --- | --- | --- | --- | --- |
| `NTRACK`, `ntrack`, `tracks`, `TRACKS` | integer-like | Optional | `NM5_DEFAULT_RAIL_TRACK_COUNT`, default `1` | `NTRACK` |
| `TRACKSPD`, `track_speed`, `train_speed`, `TRAINSPD`, `max_speed` | number | Optional | `NM5_DEFAULT_RAIL_SPEED`, default `80` | `TRACKSPD`, `COMSPD`, `TRAINSPD` |
| `trains_per_hour`, `TRAINS_PER_HOUR`, `TDAY`, `tday` | number | Optional | `NM5_DEFAULT_TRAINS_PER_HOUR`, default `2` | `TDAY`, `TEVENING`, `TNIGHT` |
| `TRAINTYPE`, `train_type` | string | Optional | `NM5_DEFAULT_TRAIN_TYPE`, default `FRET` | `TRAINTYPE` |
| `TRANSFER` | string or positive integer-like | Optional | `NM5_DEFAULT_RAIL_TRANSFER`, default `SNCF4` | `TRANSFER` |
| `ROUGHNESS` | string or positive integer-like | Optional | `NM5_DEFAULT_RAIL_ROUGHNESS`, default `SNCF1` | `ROUGHNESS` |
| `IMPACT` | string or positive integer-like | Optional | `NM5_DEFAULT_RAIL_IMPACT`, default empty | `IMPACT` |
| `CURVATURE` | integer-like | Optional | `NM5_DEFAULT_RAIL_CURVATURE`, default `0` | `CURVATURE` |
| `BRIDGE`, `bridge_type` | string or positive integer-like | Optional | `NM5_DEFAULT_RAIL_BRIDGE`, default empty | `BRIDGE` |
| `TRACKSPC`, `track_spacing`, `trackspc` | number | Optional | `NM5_DEFAULT_RAIL_TRACK_SPACING`, default `4` | `TRACKSPC` |
| `ISTUNNEL`, `tunnel` | boolean-like | Optional | `0` | `ISTUNNEL` |

For code-like rail fields, positive numeric values are converted to `SNCF<number>` unless a string code is already supplied.

### `dem.geojson`

| Item | Contract |
| --- | --- |
| Used by | Optional in `nm5`, required in `nm5_full`, ignored by `legacy` |
| Geometry types | `Point`, `MultiPoint` |
| Coordinate dimension | Must be 3D: `[x, y, z]` |
| Properties | Preserved; `PK` is added when missing |
| Invalid features | Non-point features skipped; 2D points skipped |

Example:

```json
{
  "type": "Feature",
  "properties": {},
  "geometry": {
    "type": "Point",
    "coordinates": [566000.0, 5933000.0, 7.4]
  }
}
```

### `ground_absorption.geojson`

| Item | Contract |
| --- | --- |
| Used by | Required in `nm5_full`, ignored by `legacy`, not used by compatibility `nm5` propagation |
| Geometry types | `Polygon`, `MultiPolygon` |
| Required property | `G` or `g` |
| `G` type | number or numeric string |
| `G` range | Clamped to `0-1`; `0` is hard ground, `1` is soft ground |
| Invalid features | Non-polygon features skipped; polygons missing `G` skipped |

### `source_directivity`

This layer can be supplied as `.csv`, `.json`, or `.geojson`. It is optional and only used by `nm5_full`.

Accepted payload shapes:

- CSV rows loaded through `csv.DictReader`
- JSON list of row objects
- JSON object with `rows: [...]`
- GeoJSON `FeatureCollection`, using each feature's `properties`
- single JSON row object

All field names are case-insensitive during parsing.

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `DIR_ID` | integer-like | Yes | Directivity id referenced by source rows when present. |
| `THETA` | number | Yes | Horizontal angle. |
| `PHI` | number | Yes | Vertical angle. |
| `HZ63` | number | Yes | Attenuation/value at 63 Hz. |
| `HZ125` | number | Yes | Attenuation/value at 125 Hz. |
| `HZ250` | number | Yes | Attenuation/value at 250 Hz. |
| `HZ500` | number | Yes | Attenuation/value at 500 Hz. |
| `HZ1000` | number | Yes | Attenuation/value at 1000 Hz. |
| `HZ2000` | number | Yes | Attenuation/value at 2000 Hz. |
| `HZ4000` | number | Yes | Attenuation/value at 4000 Hz. |
| `HZ8000` | number | Yes | Attenuation/value at 8000 Hz. |

Rows missing any required field are skipped.

Directivity only affects propagation when generated source rows contain matching `DIR_ID` values. The current COUP-noise adapter accepts and imports the table, but it does not explicitly copy a `DIR_ID` property from ordinary road features into the generated road source schema.

### `atmospheric_settings`

This layer can be supplied as `.csv`, `.json`, or `.geojson`. It is required by `nm5_full` and ignored by legacy. Compatibility `nm5` loads it when present but does not pass it to propagation.

Accepted payload shapes are the same as `source_directivity`.

| Field | Type | Required | Default | Meaning |
| --- | --- | --- | --- | --- |
| `PERIOD` | string | Yes | none | Period id, usually `D`, `E`, or `N`. Converted to uppercase. |
| `TEMPERATURE` | number | Yes | none | Temperature. |
| `HUMIDITY` | number | Yes | none | Relative humidity. |
| `PRESSURE` | number | Optional when absent | `NM5_DEFAULT_ATMOSPHERIC_PRESSURE`, default `101325` | Atmospheric pressure. If present but blank/invalid, row is skipped. |
| `GDISC` | boolean-like | Optional | `true` | Ground discontinuity flag passed to NM5 atmospheric table. |
| `PRIME2520` | boolean-like | Optional | `false` | Atmospheric setting flag passed to NM5. |
| `WINDROSE` | array of 16 numbers, or string list | Alternative to indexed fields | none | 16-sector wind rose. |
| `WINDROSE_0` through `WINDROSE_15` | number | Alternative to `WINDROSE` | none | 16-sector wind rose as separate columns. |

Rows missing `PERIOD`, `TEMPERATURE`, `HUMIDITY`, or a valid 16-value wind rose are skipped.

## NM5 Settings Object

`nm5_settings` is ignored by legacy. It is parsed for both `nm5` and `nm5_full`, but some fields only affect `nm5_full`.

| Field | Type | Applies to | Default | Effect |
| --- | --- | --- | --- | --- |
| `receiver_height` | number | `nm5_full` | `4` | Receiver height for Delaunay receiver generation. |
| `max_cell_dist` | number | `nm5`, `nm5_full` | `750` | Delaunay grid maximum cell distance. |
| `road_width` | number | `nm5`, `nm5_full` | `1.5` | Width used around road/source lines for receiver generation. |
| `building_buffer` | number | `nm5_full` | `null` | Passed to NM5 Delaunay grid as building buffer. |
| `max_area` | number | `nm5`, `nm5_full` | `275` | Delaunay triangle maximum area. Higher values usually reduce receiver count and runtime. |
| `skip_cell_no_sources_minimal_distance` | number | `nm5_full` | `null` | Passed to NM5 Delaunay grid. |
| `fence_negative_buffer` | number | `nm5_full` | `null` | Buffer applied to receiver fence. |
| `iso_surface_in_buildings` | boolean | `nm5_full` | `null` | Passed to NM5 Delaunay grid. |
| `export_triangles_geometries` | boolean | `nm5_full` | `null` | Requests triangle geometry export from receiver generation. |
| `reflection_order` | integer `>= 0` | `nm5_full` | `1` | Reflection order. Compatibility `nm5` always uses `0`. |
| `max_source_distance` | number | `nm5_full` | `750` | Maximum source-receiver propagation distance. Compatibility `nm5` always uses `750`. |
| `max_reflection_distance` | number | `nm5_full` | `350` | Maximum reflection search distance. Compatibility `nm5` always uses `50`. |
| `thread_number` | integer `>= 0` | `nm5_full` | `0` | NM5 propagation thread count. `0` means NM5 decides automatically. |
| `diff_vertical` | boolean | `nm5_full` | `true` when rail sources exist, else `false` | Vertical diffraction. |
| `diff_horizontal` | boolean | `nm5_full` | `true` | Horizontal diffraction. |
| `export_source_id` | boolean | `nm5_full` | `null` | Requests source id export in propagation output. |
| `humidity` | number `0-100` | `nm5_full` | `null` | Propagation humidity override. Atmospheric settings table may also define period-specific values. |
| `temperature` | number | `nm5_full` | `null` | Propagation temperature override. Atmospheric settings table may also define period-specific values. |
| `favourable_occurrences` | string | `nm5_full` | `null` | Passed to `confFavourableOccurrencesDefault`. |
| `rays_name` | string | `nm5_full` | `null` | Passed to `confRaysName`. |
| `max_error` | number `>= 0` | `nm5_full` | `0.1` | Propagation error tolerance. Higher values can improve runtime at lower precision. |
| `iso_classes` | string | `nm5`, `nm5_full` | `45,50,55,60,65,70,75,200` | Comma-separated isosurface class breakpoints. |
| `result_table_field` | string | `nm5`, `nm5_full` | `LAEQ` | Result level field used by isosurface creation. |

Boolean parsing accepts booleans, numbers, and strings such as `true`, `false`, `1`, `0`, `yes`, `no`, `on`, and `off`.

## Legacy Hard-Coded Settings

Legacy uses the old embedded OrbisGIS/H2GIS NoiseModelling path. These settings are hard-coded and are not request-configurable except for `wall_absorption`.

| Setting | Value | Meaning |
| --- | --- | --- |
| `max_prop_distance` | `750` | Maximum propagation distance. |
| `max_wall_seeking_distance` | `50` | Wall search distance. |
| `road_with` | `1.5` | Road width parameter. |
| `receiver_densification` | `2.8` | Legacy receiver densification parameter. |
| `max_triangle_area` | `275` | Legacy triangle maximum area. |
| `sound_reflection_order` | `0` | No reflections. |
| `sound_diffraction_order` | `0` | No diffraction. |
| `wall_absorption` | `0.23` | Default when request does not override it. |

Legacy contour classes are produced with these power thresholds:

```text
31622, 100000, 316227, 1000000, 3162277, 1e+7, 31622776, 1e+20
```

The service returns the resulting contour class as `idiso`.

## Result Payloads

### GeoJSON Result

All engines return a GeoJSON `FeatureCollection` when `result_format="geojson"`.

Common properties:

| Property | Type | Meaning |
| --- | --- | --- |
| `idiso` | integer | Noise class id. Current palette maps `0` to `< 45 dB(A)`, `1` to `45-50 dB(A)`, up through `7` for `> 75 dB(A)`. |
| `cell_id` or `CELL_ID` | integer | Contour cell id when available. NM5 normalizes to `cell_id`; legacy may retain `CELL_ID`. |

### PNG Result

When `result_format="png"`, the service rasterizes the GeoJSON contours and returns:

| Field | Type | Meaning |
| --- | --- | --- |
| `bbox_sw_corner` | coordinate pair | Southwest corner of output bbox in `EPSG:4326`. |
| `bbox_coordinates` | ring coordinates | Output bbox polygon in `EPSG:4326`. |
| `img_width` | integer | PNG width in pixels. |
| `img_height` | integer | PNG height in pixels. |
| `image_base64_string` | string | Base64-encoded PNG. |
| `png_style` | string | `raw` or `palette`. |
| `legend` | array or `null` | Palette legend when `png_style="palette"`. |

## Environment Variables That Affect Input Interpretation

| Variable | Default | Applies to | Meaning |
| --- | --- | --- | --- |
| `CITY_PYO` | `/app/fixtures/citypyo` in Docker Compose | all | Remote CityPyo URL or local layer root. |
| `NOISE_ENGINE` | `legacy` | all | Default engine when task does not specify `noise_engine`. |
| `NOISE_PNG_STYLE` | `raw` | all PNG outputs | Default PNG style. |
| `NM5_OUTPUT_PERIOD` | `D` | NM5 output normalization | Preferred period selected from NM5 exported contours. |
| `NM5_DEFAULT_BUILDING_HEIGHT` | `10` | NM5 | Building height fallback in meters. |
| `NM5_DEFAULT_FLOOR_HEIGHT` | `3` | NM5 | Floor-to-height conversion multiplier. |
| `NM5_DEFAULT_ATMOSPHERIC_PRESSURE` | `101325` | NM5 full | Pressure fallback when absent from atmospheric rows. |
| `NM5_DEFAULT_RAIL_TRACK_COUNT` | `1` | NM5 rail | Rail track count fallback. |
| `NM5_DEFAULT_RAIL_SPEED` | `80` | NM5 rail | Rail speed fallback. |
| `NM5_DEFAULT_TRAINS_PER_HOUR` | `2` | NM5 rail | Train frequency fallback. |
| `NM5_DEFAULT_RAIL_TRANSFER` | `SNCF4` | NM5 rail | Rail transfer fallback. |
| `NM5_DEFAULT_RAIL_ROUGHNESS` | `SNCF1` | NM5 rail | Rail roughness fallback. |
| `NM5_DEFAULT_RAIL_IMPACT` | empty string | NM5 rail | Rail impact fallback. |
| `NM5_DEFAULT_RAIL_CURVATURE` | `0` | NM5 rail | Rail curvature fallback. |
| `NM5_DEFAULT_RAIL_BRIDGE` | empty string | NM5 rail | Rail bridge fallback. |
| `NM5_DEFAULT_RAIL_TRACK_SPACING` | `4` | NM5 rail | Track spacing fallback in meters. |
| `NM5_DEFAULT_TRAIN_TYPE` | `FRET` | NM5 rail | Train type fallback. |
| `NOISEMODELLING_RUNNER` | Docker Compose path | NM5 | Path to the headless NoiseModelling WPS runner. |
