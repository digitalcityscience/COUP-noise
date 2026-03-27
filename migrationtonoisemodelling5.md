# COUP-noise Migration To NoiseModelling 5.x

## Recommendation

Keep `COUP-noise` as the public API and worker service.

Replace the internals of `noise_analysis/noisemap.py` with a direct, headless
NoiseModelling 5.x integration.

Do not insert GeoServer/WPS as an extra network hop.

The cleanest target is:

`Flask API -> Celery worker -> NoiseModelling_without_gui runner -> GeoJSON/PNG result`

## Why This Is The Right Split

`COUP-noise` already has the right outer architecture:

- request handling in Flask
- async execution in Celery
- Redis-backed task state and cache
- CityPyo as the scenario data source
- GeoJSON and PNG result shaping for downstream clients

Those parts should stay.

The part that should change is only the calculation engine.

## Current COUP-noise Engine

Today the worker uses a legacy, embedded engine in `noise_analysis/noisemap.py`.

Observed characteristics:

- It boots its own H2 server subprocess.
- It talks to H2 through the PostgreSQL wire protocol via `psycopg2`.
- It registers old `org.orbisgis.noisemap.h2.*` aliases such as:
  - `BR_EvalSource`
  - `BR_SpectrumRepartition`
  - `BR_TriGrid`
- It manually builds SQL tables and inserts geometry row by row.
- It exports the final result with `GeoJsonWrite`.
- It is described in the README as adapted from NoiseModelling and using a
  simplified implementation of NMPB-08.

Important limitations in the current implementation:

- Building heights are discarded.
- Terrain is ignored.
- Ground absorption is ignored.
- Roads and rail are mixed in one custom schema.
- Traffic is reduced from daily counts to a single-hour approximation.
- The engine bundles old `noisemap-core-2.1.2-SNAPSHOT.jar` style artifacts,
  not current NoiseModelling 5.x modules.

## Target Engine

Use the official headless runner distributed from the current `wps_scripts`
module, which exposes:

- an embedded H2GIS database
- script execution without GeoServer
- direct execution of NoiseModelling Groovy scripts

The relevant scripts for COUP-noise are:

- `Import_and_Export/Import_File.groovy`
- `Receivers/Delaunay_Grid.groovy`
- `NoiseModelling/Road_Emission_from_Traffic.groovy`
- `NoiseModelling/Railway_Emission_from_Traffic.groovy`
- `NoiseModelling/Noise_level_from_source.groovy`
- `Acoustic_Tools/Create_Isosurface.groovy`
- `Import_and_Export/Export_Table.groovy`

## Recommended Migration Strategy

### Phase 1: Keep API Contract, Swap Engine

Keep these files mostly unchanged:

- `endpoints.py`
- `tasks.py`
- `services.py`
- `format_result.py`

Replace only the implementation behind:

- `services.calculate_and_return_result`
- `noise_analysis.noisemap.noise_calculation`

In practice, create a new adapter module, for example:

- `noise_analysis/nm5_runner.py`

and let `services.py` call that instead of the legacy `noisemap.py` path.

### Phase 2: Run NoiseModelling 5.x As A Subprocess

Do not try to re-create the old `psycopg2` H2 pattern.

Instead:

1. Create a temporary working directory for each task.
2. Materialize normalized input files there.
3. Call the official NoiseModelling runner (`bin/wps_scripts` or
   `org.noise_planet.noisemodelling.runner.Main`) multiple times.
4. Read the exported GeoJSON result.
5. Reuse existing clipping and PNG conversion logic.

This is the least risky option for a Python service because:

- the Java side stays isolated
- runner upgrades are simpler
- failures are easier to inspect
- no GeoServer deployment is required

### Phase 3: Normalize Inputs Before Execution

COUP-noise should stop building custom SQL tables for the engine.

Instead it should produce NoiseModelling-native tables or files.

## Data Mapping

### Buildings

Current source:

