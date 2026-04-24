import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

import geopandas

from noise_analysis.calculation_settings import CalculationSettings
from noise_analysis.cityPyo import CityPyo
from noise_analysis.format_result import clip_gdf_to_project_area, convert_result_to_png
from noise_analysis.schema_adapter import prepare_nm5_input_files


RUNNER_ENV_VAR = "NOISEMODELLING_RUNNER"
ENGINE_OUTPUT_PERIOD_ENV_VAR = "NM5_OUTPUT_PERIOD"
KEEP_WORKDIR_ENV_VAR = "NOISEMODELLING_KEEP_WORKDIR"

DEFAULT_DB_NAME = "nm5"
DEFAULT_WALL_ABSORPTION = 0.23
DEFAULT_OUTPUT_PERIOD = "D"
ISO_CLASSES = "45,50,55,60,65,70,75,200"
MERGED_SOURCES_TABLE = "SOURCES"


def _workspace_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _wps_root() -> Path:
    return _workspace_root() / "NoiseModelling" / "wps_scripts" / "src" / "main" / "groovy" / "org" / "noise_planet" / "noisemodelling" / "wps"


def _script_path(*parts: str) -> Path:
    return _wps_root().joinpath(*parts)


def _local_script_path(*parts: str) -> Path:
    return _workspace_root().joinpath(*parts)


def _find_runner_executable() -> Path:
    configured_runner = os.getenv(RUNNER_ENV_VAR)
    if configured_runner:
        runner_path = Path(configured_runner).expanduser()
        if runner_path.exists():
            return runner_path
        raise FileNotFoundError(f"{RUNNER_ENV_VAR} points to a missing file: {runner_path}")

    candidate_paths = [
        _workspace_root()
        / "NoiseModelling"
        / "wps_scripts"
        / "build"
        / "install"
        / "NoiseModelling_without_gui"
        / "bin"
        / "wps_scripts.bat",
        _workspace_root()
        / "NoiseModelling"
        / "wps_scripts"
        / "build"
        / "install"
        / "NoiseModelling_without_gui"
        / "bin"
        / "wps_scripts",
        _workspace_root()
        / "NoiseModelling"
        / "wps_scripts"
        / "build"
        / "install"
        / "NoiseModelling_without_gui"
        / "bin"
        / "NoiseModelling_without_gui.bat",
        _workspace_root()
        / "NoiseModelling"
        / "wps_scripts"
        / "build"
        / "install"
        / "NoiseModelling_without_gui"
        / "bin"
        / "NoiseModelling_without_gui",
    ]

    for candidate_path in candidate_paths:
        if candidate_path.exists():
            return candidate_path

    raise FileNotFoundError(
        "NoiseModelling 5 runner not found. Build the bundled wps_scripts distribution "
        "or set NOISEMODELLING_RUNNER to the executable path."
    )


def _base_runner_command(runner_path: Path) -> List[str]:
    if runner_path.suffix.lower() in {".bat", ".cmd"}:
        return ["cmd.exe", "/c", str(runner_path)]
    return [str(runner_path)]


def _serialize_runner_args(parameters: Mapping[str, Any]) -> List[str]:
    serialized_args: List[str] = []

    for key, value in parameters.items():
        if value is None:
            continue

        if isinstance(value, bool):
            serialized_args.extend([f"-{key}", str(value).lower()])
            continue

        serialized_args.extend([f"-{key}", str(value)])

    return serialized_args


def _run_wps_script(
    runner_path: Path,
    workdir: Path,
    db_name: str,
    script_path: Path,
    parameters: Mapping[str, Any],
) -> None:
    started_at = time.monotonic()
    step_name = script_path.name
    print(f"[nm5] starting {step_name}", flush=True)
    command = _base_runner_command(runner_path)
    command.extend(
        [
            "-w",
            str(workdir),
            "-d",
            db_name,
            "-s",
            str(script_path),
        ]
    )
    command.extend(_serialize_runner_args(parameters))

    completed_process = subprocess.run(
        command,
        cwd=_workspace_root(),
        check=False,
        capture_output=True,
        text=True,
    )
    elapsed_seconds = time.monotonic() - started_at

    if completed_process.returncode != 0:
        stderr = (completed_process.stderr or "").strip()
        stdout = (completed_process.stdout or "").strip()
        output_parts = []
        if stderr:
            output_parts.append(f"stderr:\n{stderr}")
        if stdout:
            output_parts.append(f"stdout:\n{stdout}")
        output = "\n\n".join(output_parts) or "runner exited without output"
        print(
            f"[nm5] failed {step_name} after {elapsed_seconds:.1f}s",
            flush=True,
        )
        raise RuntimeError(f"NoiseModelling runner failed for {script_path.name}: {output}")

    print(f"[nm5] finished {step_name} in {elapsed_seconds:.1f}s", flush=True)


