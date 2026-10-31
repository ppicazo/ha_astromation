"""Astrophotography mode switch."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN
from .coordinator import AstromationCoordinator
from .entity import AstromationEntity

_ASTRO_MODE = SwitchEntityDescription(
    key="astro_mode",
    translation_key="astro_mode",
    icon="mdi:telescope",
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: AstromationCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([AstromationModeSwitch(coordinator)])


class AstromationModeSwitch(AstromationEntity, SwitchEntity, RestoreEntity):
    """Manual Astrophotography Mode. Later this can follow ASIAir capture."""

    entity_description = _ASTRO_MODE
    _attr_assumed_state = False

    def __init__(self, coordinator: AstromationCoordinator) -> None:
        super().__init__(coordinator, "astro_mode")
        self._attr_is_on = False

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None:
            self._attr_is_on = last.state == "on"
            self.coordinator.mode_on = self._attr_is_on
        self.coordinator.control_ready = True
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self, **kwargs: object) -> None:
        self._attr_is_on = True
        self.coordinator.set_mode(True)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: object) -> None:
        self._attr_is_on = False
        self.coordinator.set_mode(False)
        self.async_write_ha_state()
