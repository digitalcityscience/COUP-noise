# NoiseModelling 5 Inputs and Parameters

This document describes the core NoiseModelling 5 noise-map workflow, independent of this repository's adapter.

Scope:

- source tables: roads, railways, generic sources
- environment tables: buildings, DEM, ground, directivity, atmosphere
- receiver tables and Delaunay receiver generation
- propagation parameters for `Noise_level_from_traffic` and `Noise_level_from_source`
- emission helper parameters for `Road_Emission_from_Traffic` and `Railway_Emission_from_Traffic`
- contour parameters for `Create_Isosurface`

Except for the supported file-format summary, it does not list every utility WPS block in NoiseModelling, such as geometric cleanup tools, dynamic tutorials, or database management scripts.

## General Data Rules

NM5 works on database tables. File formats are only import/export containers. After import, the table still needs the expected table name, geometry column, CRS, and fields documented below.

The examples below use CSV-like rows with WKT geometry for readability. A `csv` example should be read as a compact table-row example, not as a claim that CSV is the preferred or only supported file format.

Common rules:

- Use a metric projected CRS, not WGS84 lon/lat, for computation tables.
- Geometry is normally stored in `THE_GEOM`.
- The `Required` column says `yes`, `no`, or `useful`. `Useful` means the field may not be a strict schema requirement, but the model needs it for a meaningful acoustic result.
- `D`, `E`, `N` mean day, evening, night.
- Sound frequencies are usually octave-band columns such as `HZ63`, `HZ125`, `HZ250`, `HZ500`, `HZ1000`, `HZ2000`, `HZ4000`, `HZ8000`.
- Some scripts also support third-octave bands from `HZ50` to `HZ10000`.

## Supported File Formats

The supported file formats depend on the WPS import/export helper used. This repo snapshot includes the following support in the bundled NM5 WPS scripts:

| Use case | WPS block | Supported extensions | Notes |
| --- | --- | --- | --- |
| Single vector or tabular file import | `Import_File` | `.csv`, `.tsv`, `.dbf`, `.geojson`, `.gpx`, `.osm`, `.gz`, `.bz2`, `.shp`, `.fgb` | `.gz` and `.bz2` are handled by the OSM driver. `.fgb` is supported by the script code even though this snapshot's WPS description omits it. |
| Folder vector or tabular import | `Import_Folder` | `.csv`, `.tsv`, `.dbf`, `.geojson`, `.gpx`, `.osm`, `.gz`, `.bz2`, `.shp` | Imports files in a folder that match the selected extension. |
| OSM-to-NM input conversion | `Import_OSM` | `.osm`, `.osm.gz`, `.osm.pbf` | Convenience importer that creates NM-style `BUILDINGS`, `GROUND`, and `ROADS` tables from OSM. |
| DEM raster import | `Import_Asc_File` | `.asc`, `.asc.gz` | ESRI ASCII grid DEM. Creates or fills the `DEM` table as 3D points. |
| DEM raster folder import | `Import_Asc_Folder` | `.asc` | Imports all `.asc` tiles in a folder into the `DEM` table. |
| Table export | `Export_Table` | `.csv`, `.tsv`, `.dbf`, `.geojson`, `.json`, `.kml`, `.shp`, `.fgb` | These are the extensions implemented in the export switch in this repo snapshot. |
| Direct database input | H2GIS or PostGIS | not file-based | Create or load the required tables directly with SQL or external GIS tooling. |

Practical notes:

- GeoJSON is usually the easiest readable spatial file format for small examples. The geometry lives in the GeoJSON `geometry` object; NM fields such as `HEIGHT`, `G`, and `PK` live in `properties`.
- Shapefile works, but keep the sidecar files together, especially `.shx`, `.dbf`, and ideally `.prj`.
- CSV/TSV examples in this document store geometry as WKT text for readability. If you use them as real files, confirm after import that `THE_GEOM` is a spatial geometry column, not plain text.
- GeoPackage `.gpkg` is not handled by the bundled `Import_File` or `Export_Table` switch in this repo snapshot. Convert it to a supported format or load it into H2GIS/PostGIS through another tool.
- Regardless of file format, acoustic computation tables should be in a metric projected CRS. If a file is lon/lat, transform it before running the acoustic workflow.