def _load_geojson(path: Path) -> Dict[str, Any]:
    with path.open(encoding="utf-8") as file_handle:
        return json.load(file_handle)


def _empty_feature_collection() -> Dict[str, Any]:
    return {"type": "FeatureCollection", "features": []}


def _preferred_period(gdf: geopandas.GeoDataFrame) -> Optional[str]:
    if "PERIOD" not in gdf.columns:
        return None

    available_periods = [
        str(period).upper()
        for period in gdf["PERIOD"].dropna().astype(str).tolist()
        if str(period).strip()
    ]
    if not available_periods:
        return None

    configured_period = os.getenv(ENGINE_OUTPUT_PERIOD_ENV_VAR, DEFAULT_OUTPUT_PERIOD).upper()
    if configured_period in available_periods:
        return configured_period

    if DEFAULT_OUTPUT_PERIOD in available_periods:
        return DEFAULT_OUTPUT_PERIOD

    return available_periods[0]


def normalize_nm5_result_geojson(exported_geojson: Mapping[str, Any]) -> Dict[str, Any]:
    features = exported_geojson.get("features", [])
    if not features:
        return _empty_feature_collection()

    result_gdf = geopandas.GeoDataFrame.from_features(features, crs="EPSG:25832")
    selected_period = _preferred_period(result_gdf)
    if selected_period:
        period_mask = result_gdf["PERIOD"].astype(str).str.upper() == selected_period
        result_gdf = result_gdf.loc[period_mask].copy()

    if result_gdf.empty:
        return _empty_feature_collection()

    result_gdf = result_gdf.to_crs("EPSG:4326")

    if "ISOLVL" in result_gdf.columns:
        result_gdf["idiso"] = result_gdf["ISOLVL"].astype(int)
    elif "idiso" not in result_gdf.columns:
        raise KeyError("NoiseModelling export did not contain ISOLVL/idiso")

    for cell_id_column in ("CELL_ID", "cell_id", "CELLID", "cellId"):
        if cell_id_column in result_gdf.columns:
            result_gdf["cell_id"] = result_gdf[cell_id_column].astype(int)
            break

    result_columns = ["geometry", "idiso"]
    if "cell_id" in result_gdf.columns:
        result_columns.append("cell_id")

    return json.loads(result_gdf[result_columns].to_json())


def _working_directory() -> Path:
    return Path(tempfile.mkdtemp(prefix="nm5_"))


def _cleanup_working_directory(path: Path) -> None:
    if os.getenv(KEEP_WORKDIR_ENV_VAR):
        return

    shutil.rmtree(path, ignore_errors=True)


def _is_full_mode(calculation_settings: CalculationSettings) -> bool:
    return calculation_settings.noise_engine == "nm5_full"


def _setting_or_default(value: Any, default: Any) -> Any:
    if value is None:
        return default
    return value


def _delaunay_parameters(
    calculation_settings: CalculationSettings,
    has_project_area: bool,
) -> Dict[str, Any]:
    full_mode = _is_full_mode(calculation_settings)
    nm5_settings = calculation_settings.nm5_settings

    parameters: Dict[str, Any] = {
        "tableBuilding": "BUILDINGS",
        "sourcesTableName": MERGED_SOURCES_TABLE,
        "maxCellDist": _setting_or_default(nm5_settings.max_cell_dist, 750),
        "roadWidth": _setting_or_default(nm5_settings.road_width, 1.5),
        "maxArea": _setting_or_default(nm5_settings.max_area, 275),
        "outputTableName": "RECEIVERS",
    }

    if full_mode and has_project_area:
        parameters["fenceTableName"] = "PROJECT_AREA"

    if full_mode:
        parameters.update(
            {
                "height": _setting_or_default(nm5_settings.receiver_height, 4),
                "buildingBuffer": nm5_settings.building_buffer,
                "skipCellNoSourcesMinimalDistance": nm5_settings.skip_cell_no_sources_minimal_distance,
                "fenceNegativeBuffer": nm5_settings.fence_negative_buffer,
                "isoSurfaceInBuildings": nm5_settings.iso_surface_in_buildings,
                "exportTrianglesGeometries": nm5_settings.export_triangles_geometries,
            }
        )

    return parameters


