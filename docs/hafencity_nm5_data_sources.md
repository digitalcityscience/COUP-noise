# HafenCity NM5 Data Sources

This note documents the concrete public datasets pulled for the local
HafenCity `nm5_full` preparation package and how they map into the COUP-noise
input contract.

The generated data package is intentionally not tracked in git:

- local CityPyo-style folder: `downloads/hafencity_full/citypyo/hafencity_full`
- source manifest: `downloads/hafencity_full/manifest.md`
- generated summary: `downloads/hafencity_full/processed/subset_summary.json`

Use it locally with `CITY_PYO=downloads/hafencity_full/citypyo`,
`city_pyo_user=hafencity_full`, and `NOISE_ENGINE=nm5_full`.

## Area

The AOI is the existing repo demo polygon in HafenCity:

- source file: `fixtures/citypyo/demo/project_area.geojson`
- source CRS: WGS84 longitude/latitude
- prepared CRS: `EPSG:25832`
- prepared file: `downloads/hafencity_full/processed/project_area_25832.geojson`

The prepared UTM32 bounding box is:

| Coordinate | Value |
| --- | ---: |
| min x | 566269.8306045276 |
| min y | 5932920.3843816295 |
| max x | 567029.5659307276 |
| max y | 5933709.686410237 |

## Runnable Local Layers

These files were copied into the local CityPyo-style folder:

| COUP-noise layer | Local file | Source basis |
| --- | --- | --- |
| `project_area.geojson` | `downloads/hafencity_full/citypyo/hafencity_full/project_area.geojson` | repo demo AOI |
| `upperfloor.geojson` | `downloads/hafencity_full/citypyo/hafencity_full/upperfloor.geojson` | Hamburg LoD2 CityGML footprints and heights |
| `roads.geojson` | `downloads/hafencity_full/citypyo/hafencity_full/roads.geojson` | Geofabrik Hamburg OSM roads and rail enriched with Hamburg traffic-count assignments and hvv GTFS rail service data where matched |
| `dem.geojson` | `downloads/hafencity_full/citypyo/hafencity_full/dem.geojson` | Hamburg DGM1 XYZ tile clipped to AOI |
| `ground_absorption.geojson` | `downloads/hafencity_full/citypyo/hafencity_full/ground_absorption.geojson` | Hamburg ALKIS actual-use polygons mapped to NM5 `G` values |
| `atmospheric_settings.csv` | `downloads/hafencity_full/citypyo/hafencity_full/atmospheric_settings.csv` | DWD station `01975` recent temperature, humidity, pressure, and wind |

Reference files in the same folder are not consumed directly by the service:

- `traffic_counts_reference.geojson`: AOI-filtered Hamburg traffic-count points;
  the nearest-road assignments are embedded in `roads.geojson`.
- `alkis_reference.geojson`: AOI-intersecting ALKIS geometries used to derive
  the runnable ALKIS ground absorption layer.

## Sources

| Dataset | Provider | Source URL | Local raw file | Prepared output |
| --- | --- | --- | --- | --- |
| Hamburg OSM GeoPackage | Geofabrik / OpenStreetMap contributors | https://download.geofabrik.de/europe/germany/hamburg.html and direct file `https://download.geofabrik.de/europe/germany/hamburg-latest-free.gpkg.zip` | `downloads/hafencity_full/raw/geofabrik_hamburg_latest_free.gpkg.zip` | `processed/roads_osm_hafencity.geojson`, `processed/ground_absorption_osm_hafencity.geojson` fallback |
| Road traffic counts | Hamburg Transparenzportal | https://suche.transparenz.hamburg.de/dataset/verkehrsstaerken-hamburg13 | `raw/verkehrsstaerken_geojson.zip`, `raw/verkehrsstaerken_csv.zip` | `processed/traffic_counts_hafencity.geojson`, `processed/traffic_count_assignments_hafencity.csv`, enriched `roads.geojson` |
| hvv GTFS | Hamburg Transparenzportal / hvv | https://suche.transparenz.hamburg.de/dataset/hvv-fahrplandaten-gtfs-april-2026-bis-dezember-2026 | `raw/hvv_gtfs_20260408.zip` | `processed/gtfs_rail_shapes_hafencity.geojson`, `processed/gtfs_rail_assignments_hafencity.csv`, enriched `roads.geojson` |
| LoD2 buildings | Hamburg Transparenzportal | https://suche.transparenz.hamburg.de/dataset/3d-gebaeudemodell-lod2-de-hamburg and direct file `https://archiv.transparenz.hamburg.de/hmbtgarchive/HMDK/lod2-de_hh_2023-04-01_162858_snap_1.zip` | `raw/lod2-de_hh_2023-04-01.zip` | `processed/buildings_lod2_hafencity.geojson` |
| DGM1 terrain | Hamburg Transparenzportal | https://suche.transparenz.hamburg.de/dataset/digitales-hoehenmodell-hamburg-dgm-15 and fallback direct file `https://archiv.transparenz.hamburg.de/hmbtgarchive/HMDK/dgm1_2x2km_xyz_hh_2020_04_24_107299_snap_1.ASCII` | `raw/dgm1_2x2km_xyz_hh_2020.ASCII` | `processed/dem_hafencity.geojson` |
| ALKIS selected cadastral data | Hamburg Transparenzportal | https://suche.transparenz.hamburg.de/dataset/alkis-ausgewaehlte-daten-hamburg5 and direct file `https://daten-hamburg.de/opendata/ALKIS_Liegenschaftskarte/ALKIS_Liegenschaftskarte_ausgewaehlteDaten_HH_2026-01-15.zip` | `raw/alkis_liegenschaftskarte_2026-01-15.zip` | `processed/alkis_hafencity_geometries.geojson`, `processed/ground_absorption_alkis_hafencity.geojson` |
| Weather observations | DWD Climate Data Center | https://opendata.dwd.de/climate_environment/CDC/observations_germany/climate/hourly/ | `raw/dwd_*_01975_*.zip` and station catalogs | `processed/atmospheric_settings_01975_recent.csv` |