The first `BUILDINGS` row below:

```csv
THE_GEOM,HEIGHT,G
"POLYGON ((0 0, 20 0, 20 15, 0 15, 0 0))",12,0.1
```

is equivalent to a GeoJSON feature like this:

```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "geometry": {
        "type": "Polygon",
        "coordinates": [
          [[0, 0], [20, 0], [20, 15], [0, 15], [0, 0]]
        ]
      },
      "properties": {
        "HEIGHT": 12,
        "G": 0.1
      }
    }
  ]
}
```

## Main Workflows

### Road Traffic Workflow

Use this when your source is road traffic.

1. `ROADS` and optional `ROADS_TRAFFIC`
2. `BUILDINGS`
3. `RECEIVERS`, often generated with `Delaunay_Grid`
4. Optional `DEM`, `GROUND`, `DIRECTIVITY`, `ATMOSPHERIC_SETTINGS`
5. Run `Noise_level_from_traffic`
6. Optional: run `Create_Isosurface`

### Generic Source Workflow

Use this when you already have source emission spectra.

1. `SOURCES_GEOM`
2. `SOURCES_EMISSION`, unless emission fields are embedded in `SOURCES_GEOM`
3. `BUILDINGS`
4. `RECEIVERS`
5. Optional `DEM`, `GROUND`, `DIRECTIVITY`, `ATMOSPHERIC_SETTINGS`
6. Run `Noise_level_from_source`
7. Optional: run `Create_Isosurface`

### Rail Workflow

Use this when your source is railway traffic.

1. `RAIL_SECTIONS`
2. `RAIL_TRAFFIC`
3. Run `Railway_Emission_from_Traffic` to create `LW_RAILWAY`
4. Use `LW_RAILWAY` as a source table in the generic source workflow

## Input Tables

### `BUILDINGS`

Purpose: buildings and thin walls used for obstruction, reflection, diffraction, and 3D ray paths.

| Field | Required | Type | Meaning |
| --- | --- | --- | --- |
| `THE_GEOM` | yes | `POLYGON`, `MULTIPOLYGON`, or `LINESTRING`, 2D or 3D | Building footprint or wall geometry |
| `HEIGHT` | yes | double, meters | Building or wall height |
| `POP` | no | double | Population, useful for exposure workflows |
| `G` | no | double | Wall absorption if `0-1`, or wall impedance if `20-20000` |

Small table-row example, using WKT geometry:

```csv
THE_GEOM,HEIGHT,G
"POLYGON ((0 0, 20 0, 20 15, 0 15, 0 0))",12,0.1
```

Notes:

- If geometry has no Z and a DEM exists, NM5 can derive ground altitude from the DEM and add `HEIGHT`.
- If geometry has no Z and no DEM exists, height is interpreted relative to flat ground.
- If geometry has Z, the Z should represent the object altitude, such as roof or gutter altitude.

### `ROADS`

Purpose: road geometry and day/evening/night road traffic input for `Noise_level_from_traffic` and `Road_Emission_from_Traffic`.