def _noise_level_parameters(
    calculation_settings: CalculationSettings,
    wall_absorption: float,
    has_dem: bool,
    has_ground_absorption: bool,
    has_source_directivity: bool,
    has_atmospheric_settings: bool,
    has_rail_sources: bool,
) -> Dict[str, Any]:
    full_mode = _is_full_mode(calculation_settings)
    nm5_settings = calculation_settings.nm5_settings

    if not full_mode:
        return {
            "tableBuilding": "BUILDINGS",
            "tableSources": MERGED_SOURCES_TABLE,
            "tableReceivers": "RECEIVERS",
            "tableDEM": "DEM" if has_dem else None,
            "paramWallAlpha": wall_absorption,
            "confReflOrder": 0,
            "confMaxSrcDist": 750,
            "confMaxReflDist": 50,
        }

    return {
        "tableBuilding": "BUILDINGS",
        "tableSources": MERGED_SOURCES_TABLE,
        "tableReceivers": "RECEIVERS",
        "tableDEM": "DEM" if has_dem else None,
        "tableGroundAbs": "GROUND_ABSORPTION" if has_ground_absorption else None,
        "tableSourceDirectivity": "SOURCE_DIRECTIVITY" if has_source_directivity else None,
        "tablePeriodAtmosphericSettings": "ATMOSPHERIC_SETTINGS" if has_atmospheric_settings else None,
        "paramWallAlpha": wall_absorption,
        "confReflOrder": _setting_or_default(nm5_settings.reflection_order, 1),
        "confMaxSrcDist": _setting_or_default(nm5_settings.max_source_distance, 750),
        "confMaxReflDist": _setting_or_default(nm5_settings.max_reflection_distance, 350),
        "confThreadNumber": _setting_or_default(nm5_settings.thread_number, 0),
        "confDiffVertical": _setting_or_default(nm5_settings.diff_vertical, has_rail_sources),
        "confDiffHorizontal": _setting_or_default(nm5_settings.diff_horizontal, True),
        "confExportSourceId": nm5_settings.export_source_id,
        "confHumidity": nm5_settings.humidity,
        "confTemperature": nm5_settings.temperature,
        "confFavourableOccurrencesDefault": nm5_settings.favourable_occurrences,
        "confRaysName": nm5_settings.rays_name,
        "confMaxError": _setting_or_default(nm5_settings.max_error, 0.1),
    }


def _isosurface_parameters(calculation_settings: CalculationSettings) -> Dict[str, Any]:
    nm5_settings = calculation_settings.nm5_settings
    return {
        "resultTable": "RECEIVERS_LEVEL",
        "isoClass": nm5_settings.iso_classes or ISO_CLASSES,
        "resultTableField": nm5_settings.result_table_field or "LAEQ",
    }


