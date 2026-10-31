"""Dew point, margin, and status sensors."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import AstromationCoordinator, Reading
from .decision import Risk
from .entity import AstromationEntity

_RISK = SensorEntityDescription(
    key="risk",
    translation_key="risk",
    device_class=SensorDeviceClass.ENUM,
    options=[Risk.SAFE.value, Risk.UNSAFE.value, Risk.UNKNOWN.value],
    icon="mdi:shield-half-full",
)
_STATUS = SensorEntityDescription(
    key="status",
    translation_key="status",
    icon="mdi:information-outline",
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: AstromationCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            AstromationOutdoorTempSensor(coordinator),
            AstromationOutdoorHumiditySensor(coordinator),
            AstromationDewPointSensor(coordinator),
            AstromationDewMarginSensor(coordinator),
            AstromationRiskSensor(coordinator),
            AstromationStatusSensor(coordinator),
        ]
    )


class AstromationOutdoorTempSensor(AstromationEntity, SensorEntity):
    """Averaged outdoor temperature."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_suggested_display_precision = 1
    _attr_translation_key = "outdoor_temperature"
    _attr_icon = "mdi:thermometer"

    def __init__(self, coordinator: AstromationCoordinator) -> None:
        super().__init__(coordinator, "outdoor_temperature")

    @property
    def native_value(self) -> float | None:
        reading = self._reading
        if reading is None or reading.value is None:
            return None
        return round(reading.value, 2)

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        reading = self._reading
        if reading is None:
            return {}
        return {"sources": reading.sources, "source_count": len(reading.sources)}

    @property
    def _reading(self) -> Reading | None:
        data = self.coordinator.data
        if data is None:
            return None
        return data.outdoor_temp


class AstromationOutdoorHumiditySensor(AstromationEntity, SensorEntity):
    """Averaged outdoor relative humidity."""

    _attr_device_class = SensorDeviceClass.HUMIDITY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_suggested_display_precision = 0
    _attr_translation_key = "outdoor_humidity"
    _attr_icon = "mdi:water-percent"

    def __init__(self, coordinator: AstromationCoordinator) -> None:
        super().__init__(coordinator, "outdoor_humidity")

    @property
    def native_value(self) -> float | None:
        reading = self._reading
        if reading is None or reading.value is None:
            return None
        return round(reading.value, 1)

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        reading = self._reading
        if reading is None:
            return {}
        return {"sources": reading.sources, "source_count": len(reading.sources)}

    @property
    def _reading(self) -> Reading | None:
        data = self.coordinator.data
        if data is None:
            return None
        return data.outdoor_humidity


class AstromationDewPointSensor(AstromationEntity, SensorEntity):
    """Calculated outdoor dew point."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_suggested_display_precision = 1
    _attr_translation_key = "dew_point"
    _attr_icon = "mdi:water-thermometer"

    def __init__(self, coordinator: AstromationCoordinator) -> None:
        super().__init__(coordinator, "dew_point")

    @property
    def native_value(self) -> float | None:
        data = self.coordinator.data
        if data is None or data.decision.dew_point_c is None:
            return None
        return round(data.decision.dew_point_c, 2)


class AstromationDewMarginSensor(AstromationEntity, SensorEntity):
    """Degrees between outdoor air and dew point (higher is safer)."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_suggested_display_precision = 1
    _attr_translation_key = "dew_margin"
    _attr_icon = "mdi:arrow-expand-vertical"

    def __init__(self, coordinator: AstromationCoordinator) -> None:
        super().__init__(coordinator, "dew_margin")

    @property
    def native_value(self) -> float | None:
        data = self.coordinator.data
        if data is None or data.decision.dew_margin_c is None:
            return None
        return round(data.decision.dew_margin_c, 2)


class AstromationRiskSensor(AstromationEntity, SensorEntity):
    """safe / unsafe / unknown from dew margin."""

    entity_description = _RISK

    def __init__(self, coordinator: AstromationCoordinator) -> None:
        super().__init__(coordinator, "risk")

    @property
    def native_value(self) -> str | None:
        data = self.coordinator.data
        if data is None:
            return None
        return data.decision.risk.value


class AstromationStatusSensor(AstromationEntity, SensorEntity):
    """Plain-language reason for the current decision."""

    entity_description = _STATUS

    def __init__(self, coordinator: AstromationCoordinator) -> None:
        super().__init__(coordinator, "status")

    @property
    def native_value(self) -> str | None:
        data = self.coordinator.data
        if data is None:
            return None
        reason = data.decision.reason
        if self.coordinator.light_error:
            return f"Light command failed: {self.coordinator.light_error} {reason}"
        if self.coordinator.actuator_error:
            return (
                f"Actuator command failed: {self.coordinator.actuator_error} {reason}"
            )
        return reason