| Field | Required | Type | Meaning |
| --- | --- | --- | --- |
| `THE_GEOM` | yes | `LINESTRING` or `MULTILINESTRING` | Road centerline |
| `PK` | yes | integer primary key | Road identifier |
| `LV_D`, `LV_E`, `LV_N` | useful | double | Hourly light vehicle count |
| `MV_D`, `MV_E`, `MV_N` | useful | double | Hourly medium vehicle count |
| `HGV_D`, `HGV_E`, `HGV_N` | useful | double | Hourly heavy vehicle count |
| `WAV_D`, `WAV_E`, `WAV_N` | useful | double | Hourly moped / small two-wheeler count |
| `WBV_D`, `WBV_E`, `WBV_N` | useful | double | Hourly motorcycle / large two-wheeler count |
| `LV_SPD_D`, `LV_SPD_E`, `LV_SPD_N` | useful | double, km/h | Light vehicle speed |
| `MV_SPD_D`, `MV_SPD_E`, `MV_SPD_N` | useful | double, km/h | Medium vehicle speed |
| `HGV_SPD_D`, `HGV_SPD_E`, `HGV_SPD_N` | useful | double, km/h | Heavy vehicle speed |
| `WAV_SPD_D`, `WAV_SPD_E`, `WAV_SPD_N` | useful | double, km/h | Small two-wheeler speed |
| `WBV_SPD_D`, `WBV_SPD_E`, `WBV_SPD_N` | useful | double, km/h | Large two-wheeler speed |
| `PVMT` | no | string | CNOSSOS pavement identifier, default commonly `DEF` or script-specific default |
| `TS_STUD` | no | double, months `0-12` | Studded tyre period |
| `PM_STUD` | no | double `0-1` | Proportion of light vehicles with studded tyres |
| `JUNC_DIST` | no | double, meters | Distance to junction |
| `JUNC_TYPE` | no | integer | `0` none, `1` traffic light crossing, `2` roundabout |
| `SLOPE` | no | double, percent | Road slope. If absent, line Z may be used to infer slope |
| `WAY` | no | integer | `1` with slope direction, `2` against slope direction, `3` bidirectional |

Small example:

```csv
PK,THE_GEOM,LV_D,LV_E,LV_N,MV_D,MV_E,MV_N,HGV_D,HGV_E,HGV_N,WAV_D,WAV_E,WAV_N,WBV_D,WBV_E,WBV_N,LV_SPD_D,LV_SPD_E,LV_SPD_N,MV_SPD_D,MV_SPD_E,MV_SPD_N,HGV_SPD_D,HGV_SPD_E,HGV_SPD_N,WAV_SPD_D,WAV_SPD_E,WAV_SPD_N,WBV_SPD_D,WBV_SPD_E,WBV_SPD_N,PVMT,JUNC_DIST,JUNC_TYPE,SLOPE,WAY
1,"LINESTRING (0 0, 100 0)",600,250,80,20,8,3,40,20,10,0,0,0,5,2,1,50,45,40,45,40,35,45,40,35,45,40,35,45,40,35,DEF,200,0,0,3
```

Notes:

- Road emission is normally placed 0.05 m above ground.
- Road geometry Z is mainly used for slope inference, not to force propagation altitude. If road altitude matters, enrich the DEM.

### `ROADS_TRAFFIC` or custom-period road traffic

Purpose: custom period traffic table for road emission, instead of `D/E/N` columns on `ROADS`.

| Field | Required | Type | Meaning |
| --- | --- | --- | --- |
| `IDSOURCE` | yes | integer | Links to road/source primary key |
| `PERIOD` | yes | string | Period label, for example `08:00-09:00` |
| `LV`, `MV`, `HGV`, `WAV`, `WBV` | useful | double | Hourly vehicle counts by class |
| `LV_SPD`, `MV_SPD`, `HGV_SPD`, `WAV_SPD`, `WBV_SPD` | useful | double, km/h | Speeds by class |
| `PVMT`, `TS_STUD`, `PM_STUD`, `JUNC_DIST`, `JUNC_TYPE`, `SLOPE`, `WAY` | no | mixed | Same meaning as `ROADS` |

Small example:

```csv
IDSOURCE,PERIOD,LV,MV,HGV,WAV,WBV,LV_SPD,MV_SPD,HGV_SPD,WAV_SPD,WBV_SPD,PVMT,JUNC_DIST,JUNC_TYPE,SLOPE,WAY
1,"08:00-09:00",900,25,60,0,8,50,45,45,45,45,DEF,200,0,0,3
```

