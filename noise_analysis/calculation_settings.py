import os
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

from noise_analysis.palette import normalize_png_style


VALID_RESULT_FORMATS = ("geojson", "png")
VALID_NOISE_ENGINES = ("legacy", "nm5", "nm5_full", "auto")


def _ensure_mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError("%s must be an object" % field_name)
    return value


def _require(mapping: Mapping[str, Any], field_name: str) -> Any:
    if field_name not in mapping:
        raise KeyError(field_name)
    return mapping[field_name]


def _coerce_float(value: Any, field_name: str) -> float:
    if isinstance(value, bool):
        raise ValueError("%s must be a number" % field_name)

    try:
        return float(value)
    except (TypeError, ValueError):
        raise ValueError("%s must be a number" % field_name)


def _coerce_optional_float(value: Any, field_name: str) -> Optional[float]:
    if value in (None, ""):
        return None
    return _coerce_float(value, field_name)


def _coerce_optional_int(value: Any, field_name: str) -> Optional[int]:
    if value in (None, ""):
        return None
    coerced_value = _coerce_float(value, field_name)
    return int(coerced_value)


def _coerce_optional_bool(value: Any, field_name: str) -> Optional[bool]:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)

    normalized_value = str(value).strip().lower()
    if normalized_value in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized_value in {"0", "false", "no", "n", "off"}:
        return False
    raise ValueError("%s must be a boolean" % field_name)