def _run_nm5_pipeline(
    calculation_settings: CalculationSettings,
    buildings_geojson: Mapping[str, Any],
    roads_geojson: Mapping[str, Any],
    project_area_geojson: Optional[Mapping[str, Any]] = None,
    dem_geojson: Optional[Mapping[str, Any]] = None,
    ground_absorption_geojson: Optional[Mapping[str, Any]] = None,
    source_directivity: Any = None,
    atmospheric_settings: Any = None,
) -> Dict[str, Any]:
    runner_path = _find_runner_executable()
    working_directory = _working_directory()
    try:
        prepared_inputs = prepare_nm5_input_files(
            working_directory,
            buildings_geojson,
            roads_geojson,
            calculation_settings.traffic_settings,
            project_area_geojson=project_area_geojson,
            dem_geojson=dem_geojson,
            ground_absorption_geojson=ground_absorption_geojson,
            source_directivity=source_directivity,
            atmospheric_settings=atmospheric_settings,
            full_contract=_is_full_mode(calculation_settings),
        )
        transport_source_count = (
            prepared_inputs.metadata["roads"]["exported_features"]
            + prepared_inputs.metadata["rail"]["exported_sections"]
        )
        if prepared_inputs.metadata["buildings"]["exported_features"] == 0:
            raise ValueError("No building footprints were available for the NoiseModelling 5 adapter.")
        if transport_source_count == 0:
            raise ValueError(
                "No transport features remained after NM5 normalization."
            )

        contouring_geojson_path = working_directory / "contouring_noise_map.geojson"
        wall_absorption = calculation_settings.calculation_settings.resolved_wall_absorption(
            DEFAULT_WALL_ABSORPTION
        )

        if prepared_inputs.project_area_path is not None:
            _run_wps_script(
                runner_path,
                working_directory,
                DEFAULT_DB_NAME,
                _script_path("Import_and_Export", "Import_File.groovy"),
                {
                    "pathFile": prepared_inputs.project_area_path,
                    "inputSRID": 25832,
                    "tableName": "PROJECT_AREA",
                },
            )
        _run_wps_script(
            runner_path,
            working_directory,
            DEFAULT_DB_NAME,
            _script_path("Import_and_Export", "Import_File.groovy"),
            {
                "pathFile": prepared_inputs.buildings_path,
                "inputSRID": 25832,
                "tableName": "BUILDINGS",
            },
        )
        if prepared_inputs.roads_path is not None:
            _run_wps_script(
                runner_path,
                working_directory,
                DEFAULT_DB_NAME,
                _script_path("Import_and_Export", "Import_File.groovy"),
                {
                    "pathFile": prepared_inputs.roads_path,
                    "inputSRID": 25832,
                    "tableName": "ROADS",
                },
            )
        if prepared_inputs.rail_sections_path is not None:
            _run_wps_script(
                runner_path,
                working_directory,
                DEFAULT_DB_NAME,
                _script_path("Import_and_Export", "Import_File.groovy"),
                {
                    "pathFile": prepared_inputs.rail_sections_path,
                    "inputSRID": 25832,
                    "tableName": "RAIL_SECTIONS",
                },
            )
        if prepared_inputs.rail_traffic_path is not None:
            _run_wps_script(
                runner_path,
                working_directory,
                DEFAULT_DB_NAME,
                _script_path("Import_and_Export", "Import_File.groovy"),
                {
                    "pathFile": prepared_inputs.rail_traffic_path,
                    "tableName": "RAIL_TRAFFIC",
                },
            )
        if prepared_inputs.dem_path is not None:
            _run_wps_script(
                runner_path,
                working_directory,
                DEFAULT_DB_NAME,
                _script_path("Import_and_Export", "Import_File.groovy"),
                {
                    "pathFile": prepared_inputs.dem_path,
                    "inputSRID": 25832,
                    "tableName": "DEM",
                },
            )
        if prepared_inputs.ground_absorption_path is not None:
            _run_wps_script(
                runner_path,
                working_directory,
                DEFAULT_DB_NAME,
                _script_path("Import_and_Export", "Import_File.groovy"),
                {
                    "pathFile": prepared_inputs.ground_absorption_path,
                    "inputSRID": 25832,
                    "tableName": "GROUND_ABSORPTION",
                },
            )
        if prepared_inputs.source_directivity_path is not None:
            _run_wps_script(
                runner_path,
                working_directory,
                DEFAULT_DB_NAME,
                _script_path("Import_and_Export", "Import_File.groovy"),
                {
                    "pathFile": prepared_inputs.source_directivity_path,
                    "tableName": "SOURCE_DIRECTIVITY",
                },
            )
        if prepared_inputs.atmospheric_settings_path is not None:
            _run_wps_script(
                runner_path,
                working_directory,
                DEFAULT_DB_NAME,
                _local_script_path("noise_analysis", "wps", "Atmospheric_Settings_From_Csv.groovy"),
                {
                    "pathFile": prepared_inputs.atmospheric_settings_path,
                    "tableName": "ATMOSPHERIC_SETTINGS",
                },
            )
        if prepared_inputs.roads_path is not None:
            _run_wps_script(
                runner_path,
                working_directory,
                DEFAULT_DB_NAME,
                _script_path("NoiseModelling", "Road_Emission_from_Traffic.groovy"),
                {
                    "tableRoads": "ROADS",
                },
            )
        if prepared_inputs.rail_sections_path is not None and prepared_inputs.rail_traffic_path is not None:
            _run_wps_script(
                runner_path,
                working_directory,
                DEFAULT_DB_NAME,
                _local_script_path("noise_analysis", "wps", "Railway_Emission_from_Traffic.groovy"),
                {
                    "tableRailwayTrack": "RAIL_SECTIONS",
                    "tableRailwayTraffic": "RAIL_TRAFFIC",
                },
            )
        _run_wps_script(
            runner_path,
            working_directory,
            DEFAULT_DB_NAME,
            _local_script_path("noise_analysis", "wps", "Merge_Transport_Sources.groovy"),
            {
                "roadTable": "LW_ROADS" if prepared_inputs.roads_path is not None else None,
                "railTable": (
                    "LW_RAILWAY"
                    if prepared_inputs.rail_sections_path is not None and prepared_inputs.rail_traffic_path is not None
                    else None
                ),
                "outputTable": MERGED_SOURCES_TABLE,
            },
        )
        _run_wps_script(
            runner_path,
            working_directory,
            DEFAULT_DB_NAME,
            _script_path("Receivers", "Delaunay_Grid.groovy"),
            _delaunay_parameters(calculation_settings, prepared_inputs.project_area_path is not None),
        )
        _run_wps_script(
            runner_path,
            working_directory,
            DEFAULT_DB_NAME,
            _script_path("NoiseModelling", "Noise_level_from_source.groovy"),
            _noise_level_parameters(
                calculation_settings,
                wall_absorption,
                prepared_inputs.dem_path is not None,
                prepared_inputs.ground_absorption_path is not None,
                prepared_inputs.source_directivity_path is not None,
                prepared_inputs.atmospheric_settings_path is not None,
                prepared_inputs.metadata["rail"]["exported_sections"] > 0,
            ),
        )
        _run_wps_script(
            runner_path,
            working_directory,
            DEFAULT_DB_NAME,
            _script_path("Acoustic_Tools", "Create_Isosurface.groovy"),
            _isosurface_parameters(calculation_settings),
        )
        _run_wps_script(
            runner_path,
            working_directory,
            DEFAULT_DB_NAME,
            _script_path("Import_and_Export", "Export_Table.groovy"),
            {
                "exportPath": contouring_geojson_path,
                "tableToExport": "CONTOURING_NOISE_MAP",
            },
        )

        return normalize_nm5_result_geojson(_load_geojson(contouring_geojson_path))
    finally:
        _cleanup_working_directory(working_directory)