### `RAIL_SECTIONS`

Purpose: railway geometry and track properties.

| Field | Required | Type | Meaning |
| --- | --- | --- | --- |
| `THE_GEOM` | yes | `LINESTRING` or `MULTILINESTRING` | Railway section geometry |
| `IDSECTION` | yes | integer primary key | Section identifier |
| `NTRACK` | yes | integer | Number of tracks |
| `TRACKSPD` | yes | double, km/h | Maximum speed on the section |
| `TRANSFER` | no | integer | Track transfer function code |
| `ROUGHNESS` | no | integer | Rail roughness code |
| `IMPACT` | no | integer | Impact noise code |
| `CURVATURE` | no | integer | Curvature code |
| `BRIDGE` | no | integer | Bridge transfer code |
| `TRACKSPC` | no | double | Additional rail section property documented by NM as commercial speed on section. Check version-specific rail docs if this field matters to your study |
| `ISTUNNEL` | no | boolean | `0/false` no tunnel, `1/true` tunnel |

Small example:

```csv
IDSECTION,THE_GEOM,NTRACK,TRACKSPD,TRANSFER,ROUGHNESS,IMPACT,CURVATURE,BRIDGE,TRACKSPC,ISTUNNEL
10,"LINESTRING (0 50, 200 50)",2,80,4,1,0,0,0,70,false
```

### `RAIL_TRAFFIC`

Purpose: train traffic linked to railway sections.

| Field | Required | Type | Meaning |
| --- | --- | --- | --- |
| `IDTRAFFIC` | yes | integer primary key | Rail traffic row identifier |
| `IDSECTION` | yes | integer | Links to `RAIL_SECTIONS.IDSECTION` |
| `TRAINTYPE` | yes | string | Train type identifier |
| `TRAINSPD` | yes | double, km/h | Train speed |
| `TDAY` | no | integer | Hourly day train count |
| `TEVENING` | no | integer | Hourly evening train count |
| `TNIGHT` | no | integer | Hourly night train count |

Small example:

```csv
IDTRAFFIC,IDSECTION,TRAINTYPE,TRAINSPD,TDAY,TEVENING,TNIGHT
1,10,"FRET",70,2,1,1
```

### `SOURCES_GEOM`

Purpose: generic point, line, or multiline sources. Use this when emissions are already known or generated by another script.

| Field | Required | Type | Meaning |
| --- | --- | --- | --- |
| `PK` or another integer primary key | yes | integer | Source identifier |
| `THE_GEOM` | yes | 3D `POINT`, `MULTIPOINT`, `LINESTRING`, or `MULTILINESTRING` | Source geometry with Z |
| `HZD63` ... `HZD8000` | no | double | Embedded day emission by band |
| `HZE63` ... `HZE8000` | no | double | Embedded evening emission by band |
| `HZN63` ... `HZN8000` | no | double | Embedded night emission by band |
| `YAW` | no | double, degrees | Source horizontal orientation |
| `PITCH` | no | double, degrees | Source vertical orientation |
| `ROLL` | no | double, degrees | Source roll |
| `DIR_ID` | no | integer | Directivity id |

Small example:

```csv
PK,THE_GEOM,YAW,PITCH,ROLL,DIR_ID
1,"POINT Z (50 20 1.5)",0,0,0,0
```

### `SOURCES_EMISSION`

Purpose: source emission levels by period for `Noise_level_from_source`.

| Field | Required | Type | Meaning |
| --- | --- | --- | --- |
| `IDSOURCE` | yes | integer | Links to source primary key |
| `PERIOD` | yes | string | Period label |
| `HZ63`, `HZ125`, `HZ250`, `HZ500`, `HZ1000`, `HZ2000`, `HZ4000`, `HZ8000` | useful | double, dB | Emission sound power level by band |

