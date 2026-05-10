"""Binary sensors for Korea Gas App."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import KoreaGasAppConfigEntry
from .coordinator import KoreaGasAppDataUpdateCoordinator


async def async_setup_entry(
    hass,
    entry: KoreaGasAppConfigEntry,
    async_add_entities,
) -> None:
    """Set up Korea Gas App binary sensors."""
    async_add_entities([KoreaGasAppSelfInputAvailableBinarySensor(entry.runtime_data)])


class KoreaGasAppSelfInputAvailableBinarySensor(
    CoordinatorEntity[KoreaGasAppDataUpdateCoordinator],
    BinarySensorEntity,
):
    """Representation of the self meter reading availability sensor."""

    _attr_translation_key = "self_input_available"
    _attr_has_entity_name = False
    _attr_name = "Self meter reading available"

    def __init__(self, coordinator: KoreaGasAppDataUpdateCoordinator) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        contract_num = coordinator.data.use_contract_num if coordinator.data else "unknown"
        customer_no = coordinator.data.customer_no if coordinator.data else "unknown"
        account_id = contract_num or customer_no or "unknown"
        self._attr_unique_id = f"self_input_available_{account_id}"
        self.entity_id = f"binary_sensor.self_meter_reading_available_{account_id}"
        self._attr_device_info = {
            "identifiers": {("korea_gasapp", account_id)},
            "name": f"Gas account {account_id}",
            "manufacturer": "Korea Gas App",
        }

    @property
    def is_on(self) -> bool | None:
        """Return true when self meter reading is available."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.self_input_available