- CityPyo layer `upperfloor`

Target NoiseModelling table:

- `BUILDINGS`

Required fields:

- `THE_GEOM`
- `HEIGHT`

Notes:

- This is the biggest migration gap.
- Current COUP-noise strips building properties and keeps only geometry.
- Current NoiseModelling 5.x needs `HEIGHT`.
- If CityPyo can provide building height, pass it through directly.
- If CityPyo only provides roof Z or floor counts, derive `HEIGHT` in the
  adapter.
- If no reliable height exists, add a temporary fallback default height, but
  treat that as a compatibility mode only.

### Roads

Current source:

- CityPyo roads GeoJSON with custom properties such as:
  - `car_traffic_daily`
  - `truck_traffic_daily`
  - `max_speed`
  - `traffic_settings_adjustable`

Target NoiseModelling table:

- `ROADS`

Recommended generated fields:

- `PK`
- `THE_GEOM`
- `LV_D`, `LV_E`, `LV_N`
- `MV_D`, `MV_E`, `MV_N`
- `HGV_D`, `HGV_E`, `HGV_N`
- `WAV_D`, `WAV_E`, `WAV_N`
- `WBV_D`, `WBV_E`, `WBV_N`
- `LV_SPD_D`, `LV_SPD_E`, `LV_SPD_N`
- `MV_SPD_D`, `MV_SPD_E`, `MV_SPD_N`
- `HGV_SPD_D`, `HGV_SPD_E`, `HGV_SPD_N`
- `WAV_SPD_D`, `WAV_SPD_E`, `WAV_SPD_N`
- `WBV_SPD_D`, `WBV_SPD_E`, `WBV_SPD_N`
- `PVMT`
- `JUNC_TYPE`
- `JUNC_DIST`
- `WAY`

Suggested compatibility mapping:

- `car_traffic_daily` -> `LV_*`
- `truck_traffic_daily` -> `HGV_*`
- `MV_*`, `WAV_*`, `WBV_*` -> `0`
- `max_speed` -> all `*_SPD_*`
- `PVMT` -> default `DEF`
- `JUNC_TYPE` -> `0`
- `JUNC_DIST` -> `0`
- `WAY` -> `3`

Open design choice:

- Preserve the current single-hour approximation, or
- introduce real day/evening/night distribution.

For a first migration, preserve current behavior as closely as possible.

### Rail

Current source:

- rail features are mixed into the same roads feed using:
  - `road_type = railroad`
  - `train_speed`
  - `trains_per_hour`
  - `ground_type`
  - `has_anti_vibration`

Target NoiseModelling 5.x flow:

- separate track geometry table
- separate traffic table
- `Railway_Emission_from_Traffic.groovy`

This is not drop-in compatible.

Recommended approach:

- Phase 1: road-only migration if business requirements allow it
- Phase 2: add a rail splitter in the adapter and route rail through the
  railway emission script

Rail support is the second biggest migration gap after building height.

### Terrain And Ground

Current COUP-noise behavior:

- flat world
- no DEM
- no ground absorption table
- only a scalar `wall_absorption`

NoiseModelling 5.x behavior:

- `DEM` is optional
- ground absorption table is optional
- wall absorption can be passed as a parameter

Recommended migration path:

- Phase 1: no DEM, no ground table, map `wall_absorption` to the wall
  absorption parameter
- Phase 2: add DEM and ground once base parity is stable

This keeps the first migration close to current COUP-noise results.

## Recommended Execution Pipeline

For each task:

1. Fetch buildings and roads from CityPyo.
2. Apply `traffic_quota` and `max_speed` exactly as today.
3. Reproject to `EPSG:25832` as today.
4. Build normalized input files for NoiseModelling 5.x.
5. Import `BUILDINGS` and `ROADS`.
6. Generate `RECEIVERS` and `TRIANGLES` with `Delaunay_Grid`.
7. Generate `LW_ROADS` with `Road_Emission_from_Traffic`.
8. Run propagation with `Noise_level_from_source`.
9. Generate `CONTOURING_NOISE_MAP` with `Create_Isosurface`.
10. Export result to GeoJSON.
11. Clip to `project_area`.
12. Convert to PNG when requested.