Small example:

```csv
IDSOURCE,PERIOD,HZ63,HZ125,HZ250,HZ500,HZ1000,HZ2000,HZ4000,HZ8000
1,D,80,82,84,86,88,86,82,78
```

### `RECEIVERS`

Purpose: receiver points where noise levels are computed.

| Field | Required | Type | Meaning |
| --- | --- | --- | --- |
| `PK` | yes | integer primary key | Receiver identifier |
| `THE_GEOM` | yes | 3D `POINT` or `MULTIPOINT` | Receiver geometry. Z is receiver height relative to ground for generated receivers |
| `BUILD_PK` | no | integer | Building id for facade/building receiver workflows |

Small example:

```csv
PK,THE_GEOM
1,"POINT Z (40 30 4)"
```

### `DEM`

Purpose: digital elevation model used for terrain and altitude deduction.

| Field | Required | Type | Meaning |
| --- | --- | --- | --- |
| `THE_GEOM` | yes | 3D `POINT` or `MULTIPOINT` | DEM point with Z altitude above sea level |

Small example:

```csv
THE_GEOM
"POINT Z (0 0 6.2)"
```

### `GROUND`

Purpose: ground absorption surfaces.

| Field | Required | Type | Meaning |
| --- | --- | --- | --- |
| `THE_GEOM` | yes | 2D `POLYGON` or `MULTIPOLYGON` | Ground surface geometry |
| `G` | yes | double `0-1` | Ground absorption, `0` hard, `1` soft |

Small example:

```csv
THE_GEOM,G
"POLYGON ((0 0, 100 0, 100 100, 0 100, 0 0))",0.3
```

Notes:

- Ground polygons should not overlap, because each point can have only one `G` value.

### `DIRECTIVITY`

Purpose: source directivity attenuation by angle and frequency.

| Field | Required | Type | Meaning |
| --- | --- | --- | --- |
| `DIR_ID` | yes | integer | Directivity sphere identifier |
| `THETA` | yes | double, degrees | Vertical angle, `-90` bottom to `90` top |
| `PHI` | yes | double, degrees | Horizontal angle, `0-360` |
| `HZ63`, `HZ125`, `HZ250`, `HZ500`, `HZ1000`, `HZ2000`, `HZ4000`, `HZ8000` | yes | double, dB | Attenuation by band |

Small example:

```csv
DIR_ID,THETA,PHI,HZ63,HZ125,HZ250,HZ500,HZ1000,HZ2000,HZ4000,HZ8000
7,0,0,0,0,0,0,0,0,0,0
```

Note: the general directivity input documentation uses `HZ` columns. Some WPS descriptions use an `LW` prefix for directivity columns. Keep the table prefix aligned with the script and `frequencyFieldPrepend` setting you are using.

### `ATMOSPHERIC_SETTINGS`

Purpose: period-specific propagation atmosphere.

| Field | Required | Type | Meaning |
| --- | --- | --- | --- |
| `PERIOD` | yes | string primary key | Period label |
| `WINDROSE` | yes | array of 16 doubles | Favourable propagation occurrence by direction sector |
| `TEMPERATURE` | yes | double, Celsius | Air temperature |
| `PRESSURE` | yes | double, Pascal | Air pressure |
| `HUMIDITY` | yes | double, percent | Relative humidity |
| `GDISC` | yes | boolean | Accept ground discontinuity, default true |
| `PRIME2520` | yes | boolean | Use prime values for equation 2.5.20, default false |

Small example:

```sql
INSERT INTO ATMOSPHERIC_SETTINGS
  (PERIOD, WINDROSE, TEMPERATURE, PRESSURE, HUMIDITY, GDISC, PRIME2520)
VALUES
  ('D', ARRAY[0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5], 15, 101325, 70, true, false);
```

Note: exact array syntax depends on the database/import path. The important shape is one period row with 16 wind-sector values.

