"""Convert between the user's temperature unit and Celsius storage.

Absolute temperatures use the normal conversion. Deltas (dew margin,
hysteresis) must not — 5°F as an absolute temperature is -15°C.
"""

from __future__ import annotations

from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.util.unit_conversion import TemperatureConverter

from .const import DEFAULTS_F, DELTA_KEYS, FORM_RANGES_F


def user_temperature_unit(hass: HomeAssistant) -> str:
    return hass.config.units.temperature_unit


def _is_fahrenheit(unit: str) -> bool:
    return unit == UnitOfTemperature.FAHRENHEIT


def f_to_c(value_f: float) -> float:
    return (value_f - 32.0) * 5.0 / 9.0


def c_to_f(value_c: float) -> float:
    return value_c * 9.0 / 5.0 + 32.0


def delta_f_to_c(value_f: float) -> float:
    return value_f * 5.0 / 9.0


def delta_c_to_f(value_c: float) -> float:
    return value_c * 9.0 / 5.0


def state_to_celsius(value: float, unit: str | None, fallback_unit: str) -> float:
    """Convert a sensor reading to Celsius."""

    source = unit or fallback_unit
    if source == UnitOfTemperature.CELSIUS:
        return value
    return TemperatureConverter.convert(value, source, UnitOfTemperature.CELSIUS)


def default_options_c() -> dict[str, float]:
    """Default dew thresholds in Celsius degrees."""

    stored: dict[str, float] = {}
    for key, value_f in DEFAULTS_F.items():
        if key in DELTA_KEYS:
            stored[key] = round(delta_f_to_c(value_f), 4)
        else:
            stored[key] = round(f_to_c(value_f), 4)
    return stored


def to_display(key: str, stored_c: float, unit: str) -> float:
    if not _is_fahrenheit(unit):
        return round(stored_c, 1)
    if key in DELTA_KEYS:
        return round(delta_c_to_f(stored_c), 1)
    return round(c_to_f(stored_c), 1)


def from_display(key: str, value: float, unit: str) -> float:
    if not _is_fahrenheit(unit):
        return round(float(value), 4)
    if key in DELTA_KEYS:
        return round(delta_f_to_c(value), 4)
    return round(f_to_c(value), 4)


def form_range(key: str, unit: str) -> tuple[float, float, float]:
    minimum_f, maximum_f, step_f = FORM_RANGES_F[key]
    if not _is_fahrenheit(unit):
        scale = 5.0 / 9.0
        step = 0.5 if step_f >= 1 else 0.1
        return (
            round(minimum_f * scale, 1) if key in DELTA_KEYS else round(f_to_c(minimum_f), 1),
            round(maximum_f * scale, 1) if key in DELTA_KEYS else round(f_to_c(maximum_f), 1),
            step,
        )
    return minimum_f, maximum_f, step_f
