"""Evaluate dew risk and enforce lights / actuators during astro mode."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

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
    DEFAULT_STALE_MINUTES,
    DOMAIN,
    EVENT_ASTROMATION,
)
from .decision import (
    ControlSettings,
    Decision,
    Risk,
    Snapshot,
    decide,
    held_sample,
)
from .units import default_options_c, state_to_celsius

_LOGGER = logging.getLogger(__name__)


class Reading:
    """An averaged value and the sensors that produced it."""

    def __init__(self, value: float | None, sources: list[str]) -> None:
        self.value = value
        self.sources = sources


class AstromationData:
    """Latest evaluation."""

    def __init__(
        self,
        outdoor_temp: Reading,
        outdoor_humidity: Reading,
        decision: Decision,
        mode_on: bool,
    ) -> None:
        self.outdoor_temp = outdoor_temp
        self.outdoor_humidity = outdoor_humidity
        self.decision = decision
        self.mode_on = mode_on


class AstromationCoordinator(DataUpdateCoordinator[AstromationData]):
    """Average outdoor sensors, decide dew risk, and command lights."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=60),
        )
        self.entry = entry
        self.mode_on = False
        # Light / actuator commands wait until the mode switch restores.
        self.control_ready = False
        self._previous_unsafe: bool | None = None
        self._held_samples: dict[str, tuple[float, datetime]] = {}
        self._saved_lights: dict[str, dict[str, Any]] = {}
        self._light_task: asyncio.Task[None] | None = None
        self._actuator_task: asyncio.Task[None] | None = None
        self._pending_actuator: str | None = None
        self.light_error: str | None = None
        self.actuator_error: str | None = None
        self._was_mode_on: bool | None = None

    async def _async_update_data(self) -> AstromationData:
        try:
            return self._evaluate()
        except Exception as err:
            _LOGGER.exception("Astromation could not evaluate dew risk")
            return AstromationData(
                outdoor_temp=Reading(None, []),
                outdoor_humidity=Reading(None, []),
                decision=Decision(
                    risk=Risk.UNKNOWN,
                    unsafe=None,
                    dew_point_c=None,
                    dew_margin_c=None,
                    reason=f"Evaluation failed: {err}",
                    became_unsafe=False,
                    became_safe=False,
                ),
                mode_on=self.mode_on,
            )

    def _evaluate(self) -> AstromationData:
        options = self.entry.options
        defaults = default_options_c()
        stale = timedelta(
            minutes=int(options.get(CONF_STALE_MINUTES, DEFAULT_STALE_MINUTES))
        )
        outdoor_temp = self._average_temperature(
            self._entity_list(options, CONF_OUTDOOR_TEMP_SENSORS), stale
        )
        outdoor_humidity = self._average_humidity(
            self._entity_list(options, CONF_OUTDOOR_HUMIDITY_SENSORS), stale
        )
        settings = ControlSettings(
            dew_margin_c=float(options.get(CONF_DEW_MARGIN, defaults[CONF_DEW_MARGIN])),
            hysteresis_c=float(options.get(CONF_HYSTERESIS, defaults[CONF_HYSTERESIS])),
        )
        decision = decide(
            Snapshot(
                outdoor_c=outdoor_temp.value,
                outdoor_rh=outdoor_humidity.value,
                previous_unsafe=self._previous_unsafe,
                mode_on=self.mode_on,
            ),
            settings,
        )
        if decision.unsafe is not None:
            self._previous_unsafe = decision.unsafe

        data = AstromationData(
            outdoor_temp=outdoor_temp,
            outdoor_humidity=outdoor_humidity,
            decision=decision,
            mode_on=self.mode_on,
        )

        if self.control_ready:
            self._schedule_lights()
            if decision.became_unsafe:
                self._emit("became_unsafe", decision)
                self._schedule_actuators("unsafe")
            elif decision.became_safe:
                self._emit("became_safe", decision)
                self._schedule_actuators("safe")
            self._track_mode_edge(decision)

        return data

    def _track_mode_edge(self, decision: Decision) -> None:
        if self._was_mode_on is None:
            self._was_mode_on = self.mode_on
            return
        if self.mode_on and not self._was_mode_on:
            self._emit("astro_mode_on", decision)
            # Session started while already in dew risk — notify and arm heaters.
            if decision.unsafe is True:
                self._emit("became_unsafe", decision)
                self._schedule_actuators("unsafe")
        elif not self.mode_on and self._was_mode_on:
            self._emit("astro_mode_off", decision)
            # Leaving a session restores lights and turns off heaters we armed.
            self._schedule_actuators("mode_off")
        self._was_mode_on = self.mode_on

    def _emit(self, event_type: str, decision: Decision) -> None:
        device = dr.async_get(self.hass).async_get_device(
            identifiers={(DOMAIN, self.entry.entry_id)}
        )
        self.hass.bus.async_fire(
            EVENT_ASTROMATION,
            {
                "type": event_type,
                "entry_id": self.entry.entry_id,
                "device_id": device.id if device else None,
                "risk": decision.risk.value,
                "reason": decision.reason,
                "dew_point_c": decision.dew_point_c,
                "dew_margin_c": decision.dew_margin_c,
            },
        )

    @callback
    def _handle_state_change(self, _event: Event) -> None:
        self.hass.async_create_task(self.async_request_refresh())

    def set_mode(self, mode_on: bool) -> None:
        self.mode_on = mode_on
        self.hass.async_create_task(self.async_request_refresh())

    def listened_entities(self) -> list[str]:
        options = self.entry.options
        entities: list[str] = []
        for key in (
            CONF_OUTDOOR_TEMP_SENSORS,
            CONF_OUTDOOR_HUMIDITY_SENSORS,
            CONF_BLOCKED_LIGHTS,
            CONF_DIMMED_LIGHTS,
            CONF_TURN_ON_UNSAFE,
            CONF_TURN_OFF_UNSAFE,
            CONF_TURN_ON_SAFE,
            CONF_TURN_OFF_SAFE,
        ):
            entities.extend(self._entity_list(options, key))
        return entities

    def listen(self) -> None:
        watched = self.listened_entities()
        if not watched:
            return
        self.entry.async_on_unload(
            async_track_state_change_event(
                self.hass, watched, self._handle_state_change
            )
        )

    def _schedule_lights(self) -> None:
        if self._light_task is not None and not self._light_task.done():
            return
        self._light_task = self.hass.async_create_task(self._async_safe_lights())

    async def _async_safe_lights(self) -> None:
        self.light_error = None
        try:
            if self.mode_on:
                await self._async_enforce_lights()
            else:
                await self._async_restore_lights()
        except Exception as err:
            _LOGGER.exception("Astromation could not enforce lights")
            self.light_error = str(err)
        if self.data is not None:
            self.async_set_updated_data(self.data)

    async def _async_enforce_lights(self) -> None:
        options = self.entry.options
        max_pct = int(options.get(CONF_MAX_BRIGHTNESS, DEFAULT_MAX_BRIGHTNESS))
        max_brightness = max(1, min(255, round(max_pct * 255 / 100)))

        for entity_id in self._entity_list(options, CONF_BLOCKED_LIGHTS):
            state = self.hass.states.get(entity_id)
            if state is None or state.state in {STATE_UNAVAILABLE, STATE_UNKNOWN}:
                continue
            if state.state == STATE_OFF:
                continue
            self._remember_light(entity_id, state)
            _LOGGER.info("Astromation blocked %s", entity_id)
            await self.hass.services.async_call(
                "light",
                "turn_off",
                {"entity_id": entity_id},
                blocking=True,
            )

        for entity_id in self._entity_list(options, CONF_DIMMED_LIGHTS):
            state = self.hass.states.get(entity_id)
            if state is None or state.state in {STATE_UNAVAILABLE, STATE_UNKNOWN}:
                continue
            if state.state != STATE_ON:
                continue
            brightness = state.attributes.get("brightness")
            if brightness is None:
                continue
            try:
                brightness_i = int(brightness)
            except (TypeError, ValueError):
                continue
            if brightness_i <= max_brightness:
                continue
            self._remember_light(entity_id, state)
            _LOGGER.info(
                "Astromation capped %s at %s%% brightness", entity_id, max_pct
            )
            await self.hass.services.async_call(
                "light",
                "turn_on",
                {"entity_id": entity_id, "brightness_pct": max_pct},
                blocking=True,
            )

    def _remember_light(self, entity_id: str, state: Any) -> None:
        if entity_id in self._saved_lights:
            return
        saved: dict[str, Any] = {"state": state.state}
        for key in ("brightness", "color_temp", "hs_color", "rgb_color", "xy_color"):
            if key in state.attributes and state.attributes[key] is not None:
                saved[key] = state.attributes[key]
        self._saved_lights[entity_id] = saved

    async def _async_restore_lights(self) -> None:
        pending = dict(self._saved_lights)
        self._saved_lights.clear()
        for entity_id, saved in pending.items():
            if saved.get("state") == STATE_OFF:
                await self.hass.services.async_call(
                    "light",
                    "turn_off",
                    {"entity_id": entity_id},
                    blocking=True,
                )
                continue
            data: dict[str, Any] = {"entity_id": entity_id}
            if "brightness" in saved:
                data["brightness"] = saved["brightness"]
            if "color_temp" in saved:
                data["color_temp"] = saved["color_temp"]
            elif "hs_color" in saved:
                data["hs_color"] = saved["hs_color"]
            elif "rgb_color" in saved:
                data["rgb_color"] = saved["rgb_color"]
            elif "xy_color" in saved:
                data["xy_color"] = saved["xy_color"]
            _LOGGER.info("Astromation restored %s", entity_id)
            await self.hass.services.async_call(
                "light",
                "turn_on",
                data,
                blocking=True,
            )

    def _schedule_actuators(self, phase: str) -> None:
        self._pending_actuator = phase
        if self._actuator_task is not None and not self._actuator_task.done():
            return
        self._actuator_task = self.hass.async_create_task(self._async_safe_actuators())

    async def _async_safe_actuators(self) -> None:
        while True:
            phase = self._pending_actuator
            self._pending_actuator = None
            self.actuator_error = None
            try:
                await self._async_run_actuators(phase or "noop")
            except Exception as err:
                _LOGGER.exception("Astromation could not run actuators")
                self.actuator_error = str(err)
            if self._pending_actuator is None:
                break
        if self.data is not None:
            self.async_set_updated_data(self.data)

    async def _async_run_actuators(self, phase: str) -> None:
        options = self.entry.options
        if phase == "unsafe":
            await self._call_switches(self._entity_list(options, CONF_TURN_ON_UNSAFE), "turn_on")
            await self._call_switches(self._entity_list(options, CONF_TURN_OFF_UNSAFE), "turn_off")
        elif phase == "safe":
            await self._call_switches(self._entity_list(options, CONF_TURN_ON_SAFE), "turn_on")
            await self._call_switches(self._entity_list(options, CONF_TURN_OFF_SAFE), "turn_off")
        elif phase == "mode_off":
            # Stop heaters we would have turned on for dew risk.
            await self._call_switches(
                self._entity_list(options, CONF_TURN_ON_UNSAFE), "turn_off"
            )

    async def _call_switches(self, entity_ids: list[str], service: str) -> None:
        for entity_id in entity_ids:
            state = self.hass.states.get(entity_id)
            if state is None or state.state in {STATE_UNAVAILABLE, STATE_UNKNOWN}:
                continue
            want_on = service == "turn_on"
            if want_on and state.state == STATE_ON:
                continue
            if not want_on and state.state == STATE_OFF:
                continue
            domain = entity_id.split(".", 1)[0]
            if domain not in {"switch", "input_boolean", "light", "fan"}:
                domain = "homeassistant"
            _LOGGER.info("Astromation %s %s", service, entity_id)
            await self.hass.services.async_call(
                domain,
                service,
                {"entity_id": entity_id},
                blocking=True,
            )

    def _average_temperature(
        self, entity_ids: list[str], stale_after: timedelta
    ) -> Reading:
        values: list[float] = []
        sources: list[str] = []
        now = dt_util.utcnow()
        for entity_id in entity_ids:
            sample = self._sample_temperature(entity_id, now, stale_after)
            if sample is None:
                continue
            values.append(sample)
            sources.append(entity_id)
        if not values:
            return Reading(None, [])
        return Reading(sum(values) / len(values), sources)

    def _average_humidity(
        self, entity_ids: list[str], stale_after: timedelta
    ) -> Reading:
        values: list[float] = []
        sources: list[str] = []
        now = dt_util.utcnow()
        for entity_id in entity_ids:
            sample = self._sample_humidity(entity_id, now, stale_after)
            if sample is None:
                continue
            values.append(sample)
            sources.append(entity_id)
        if not values:
            return Reading(None, [])
        return Reading(sum(values) / len(values), sources)

    def _sample_temperature(
        self, entity_id: str, now: datetime, stale_after: timedelta
    ) -> float | None:
        fresh: float | None = None
        fresh_at: datetime | None = None
        state = self.hass.states.get(entity_id)
        if state is not None and state.state not in {STATE_UNAVAILABLE, STATE_UNKNOWN}:
            try:
                raw = float(state.state)
            except (TypeError, ValueError):
                raw = None
            if raw is not None:
                unit = state.attributes.get("unit_of_measurement")
                try:
                    fresh = state_to_celsius(
                        raw, unit, self.hass.config.units.temperature_unit
                    )
                except ValueError:
                    _LOGGER.debug("Skipping %s with unsupported unit %s", entity_id, unit)
                else:
                    fresh_at = state.last_updated
                    try:
                        now - fresh_at
                    except TypeError:
                        fresh_at = now
        value, held = held_sample(
            fresh, fresh_at, self._held_samples.get(entity_id), now, stale_after
        )
        if held is None:
            self._held_samples.pop(entity_id, None)
        else:
            self._held_samples[entity_id] = held
        return value

    def _sample_humidity(
        self, entity_id: str, now: datetime, stale_after: timedelta
    ) -> float | None:
        fresh: float | None = None
        fresh_at: datetime | None = None
        state = self.hass.states.get(entity_id)
        if state is not None and state.state not in {STATE_UNAVAILABLE, STATE_UNKNOWN}:
            try:
                raw = float(state.state)
            except (TypeError, ValueError):
                raw = None
            if raw is not None and 0 < raw <= 100:
                fresh = raw
                fresh_at = state.last_updated
                try:
                    now - fresh_at
                except TypeError:
                    fresh_at = now
        value, held = held_sample(
            fresh, fresh_at, self._held_samples.get(entity_id), now, stale_after
        )
        if held is None:
            self._held_samples.pop(entity_id, None)
        else:
            self._held_samples[entity_id] = held
        return value

    @staticmethod
    def _entity_list(options: dict[str, Any], key: str) -> list[str]:
        value = options.get(key) or []
        if isinstance(value, str):
            return [value] if value else []
        return list(value)