## WPS Parameters

### `Delaunay_Grid`

Purpose: generate receivers and triangles.

| Parameter | Required | Type | Default | Meaning |
| --- | --- | --- | --- | --- |
| `tableBuilding` | yes | string | `BUILDINGS` if omitted in script body | Building table |
| `sourcesTableName` | yes | string | none | Source or road table used to avoid placing receivers on sources |
| `fenceTableName` | no | string | none | Table whose extent limits receiver generation |
| `fence` | no | geometry | none | Direct polygon fence |
| `maxCellDist` | no | double, m | `600` | Sub-domain size for Delaunay generation |
| `skipCellNoSourcesMinimalDistance` | no | double, m | disabled | Skip cells with no nearby sources |
| `roadWidth` | no | double, m | `2` | No receivers closer than this distance to roads/sources |
| `buildingBuffer` | no | double, m | `2` | No receivers closer than this distance to buildings |
| `maxArea` | no | double, m2 | `2500` | Maximum triangle area. Smaller means more receivers |
| `height` | no | double, m | `4` | Receiver height relative to ground |
| `outputTableName` | no | string | `RECEIVERS` | Receiver output table |
| `isoSurfaceInBuildings` | no | boolean | `false` | Allow isosurfaces over building footprints |
| `fenceNegativeBuffer` | no | double, m | `0` | Shrink receiver fence |
| `exportTrianglesGeometries` | no | boolean | `false` | Store triangle geometries in `TRIANGLES` |

Small example:

```json
{
  "tableBuilding": "BUILDINGS",
  "sourcesTableName": "ROADS",
  "maxCellDist": 600,
  "roadWidth": 2,
  "buildingBuffer": 2,
  "maxArea": 2500,
  "height": 4,
  "outputTableName": "RECEIVERS"
}
```

### `Noise_level_from_traffic`

Purpose: compute receiver levels directly from road traffic.

| Parameter | Required | Type | Default | Meaning |
| --- | --- | --- | --- | --- |
| `tableBuilding` | yes | string | none | Building table |
| `tableRoads` | yes | string | none | Road traffic geometry table |
| `tableRoadsTraffic` | no | string | none | Custom-period traffic table |
| `tableReceivers` | yes | string | none | Receiver table |
| `tableDEM` | no | string | none | DEM table |
| `tableGroundAbs` | no | string | none | Ground absorption table |
| `tableSourceDirectivity` | no | string | default directivity handling | Directivity table |
| `tablePeriodAtmosphericSettings` | no | string | none | Period atmosphere table |
| `paramWallAlpha` | no | double | `0.1` | Wall absorption coefficient, `0` reflective and `1` absorbent |
| `confReflOrder` | no | integer | documented `1`; some script versions initialize `0` if omitted | Reflection order. Set explicitly |
| `confMaxSrcDist` | no | double, m | `150` | Maximum source-receiver distance |
| `confMaxReflDist` | no | double, m | `50` | Reflection search distance |
| `confThreadNumber` | no | integer | `0` | Thread count, `0` automatic |
| `confDiffVertical` | no | boolean | `false` | Vertical-edge diffraction |
| `confDiffHorizontal` | no | boolean | `false` | Horizontal-edge diffraction |
| `confExportSourceId` | no | boolean | `false` | Keep source id in output |
| `confHumidity` | no | double, percent | `70` if using default attenuation parameters | Relative humidity |
| `confTemperature` | no | double, Celsius | `15` if using default attenuation parameters | Air temperature |
| `confFavourableOccurrencesDefault` | no | comma string of 16 doubles | all `0.5` | Default favourable propagation occurrence |
| `confRaysName` | no | string | empty | Export rays/table/scene |
| `confMaxError` | no | double, dB | `0.1` | Negligible-source error threshold |
| `frequencyFieldPrepend` | no | string | `HZ` | Frequency column prefix |

Small example:

