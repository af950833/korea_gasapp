"""Binary sensors for Korea Gas App."""

from __future__ import annotations

import logging

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import KoreaGasAppConfigEntry
from .coordinator import KoreaGasAppDataUpdateCoordinator
from .entity_helper import build_device_info, get_account_id

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass,
    entry: KoreaGasAppConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Korea Gas App binary sensors.

    The self-input-available sensor is only created for accounts that have
    registered for the self-reading service.  If the account later signs up,
    the coordinator listener below adds the entity automatically.
    """
    coordinator = entry.runtime_data
    added: set[str] = set()

    def _add_if_needed() -> None:
        if coordinator.data is None:
            return
        if not coordinator.data.indication.self_reading_registered:
            return
        uid = f"self_input_available_{get_account_id(coordinator)}"
        if uid in added:
            return
        _LOGGER.debug("Adding self-input-available binary sensor for %s", uid)
        added.add(uid)
        async_add_entities([KoreaGasAppSelfInputAvailableBinarySensor(coordinator)])

    # Initial setup
    _add_if_needed()

    # Watch for the account signing up for self-reading later
    entry.async_on_unload(
        coordinator.async_add_listener(lambda: _add_if_needed())
    )


class KoreaGasAppSelfInputAvailableBinarySensor(
    CoordinatorEntity[KoreaGasAppDataUpdateCoordinator],
    BinarySensorEntity,
):
    """Binary sensor: whether self meter reading input window is currently open."""

    _attr_has_entity_name = False
    _attr_name = "Self meter reading available"

    def __init__(self, coordinator: KoreaGasAppDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        aid = get_account_id(coordinator)
        self._attr_unique_id = f"self_input_available_{aid}"
        self.entity_id = f"binary_sensor.self_meter_reading_available_{aid}"
        self._attr_device_info = build_device_info(aid)

    @property
    def is_on(self) -> bool | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.self_input_available