def _coerce_optional_string(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None
    return str(value)


def _normalize_choice(value: Any, field_name: str, valid_values) -> str:
    normalized_value = str(value).lower()
    if normalized_value not in valid_values:
        raise ValueError(
            "Unsupported %s value: %s. Expected one of %s"
            % (field_name, value, ", ".join(valid_values))
        )
    return normalized_value


@dataclass(frozen=True)
class TrafficSettings:
    max_speed: float
    traffic_quota: float

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "TrafficSettings":
        payload = _ensure_mapping(payload, "traffic_settings")

        max_speed = _coerce_float(_require(payload, "max_speed"), "max_speed")
        if max_speed < 0:
            raise ValueError("max_speed must be non-negative")

        traffic_quota = _coerce_float(_require(payload, "traffic_quota"), "traffic_quota")
        if traffic_quota < 0:
            raise ValueError("traffic_quota must be non-negative")

        return cls(max_speed=max_speed, traffic_quota=traffic_quota)

    def to_dict(self) -> Mapping[str, Any]:
        return {
            "max_speed": self.max_speed,
            "traffic_quota": self.traffic_quota,
        }


@dataclass(frozen=True)
class AcousticSettings:
    wall_absorption: Optional[float] = None

    @classmethod
    def from_mapping(cls, payload: Optional[Mapping[str, Any]]) -> "AcousticSettings":
        payload = _ensure_mapping(payload or {}, "calculation_settings")
        wall_absorption = _coerce_optional_float(payload.get("wall_absorption"), "wall_absorption")
        if wall_absorption is not None and not 0 <= wall_absorption <= 1:
            raise ValueError("wall_absorption must be between 0 and 1")
        return cls(wall_absorption=wall_absorption)

    def resolved_wall_absorption(self, default: float) -> float:
        if self.wall_absorption is None:
            return default
        return self.wall_absorption

    def to_dict(self) -> Mapping[str, Any]:
        return {
            "wall_absorption": self.wall_absorption,
        }


@dataclass(frozen=True)
class Nm5Settings:
    receiver_height: Optional[float] = None
    max_cell_dist: Optional[float] = None
    road_width: Optional[float] = None
    building_buffer: Optional[float] = None
    max_area: Optional[float] = None
    skip_cell_no_sources_minimal_distance: Optional[float] = None
    fence_negative_buffer: Optional[float] = None
    iso_surface_in_buildings: Optional[bool] = None
    export_triangles_geometries: Optional[bool] = None
    reflection_order: Optional[int] = None
    max_source_distance: Optional[float] = None
    max_reflection_distance: Optional[float] = None
    thread_number: Optional[int] = None
    diff_vertical: Optional[bool] = None
    diff_horizontal: Optional[bool] = None
    export_source_id: Optional[bool] = None
    humidity: Optional[float] = None
    temperature: Optional[float] = None
    favourable_occurrences: Optional[str] = None
    rays_name: Optional[str] = None
    max_error: Optional[float] = None
    iso_classes: Optional[str] = None
    result_table_field: Optional[str] = None

    @classmethod
    def from_mapping(cls, payload: Optional[Mapping[str, Any]]) -> "Nm5Settings":
        payload = _ensure_mapping(payload or {}, "nm5_settings")

        settings = cls(
            receiver_height=_coerce_optional_float(payload.get("receiver_height"), "receiver_height"),
            max_cell_dist=_coerce_optional_float(payload.get("max_cell_dist"), "max_cell_dist"),
            road_width=_coerce_optional_float(payload.get("road_width"), "road_width"),
            building_buffer=_coerce_optional_float(payload.get("building_buffer"), "building_buffer"),
            max_area=_coerce_optional_float(payload.get("max_area"), "max_area"),
            skip_cell_no_sources_minimal_distance=_coerce_optional_float(
                payload.get("skip_cell_no_sources_minimal_distance"),
                "skip_cell_no_sources_minimal_distance",
            ),
            fence_negative_buffer=_coerce_optional_float(
                payload.get("fence_negative_buffer"),
                "fence_negative_buffer",
            ),
            iso_surface_in_buildings=_coerce_optional_bool(
                payload.get("iso_surface_in_buildings"),
                "iso_surface_in_buildings",
            ),
            export_triangles_geometries=_coerce_optional_bool(
                payload.get("export_triangles_geometries"),
                "export_triangles_geometries",
            ),
            reflection_order=_coerce_optional_int(payload.get("reflection_order"), "reflection_order"),
            max_source_distance=_coerce_optional_float(
                payload.get("max_source_distance"),
                "max_source_distance",
            ),
            max_reflection_distance=_coerce_optional_float(
                payload.get("max_reflection_distance"),
                "max_reflection_distance",
            ),
            thread_number=_coerce_optional_int(payload.get("thread_number"), "thread_number"),
            diff_vertical=_coerce_optional_bool(payload.get("diff_vertical"), "diff_vertical"),
            diff_horizontal=_coerce_optional_bool(payload.get("diff_horizontal"), "diff_horizontal"),
            export_source_id=_coerce_optional_bool(payload.get("export_source_id"), "export_source_id"),
            humidity=_coerce_optional_float(payload.get("humidity"), "humidity"),
            temperature=_coerce_optional_float(payload.get("temperature"), "temperature"),
            favourable_occurrences=_coerce_optional_string(payload.get("favourable_occurrences")),
            rays_name=_coerce_optional_string(payload.get("rays_name")),
            max_error=_coerce_optional_float(payload.get("max_error"), "max_error"),
            iso_classes=_coerce_optional_string(payload.get("iso_classes")),
            result_table_field=_coerce_optional_string(payload.get("result_table_field")),
        )

        if settings.reflection_order is not None and settings.reflection_order < 0:
            raise ValueError("reflection_order must be non-negative")
        if settings.thread_number is not None and settings.thread_number < 0:
            raise ValueError("thread_number must be non-negative")
        if settings.humidity is not None and not 0 <= settings.humidity <= 100:
            raise ValueError("humidity must be between 0 and 100")
        if settings.max_error is not None and settings.max_error < 0:
            raise ValueError("max_error must be non-negative")

        return settings

    def to_dict(self) -> Mapping[str, Any]:
        return {
            key: value
            for key, value in {
                "receiver_height": self.receiver_height,
                "max_cell_dist": self.max_cell_dist,
                "road_width": self.road_width,
                "building_buffer": self.building_buffer,
                "max_area": self.max_area,
                "skip_cell_no_sources_minimal_distance": self.skip_cell_no_sources_minimal_distance,
                "fence_negative_buffer": self.fence_negative_buffer,
                "iso_surface_in_buildings": self.iso_surface_in_buildings,
                "export_triangles_geometries": self.export_triangles_geometries,
                "reflection_order": self.reflection_order,
                "max_source_distance": self.max_source_distance,
                "max_reflection_distance": self.max_reflection_distance,
                "thread_number": self.thread_number,
                "diff_vertical": self.diff_vertical,
                "diff_horizontal": self.diff_horizontal,
                "export_source_id": self.export_source_id,
                "humidity": self.humidity,
                "temperature": self.temperature,
                "favourable_occurrences": self.favourable_occurrences,
                "rays_name": self.rays_name,
                "max_error": self.max_error,
                "iso_classes": self.iso_classes,
                "result_table_field": self.result_table_field,
            }.items()
            if value is not None
        }


@dataclass(frozen=True)
class CalculationSettings:
    traffic_settings: TrafficSettings
    calculation_settings: AcousticSettings
    result_format: str
    noise_engine: str
    png_style: Optional[str] = None
    nm5_settings: Nm5Settings = field(default_factory=Nm5Settings)

    @classmethod
    def from_mapping(
        cls,
        payload: Any,
        default_noise_engine: Optional[str] = None,
    ) -> "CalculationSettings":
        if isinstance(payload, cls):
            return payload

        payload = _ensure_mapping(payload, "scenario")
        if "traffic_settings" in payload:
            traffic_settings = TrafficSettings.from_mapping(payload["traffic_settings"])
            acoustic_settings = AcousticSettings.from_mapping(payload.get("calculation_settings"))
        else:
            traffic_settings = TrafficSettings.from_mapping(payload)
            acoustic_settings = AcousticSettings.from_mapping(payload)

        result_format = _normalize_choice(
            _require(payload, "result_format"),
            "result_format",
            VALID_RESULT_FORMATS,
        )
        noise_engine = _normalize_choice(
            payload.get("noise_engine", default_noise_engine or "legacy"),
            "noise_engine",
            VALID_NOISE_ENGINES,
        )

        png_style = None
        if result_format == "png":
            png_style = normalize_png_style(payload.get("png_style", os.getenv("NOISE_PNG_STYLE", "raw")))

        return cls(
            traffic_settings=traffic_settings,
            calculation_settings=acoustic_settings,
            result_format=result_format,
            noise_engine=noise_engine,
            png_style=png_style,
            nm5_settings=Nm5Settings.from_mapping(payload.get("nm5_settings")),
        )

    def to_dict(self) -> Mapping[str, Any]:
        payload = {
            "traffic_settings": dict(self.traffic_settings.to_dict()),
            "calculation_settings": dict(self.calculation_settings.to_dict()),
            "result_format": self.result_format,
            "noise_engine": self.noise_engine,
        }

        if self.png_style is not None:
            payload["png_style"] = self.png_style

        nm5_settings = self.nm5_settings.to_dict()
        if nm5_settings:
            payload["nm5_settings"] = dict(nm5_settings)

        return payload