```json
{
  "tableBuilding": "BUILDINGS",
  "tableRoads": "ROADS",
  "tableReceivers": "RECEIVERS",
  "tableDEM": "DEM",
  "tableGroundAbs": "GROUND",
  "paramWallAlpha": 0.1,
  "confReflOrder": 1,
  "confMaxSrcDist": 500,
  "confMaxReflDist": 100,
  "confDiffHorizontal": true,
  "confThreadNumber": 0,
  "confMaxError": 0.1
}
```

### `Noise_level_from_source`

Purpose: compute receiver levels from generic source geometry and source emissions.

It uses the same propagation parameters as `Noise_level_from_traffic`, except road-specific tables are replaced by source tables.

| Parameter | Required | Type | Default | Meaning |
| --- | --- | --- | --- | --- |
| `tableBuilding` | yes | string | none | Building table |
| `tableSources` | yes | string | none | Generic source geometry table |
| `tableSourcesEmission` | no | string | none | Source emission by period |
| `tableReceivers` | yes | string | none | Receiver table |
| `tableDEM` | no | string | none | DEM table |
| `tableGroundAbs` | no | string | none | Ground absorption table |
| `tableSourceDirectivity` | no | string | default directivity handling | Directivity table |
| `tablePeriodAtmosphericSettings` | no | string | none | Period atmosphere table |
| `paramWallAlpha` | no | double | `0.1` | Wall absorption coefficient, `0` reflective and `1` absorbent |
| `confReflOrder` | no | integer | documented `1`; some script versions initialize `0` if omitted | Reflection order. Set explicitly |
| `confMaxSrcDist` | no | double, m | `150` | Maximum source-receiver distance |
| `confMaxReflDist` | no | double, m | `50` | Reflection search distance |
| `confThreadNumber` | no | integer | `0` | Thread count, `0` automatic |
| `confDiffVertical` | no | boolean | `false` | Vertical-edge diffraction |
| `confDiffHorizontal` | no | boolean | `false` | Horizontal-edge diffraction |
| `confExportSourceId` | no | boolean | `false` | Keep source id in output |
| `confHumidity` | no | double, percent | `70` if using default attenuation parameters | Relative humidity |
| `confTemperature` | no | double, Celsius | `15` if using default attenuation parameters | Air temperature |
| `confFavourableOccurrencesDefault` | no | comma string of 16 doubles | all `0.5` | Default favourable propagation occurrence |
| `confRaysName` | no | string | empty | Export rays/table/scene |
| `confMaxError` | no | double, dB | `0.1` | Negligible-source error threshold |
| `frequencyFieldPrepend` | no | string | `HZ` | Frequency column prefix |

Small example:

```json
{
  "tableBuilding": "BUILDINGS",
  "tableSources": "SOURCES_GEOM",
  "tableSourcesEmission": "SOURCES_EMISSION",
  "tableReceivers": "RECEIVERS",
  "paramWallAlpha": 0.1,
  "confMaxSrcDist": 500,
  "confMaxReflDist": 100,
  "confReflOrder": 1,
  "confDiffHorizontal": true,
  "confExportSourceId": false
}
```

### `Road_Emission_from_Traffic`

Purpose: create an emission table, typically `LW_ROADS`, from road traffic fields.

| Parameter | Required | Type | Default | Meaning |
| --- | --- | --- | --- | --- |
| `tableRoads` | yes | string | none | Road table with D/E/N or custom `PERIOD` traffic fields |
| `coefficientVersion` | no | integer | `2` | CNOSSOS coefficient version, commonly `1` for 2015 and `2` for 2020 |

Small example:

```json
{
  "tableRoads": "ROADS",
  "coefficientVersion": 2
}
```

### `Railway_Emission_from_Traffic`

Purpose: create an emission table, typically `LW_RAILWAY`, from rail section and rail traffic tables.

