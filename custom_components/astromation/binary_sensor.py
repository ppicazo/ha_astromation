"""Dew-risk binary sensor."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import AstromationCoordinator
from .entity import AstromationEntity

_DEW_UNSAFE = BinarySensorEntityDescription(
    key="dew_unsafe",
    translation_key="dew_unsafe",
    icon="mdi:water-alert",
)

_SESSION_ACTIVE = BinarySensorEntityDescription(
    key="session_active",
    translation_key="session_active",
    icon="mdi:telescope",
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: AstromationCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            AstromationDewUnsafeSensor(coordinator),
            AstromationSessionSensor(coordinator),
        ]
    )


class AstromationDewUnsafeSensor(AstromationEntity, BinarySensorEntity):
    """On when outdoor dew margin is at or below the threshold."""

    entity_description = _DEW_UNSAFE

    def __init__(self, coordinator: AstromationCoordinator) -> None:
        super().__init__(coordinator, "dew_unsafe")

    @property
    def is_on(self) -> bool | None:
        data = self.coordinator.data
        if data is None or data.decision.unsafe is None:
            return None
        return data.decision.unsafe


class AstromationSessionSensor(AstromationEntity, BinarySensorEntity):
    """On when Astrophotography Mode is enforcing lights and actuators."""

    entity_description = _SESSION_ACTIVE

    def __init__(self, coordinator: AstromationCoordinator) -> None:
        super().__init__(coordinator, "session_active")

    @property
    def is_on(self) -> bool | None:
        data = self.coordinator.data
        if data is None:
            return None
        return data.mode_on
