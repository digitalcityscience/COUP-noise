import os
from dataclasses import dataclass
from typing import Any, Mapping, Optional

from noise_analysis.palette import normalize_png_style


VALID_RESULT_FORMATS = ("geojson", "png")
VALID_NOISE_ENGINES = ("legacy", "nm5", "auto")


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
class CalculationSettings:
    traffic_settings: TrafficSettings
    calculation_settings: AcousticSettings
    result_format: str
    noise_engine: str
    png_style: Optional[str] = None

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

        return payload