| Parameter | Required | Type | Default | Meaning |
| --- | --- | --- | --- | --- |
| `tableRailwayTrack` | yes | string | none | Rail section geometry table |
| `tableRailwayTraffic` | yes | string | none | Rail traffic table |

Small example:

```json
{
  "tableRailwayTrack": "RAIL_SECTIONS",
  "tableRailwayTraffic": "RAIL_TRAFFIC"
}
```

### `Create_Isosurface`

Purpose: create contour polygons from receiver levels and the `TRIANGLES` table generated by `Delaunay_Grid`.

| Parameter | Required | Type | Default | Meaning |
| --- | --- | --- | --- | --- |
| `resultTable` | yes | string | none | Receiver level table, usually `RECEIVERS_LEVEL` |
| `isoClass` | no | comma-separated doubles | `35,40,45,50,55,60,65,70,75,80,200` | Noise class breakpoints |
| `resultTableField` | no | string | `LAEQ` | Result field used to build contours |
| `keepTriangles` | no | boolean | `false` | Keep same-class triangles separated |
| `smoothCoefficient` | no | double | `0.5` | Smoothing coefficient. `0` disables smoothing |

Small example:

```json
{
  "resultTable": "RECEIVERS_LEVEL",
  "isoClass": "45,50,55,60,65,70,75,200",
  "resultTableField": "LAEQ",
  "keepTriangles": false,
  "smoothCoefficient": 0.5
}
```

## Minimal End-to-End Example

This is the smallest conceptual road workflow. In practice, create these as spatial database tables with the same projected CRS.

```csv
# BUILDINGS
THE_GEOM,HEIGHT
"POLYGON ((0 0, 20 0, 20 15, 0 15, 0 0))",12

# ROADS
PK,THE_GEOM,LV_D,LV_E,LV_N,HGV_D,HGV_E,HGV_N,LV_SPD_D,LV_SPD_E,LV_SPD_N,HGV_SPD_D,HGV_SPD_E,HGV_SPD_N,PVMT,WAY
1,"LINESTRING (0 30, 100 30)",600,250,80,40,20,10,50,45,40,45,40,35,DEF,3

# RECEIVERS
PK,THE_GEOM
1,"POINT Z (50 60 4)"
```

Then run:

```json
{
  "tableBuilding": "BUILDINGS",
  "tableRoads": "ROADS",
  "tableReceivers": "RECEIVERS",
  "confMaxSrcDist": 500,
  "confReflOrder": 0,
  "confDiffHorizontal": false
}
```

## Sources

- NoiseModelling documentation: https://noisemodelling.readthedocs.io/en/latest/
- Roads input: https://noisemodelling.readthedocs.io/en/latest/Input_roads.html
- Railways input: https://noisemodelling.readthedocs.io/en/latest/Input_railways.html
- Buildings input: https://noisemodelling.readthedocs.io/en/latest/Input_buildings.html
- DEM input: https://noisemodelling.readthedocs.io/en/latest/Input_dem.html
- Ground input: https://noisemodelling.readthedocs.io/en/latest/Input_ground.html
- Directivity input: https://noisemodelling.readthedocs.io/en/latest/Input_directivity.html
- Receivers input: https://noisemodelling.readthedocs.io/en/latest/Input_receivers.html
- Generic source input: https://noisemodelling.readthedocs.io/en/latest/Input_source.html
- Acoustic parameters: https://noisemodelling.readthedocs.io/en/latest/Input_acoustics.html
- Local WPS scripts checked in this repository: `NoiseModelling/wps_scripts/src/main/groovy/org/noise_planet/noisemodelling/wps`
- Local WPS import/export scripts checked for file formats: `NoiseModelling/wps_scripts/src/main/groovy/org/noise_planet/noisemodelling/wps/Import_and_Export` (`Import_File.groovy`, `Import_Folder.groovy`, `Import_Asc_File.groovy`, `Import_Asc_Folder.groovy`, `Import_OSM.groovy`, `Export_Table.groovy`)