def noise_calculation(calculation_settings, buildings_geojson, roads_geojson, cityPyo_user):
    calculation_settings = CalculationSettings.from_mapping(calculation_settings)
    citypyo = CityPyo()
    full_mode = _is_full_mode(calculation_settings)
    project_area_geojson = citypyo.get_project_area_for_user(cityPyo_user)
    dem_geojson = citypyo.get_dem_for_user(cityPyo_user, required=full_mode)
    ground_absorption_geojson = citypyo.get_ground_absorption_for_user(cityPyo_user, required=full_mode)
    source_directivity = citypyo.get_source_directivity_for_user(cityPyo_user, required=False)
    atmospheric_settings = citypyo.get_atmospheric_settings_for_user(cityPyo_user, required=full_mode)
    noise_result_geojson = _run_nm5_pipeline(
        calculation_settings,
        buildings_geojson,
        roads_geojson,
        project_area_geojson=project_area_geojson,
        dem_geojson=dem_geojson,
        ground_absorption_geojson=ground_absorption_geojson,
        source_directivity=source_directivity,
        atmospheric_settings=atmospheric_settings,
    )
    noise_result_geojson = clip_gdf_to_project_area(noise_result_geojson, cityPyo_user)

    if calculation_settings.result_format == "png":
        return convert_result_to_png(noise_result_geojson, calculation_settings.png_style or "raw")

    return noise_result_geojson