The 2022 DGM1 URL listed in the Hamburg metadata was also checked:
`https://archiv.transparenz.hamburg.de/hmbtgarchive/HMDK/dgm1_hh_2022-04-30_169660_snap_1.zip`.
On 2026-04-24 it returned HTTP 200 with `Content-Length: 0`, so the prepared
package uses the 2020 2x2 km DGM1 XYZ archive instead.

## Generated Subset Counts

`tools/prepare_hafencity_nm5_subset.py` generated these AOI-scoped counts:

| Output | Count |
| --- | ---: |
| LoD2 building features | 117 |
| DGM DEM points | 583176 |
| OSM road features | 227 |
| OSM rail features inside `roads.geojson` | 117 |
| OSM ground absorption polygons | 143 |
| Hamburg traffic-count points | 4 |
| Hamburg traffic-count assignments to roads | 4 |
| hvv GTFS rail/subway shapes near AOI | 214 |
| OSM rail features enriched from GTFS | 94 |
| ALKIS AOI-intersecting features | 2647 |
| ALKIS ground absorption polygons | 194 |

## Current Data Gaps

The package is runnable as an `nm5_full` input package, but it is still a
first-pass data preparation:

- The four Hamburg traffic-count points inside the AOI are assigned to the
  nearest plausible OSM road segments. Other road segments still use
  OSM-class-based traffic defaults.
- 94 of 117 OSM rail features are assigned to nearby hvv GTFS rail/subway
  shapes. Unmatched rail features keep the fallback rail settings.
- ALKIS actual-use classes are mapped to `G` values by rule. This is better
  than OSM-only land use, but still not a surveyed acoustic surface-material
  model.
- No project-specific `source_directivity` table was found; the package relies
  on NM5 defaults unless such a table is supplied later.

## Reproduction On Another PC

The prepared `downloads/hafencity_full` folder is intentionally ignored by git.
After cloning the repository on another machine, regenerate the data package
instead of committing the downloaded data.

Prerequisites:

- Docker Desktop, for the COUP-noise API/worker stack and bundled NM5 runner
- Python 3.10 or newer
- Internet access for the public Hamburg, OSM, hvv, and DWD downloads
- VS Code with the Jupyter extension, if running the notebook interactively

From the repository root on Windows PowerShell:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install ipykernel ipython
.\.venv\Scripts\python.exe tools\prepare_hafencity_nm5_subset.py
.\.venv\Scripts\python.exe tools\create_hafencity_half_package.py --target-user hafencity_half_10m --dem-spacing 10
```

The first data-prep command creates the full local CityPyo-style package:

```text
downloads/hafencity_full/citypyo/hafencity_full
```

The second command derives the fast notebook package:

```text
downloads/hafencity_full/citypyo/hafencity_half_10m
```

That fast package keeps the western half of the HafenCity AOI and downsamples
the DEM from 1 m to 10 m spacing. It is intended for smoke tests and local
iteration, not final acoustic assessment.

Open
`notebooks/hafencity_nm5_full_simulation.ipynb`, select the `.venv` kernel, and
run the notebook from the top. The Docker-stack cell writes
`outputs/docker-compose.hafencity-nm5-full.yml`, bind-mounts `downloads/`, and
starts the API/worker stack with `NOISE_ENGINE=nm5_full`.

Watch NM5 progress from another PowerShell terminal:

```powershell
docker compose -f docker-compose.yml -f outputs\docker-compose.hafencity-nm5-full.yml logs -f worker_1 worker_2
```

The smoke-test notebook result is written to:

```text
outputs/hafencity_half_10m_nm5_full.geojson
```

For a higher-fidelity run, change `CITY_PYO_USER` in the notebook to
`hafencity_full`, `hafencity_half`, or `hafencity_half_5m`, and increase the
NM5 propagation settings deliberately. Those runs can take much longer.

The preparation scripts use only the Python standard library because this local
environment does not have GDAL, geopandas, rasterio, or pyogrio installed.
