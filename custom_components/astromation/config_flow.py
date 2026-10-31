"""Config and options flow for Astromation."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.const import UnitOfTemperature
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_BLOCKED_LIGHTS,
    CONF_DEW_MARGIN,
    CONF_DIMMED_LIGHTS,
    CONF_HYSTERESIS,
    CONF_MAX_BRIGHTNESS,
    CONF_OUTDOOR_HUMIDITY_SENSORS,
    CONF_OUTDOOR_TEMP_SENSORS,
    CONF_STALE_MINUTES,
    CONF_TURN_OFF_SAFE,
    CONF_TURN_OFF_UNSAFE,
    CONF_TURN_ON_SAFE,
    CONF_TURN_ON_UNSAFE,
    DEFAULT_MAX_BRIGHTNESS,
    DEFAULT_NAME,
    DEFAULT_STALE_MINUTES,
    DOMAIN,
)
from .units import (
    default_options_c,
    form_range,
    from_display,
    to_display,
    user_temperature_unit,
)

TEMP_SENSOR = selector.EntitySelector(
    selector.EntitySelectorConfig(
        domain="sensor",
        device_class="temperature",
        multiple=True,
    )
)
HUMIDITY_SENSOR = selector.EntitySelector(
    selector.EntitySelectorConfig(
        domain="sensor",
        device_class="humidity",
        multiple=True,
    )
)
LIGHT_SELECTOR = selector.EntitySelector(
    selector.EntitySelectorConfig(domain="light", multiple=True)
)
SWITCH_SELECTOR = selector.EntitySelector(
    selector.EntitySelectorConfig(
        domain=["switch", "input_boolean", "light"],
        multiple=True,
    )
)

_BEHAVIOR_KEYS = (CONF_DEW_MARGIN, CONF_HYSTERESIS)

_ENTITY_KEYS = (
    CONF_OUTDOOR_TEMP_SENSORS,
    CONF_OUTDOOR_HUMIDITY_SENSORS,
    CONF_BLOCKED_LIGHTS,
    CONF_DIMMED_LIGHTS,
    CONF_TURN_ON_UNSAFE,
    CONF_TURN_OFF_UNSAFE,
    CONF_TURN_ON_SAFE,
    CONF_TURN_OFF_SAFE,
)


def _entities_schema(suggested: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(
                CONF_OUTDOOR_TEMP_SENSORS,
                description={
                    "suggested_value": suggested.get(CONF_OUTDOOR_TEMP_SENSORS, [])
                },
            ): TEMP_SENSOR,
            vol.Required(
                CONF_OUTDOOR_HUMIDITY_SENSORS,
                description={
                    "suggested_value": suggested.get(CONF_OUTDOOR_HUMIDITY_SENSORS, [])
                },
            ): HUMIDITY_SENSOR,
            vol.Optional(
                CONF_BLOCKED_LIGHTS,
                description={"suggested_value": suggested.get(CONF_BLOCKED_LIGHTS, [])},
            ): LIGHT_SELECTOR,
            vol.Optional(
                CONF_DIMMED_LIGHTS,
                description={"suggested_value": suggested.get(CONF_DIMMED_LIGHTS, [])},
            ): LIGHT_SELECTOR,
            vol.Optional(
                CONF_TURN_ON_UNSAFE,
                description={"suggested_value": suggested.get(CONF_TURN_ON_UNSAFE, [])},
            ): SWITCH_SELECTOR,
            vol.Optional(
                CONF_TURN_OFF_UNSAFE,
                description={"suggested_value": suggested.get(CONF_TURN_OFF_UNSAFE, [])},
            ): SWITCH_SELECTOR,
            vol.Optional(
                CONF_TURN_ON_SAFE,
                description={"suggested_value": suggested.get(CONF_TURN_ON_SAFE, [])},
            ): SWITCH_SELECTOR,
            vol.Optional(
                CONF_TURN_OFF_SAFE,
                description={"suggested_value": suggested.get(CONF_TURN_OFF_SAFE, [])},
            ): SWITCH_SELECTOR,
        }
    )


def _behavior_schema(suggested: dict[str, Any], unit: str) -> vol.Schema:
    fields: dict[Any, Any] = {}
    for key in _BEHAVIOR_KEYS:
        minimum, maximum, step = form_range(key, unit)
        fields[
            vol.Required(key, description={"suggested_value": suggested[key]})
        ] = selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=minimum,
                max=maximum,
                step=step,
                mode=selector.NumberSelectorMode.BOX,
                unit_of_measurement=unit,
            )
        )
    fields[
        vol.Required(
            CONF_MAX_BRIGHTNESS,
            description={
                "suggested_value": suggested.get(
                    CONF_MAX_BRIGHTNESS, DEFAULT_MAX_BRIGHTNESS
                )
            },
        )
    ] = selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=1,
            max=100,
            step=1,
            unit_of_measurement="%",
        )
    )
    fields[
        vol.Required(
            CONF_STALE_MINUTES,
            description={
                "suggested_value": suggested.get(
                    CONF_STALE_MINUTES, DEFAULT_STALE_MINUTES
                )
            },
        )
    ] = selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=5, max=180, step=1, unit_of_measurement="min"
        )
    )
    return vol.Schema(fields)


def _clean_entities(user_input: dict[str, Any]) -> dict[str, Any]:
    cleaned = dict(user_input)
    for key in _ENTITY_KEYS:
        if key in (
            CONF_OUTDOOR_TEMP_SENSORS,
            CONF_OUTDOOR_HUMIDITY_SENSORS,
        ):
            continue
        if not cleaned.get(key):
            cleaned.pop(key, None)
    return cleaned


def _display_behavior(stored: dict[str, Any], unit: str) -> dict[str, Any]:
    defaults = default_options_c()
    shown: dict[str, Any] = {}
    for key in _BEHAVIOR_KEYS:
        shown[key] = to_display(key, float(stored.get(key, defaults[key])), unit)
    shown[CONF_MAX_BRIGHTNESS] = stored.get(
        CONF_MAX_BRIGHTNESS, DEFAULT_MAX_BRIGHTNESS
    )
    shown[CONF_STALE_MINUTES] = stored.get(CONF_STALE_MINUTES, DEFAULT_STALE_MINUTES)
    return shown


def _store_behavior(user_input: dict[str, Any], unit: str) -> dict[str, Any]:
    stored: dict[str, Any] = {}
    for key in _BEHAVIOR_KEYS:
        stored[key] = from_display(key, float(user_input[key]), unit)
    stored[CONF_MAX_BRIGHTNESS] = int(user_input[CONF_MAX_BRIGHTNESS])
    stored[CONF_STALE_MINUTES] = int(user_input[CONF_STALE_MINUTES])
    return stored


def _behavior_errors(stored: dict[str, Any]) -> dict[str, str]:
    errors: dict[str, str] = {}
    if stored[CONF_DEW_MARGIN] <= 0 or stored[CONF_HYSTERESIS] <= 0:
        errors["base"] = "threshold_positive"
    return errors


class AstromationConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up an Astromation controller."""

    VERSION = 1

    def __init__(self) -> None:
        self._entities: dict[str, Any] = {}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> AstromationOptionsFlow:
        return AstromationOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> Any:
        errors: dict[str, str] = {}
        if user_input is not None:
            self._entities = _clean_entities(user_input)
            return await self.async_step_behavior()

        return self.async_show_form(
            step_id="user",
            data_schema=_entities_schema({}),
            errors=errors,
        )

    async def async_step_behavior(
        self, user_input: dict[str, Any] | None = None
    ) -> Any:
        unit = user_temperature_unit(self.hass)
        errors: dict[str, str] = {}
        if user_input is not None:
            stored = _store_behavior(user_input, unit)
            errors = _behavior_errors(stored)
            if not errors:
                return self.async_create_entry(
                    title=DEFAULT_NAME,
                    data={"name": DEFAULT_NAME},
                    options={**self._entities, **stored},
                )

        suggested = _display_behavior(default_options_c(), unit)
        if user_input is not None:
            suggested.update(user_input)
        return self.async_show_form(
            step_id="behavior",
            data_schema=_behavior_schema(suggested, unit),
            errors=errors,
            description_placeholders={"unit": _unit_name(unit)},
        )


