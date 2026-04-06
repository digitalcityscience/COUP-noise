import json
import os
import shutil
import subprocess
import tempfile
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
            if value:
                serialized_args.append(f"-{key}")
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

    if completed_process.returncode != 0:
        stderr = (completed_process.stderr or "").strip()
        stdout = (completed_process.stdout or "").strip()
        output = stderr or stdout or "runner exited without output"
        raise RuntimeError(f"NoiseModelling runner failed for {script_path.name}: {output}")


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


def _run_nm5_pipeline(
    calculation_settings: CalculationSettings,
    buildings_geojson: Mapping[str, Any],
    roads_geojson: Mapping[str, Any],
    dem_geojson: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    runner_path = _find_runner_executable()
    working_directory = _working_directory()
    try:
        prepared_inputs = prepare_nm5_input_files(
            working_directory,
            buildings_geojson,
            roads_geojson,
            calculation_settings.traffic_settings,
            dem_geojson=dem_geojson,
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
            {
                "tableBuilding": "BUILDINGS",
                "sourcesTableName": MERGED_SOURCES_TABLE,
                "maxCellDist": 750,
                "roadWidth": 1.5,
                "maxArea": 275,
                "outputTableName": "RECEIVERS",
            },
        )
        _run_wps_script(
            runner_path,
            working_directory,
            DEFAULT_DB_NAME,
            _script_path("NoiseModelling", "Noise_level_from_source.groovy"),
            {
                "tableBuilding": "BUILDINGS",
                "tableSources": MERGED_SOURCES_TABLE,
                "tableReceivers": "RECEIVERS",
                "tableDEM": "DEM" if prepared_inputs.dem_path is not None else None,
                "paramWallAlpha": wall_absorption,
                "confReflOrder": 0,
                "confMaxSrcDist": 750,
                "confMaxReflDist": 50,
            },
        )
        _run_wps_script(
            runner_path,
            working_directory,
            DEFAULT_DB_NAME,
            _script_path("Acoustic_Tools", "Create_Isosurface.groovy"),
            {
                "resultTable": "RECEIVERS_LEVEL",
                "isoClass": ISO_CLASSES,
                "resultTableField": "LAEQ",
            },
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
    dem_geojson = CityPyo().get_dem_for_user(cityPyo_user, required=False)
    noise_result_geojson = _run_nm5_pipeline(
        calculation_settings,
        buildings_geojson,
        roads_geojson,
        dem_geojson=dem_geojson,
    )
    noise_result_geojson = clip_gdf_to_project_area(noise_result_geojson, cityPyo_user)

    if calculation_settings.result_format == "png":
        return convert_result_to_png(noise_result_geojson, calculation_settings.png_style or "raw")

    return noise_result_geojson