## Parameter Mapping

### Current COUP-noise settings

- `max_prop_distance = 750`
- `max_wall_seeking_distance = 50`
- `road_with = 1.5`
- `receiver_densification = 2.8`
- `max_triangle_area = 275`
- `sound_reflection_order = 0`
- `sound_diffraction_order = 0`
- `wall_absorption = 0.23`

### Suggested NoiseModelling 5.x mapping

- `Delaunay_Grid.maxCellDist` -> `750`
- `Delaunay_Grid.roadWidth` -> `1.5`
- `Delaunay_Grid.maxArea` -> `275`
- `Noise_level_from_source.confMaxSrcDist` -> `750`
- `Noise_level_from_source.confMaxReflDist` -> `50`
- `Noise_level_from_source.confReflOrder` -> `0`
- `Noise_level_from_source.confDiffVertical` -> `false`
- `Noise_level_from_source.confDiffHorizontal` -> `false`
- `Noise_level_from_source.paramWallAlpha` -> request `wall_absorption`

Compatibility note:

- `receiver_densification` in the old engine does not map one-to-one to the
  new receiver pipeline. `Delaunay_Grid.maxArea`, `roadWidth`, `buildingBuffer`,
  and receiver height must be tuned together during validation.

## Preserve Current Result Contract

Keep the API outputs unchanged:

- default result format `geojson`
- optional result format `png`
- clip to project area
- keep category-style output expected by clients

To preserve current category semantics, configure isosurface classes explicitly
instead of using the default NoiseModelling classes.

Suggested `isoClass` for compatibility with current `idiso` buckets:

- `45,50,55,60,65,70,75,200`

After export, normalize field names if necessary so the response still exposes:

- `idiso`
- `cell_id`

## Files To Change First

### Keep

- `endpoints.py`
- `tasks.py`
- `cache.py`
- most of `services.py`
- most of `format_result.py`

### Replace Or Introduce

- replace `noise_analysis/noisemap.py`
- add `noise_analysis/nm5_runner.py`
- add `noise_analysis/schema_adapter.py`
- possibly update `cityPyo.py` so building height attributes are preserved

## Lowest-Risk Implementation Plan

### Step 1

Add an adapter that writes two local files:

- `buildings.geojson`
- `roads.geojson`

with NoiseModelling-compatible properties.

### Step 2

Call the official headless runner from the worker with subprocess execution.

### Step 3

Export `CONTOURING_NOISE_MAP.geojson` and feed it into the existing
`clip_gdf_to_project_area` and `convert_result_to_png`.

### Step 4

Validate output parity against the current engine for:

- unchanged scenario settings
- several traffic quotas
- several max speeds
- wall absorption changes

### Step 5

Only after road parity is acceptable:

- add rail support
- add real building heights if still missing
- add DEM and ground absorption

## What Not To Do

- Do not add GeoServer/WPS as a remote dependency.
- Do not keep the old H2-over-psycopg2 pattern.
- Do not rewrite the Flask/Celery API surface first.
- Do not combine road and rail in one custom emission path in the new engine.

## Open Questions Before Full Cutover

- Can CityPyo provide reliable building heights now?
- Do clients really need rail in the first migration?
- Should day/evening/night traffic be modeled explicitly instead of preserving
  the current hourly approximation?
- Is result parity more important than scientific improvement for the first
  release?

## Final Recommendation

The cleanest upgrade is:

1. keep `COUP-noise` as the API and orchestration service
2. replace only the legacy engine
3. use headless NoiseModelling 5.x directly from the worker
4. migrate roads first
5. add rail, DEM, and richer building data after parity is reached