class AstromationOptionsFlow(OptionsFlow):
    """Edit sensors, lights, actuators, and thresholds."""

    def __init__(self) -> None:
        self._entities: dict[str, Any] = {}

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> Any:
        if user_input is not None:
            self._entities = _clean_entities(user_input)
            return await self.async_step_behavior()

        current = dict(self.config_entry.options)
        return self.async_show_form(
            step_id="init",
            data_schema=_entities_schema(current),
        )

    async def async_step_behavior(
        self, user_input: dict[str, Any] | None = None
    ) -> Any:
        unit = user_temperature_unit(self.hass)
        errors: dict[str, str] = {}
        if user_input is not None:
            stored = _store_behavior(user_input, unit)
            errors = _behavior_errors(stored)
            if not errors:
                return self.async_create_entry(
                    title="",
                    data={**self._entities, **stored},
                )

        suggested = _display_behavior(dict(self.config_entry.options), unit)
        if user_input is not None:
            suggested.update(user_input)
        return self.async_show_form(
            step_id="behavior",
            data_schema=_behavior_schema(suggested, unit),
            errors=errors,
            description_placeholders={"unit": _unit_name(unit)},
        )


def _unit_name(unit: str) -> str:
    if unit == UnitOfTemperature.FAHRENHEIT:
        return "°F"
    return "°C"
