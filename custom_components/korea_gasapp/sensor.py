"""Sensors for Korea Gas App."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorEntityDescription, SensorStateClass
from homeassistant.const import UnitOfVolume
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import KoreaGasAppConfigEntry
from .api import GasUsageSnapshot
from .coordinator import KoreaGasAppDataUpdateCoordinator


@dataclass(frozen=True, kw_only=True)
class KoreaGasAppSensorEntityDescription(SensorEntityDescription):
    """Describe a Korea Gas App sensor."""

    value_fn: Callable[[GasUsageSnapshot], int | float | str | None]
    extra_attrs_fn: Callable[[GasUsageSnapshot], dict[str, Any]] | None = None


SENSOR_DESCRIPTIONS: tuple[KoreaGasAppSensorEntityDescription, ...] = (
    KoreaGasAppSensorEntityDescription(
        key="latest_bill_charge",
        name="Latest bill gas charge",
        translation_key="latest_bill_charge",
        native_unit_of_measurement="KRW",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.latest_bill_charge_krw,
        extra_attrs_fn=lambda data: {
            "latest_bill_month": data.latest_bill_month,
            "latest_bill_usage_m3": data.latest_bill_usage_m3,
        },
    ),
    KoreaGasAppSensorEntityDescription(
        key="last_meter_reading",
        name="Last meter reading",
        translation_key="last_meter_reading",
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        device_class=SensorDeviceClass.GAS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda data: data.last_meter_reading_m3,
        extra_attrs_fn=lambda data: {
            "latest_indication_date": data.latest_indication_date,
        },
    ),
)


async def async_setup_entry(
    hass,
    entry: KoreaGasAppConfigEntry,
    async_add_entities,
) -> None:
    """Set up Korea Gas App sensors."""
    coordinator = entry.runtime_data
    async_add_entities(
        KoreaGasAppSensor(coordinator, description)
        for description in SENSOR_DESCRIPTIONS
    )


class KoreaGasAppSensor(
    CoordinatorEntity[KoreaGasAppDataUpdateCoordinator],
    SensorEntity,
):
    """Representation of a Korea Gas App sensor."""

    entity_description: KoreaGasAppSensorEntityDescription

    def __init__(
        self,
        coordinator: KoreaGasAppDataUpdateCoordinator,
        description: KoreaGasAppSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        contract_num = coordinator.data.use_contract_num if coordinator.data else "unknown"
        customer_no = coordinator.data.customer_no if coordinator.data else "unknown"
        account_id = contract_num or customer_no or "unknown"
        self._attr_unique_id = f"{description.key}_{account_id}"
        self.entity_id = f"sensor.{description.key}_{account_id}"
        self._attr_has_entity_name = False
        self._attr_name = description.name
        self._attr_device_info = {
            "identifiers": {("korea_gasapp", account_id)},
            "name": f"Gas account {account_id}",
            "manufacturer": "Korea Gas App",
        }

    @property
    def native_value(self) -> int | float | str | None:
        """Return the sensor value."""
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra state attributes."""
        if (
            self.coordinator.data is None
            or self.entity_description.extra_attrs_fn is None
        ):
            return None
        return {
            key: value
            for key, value in self.entity_description.extra_attrs_fn(
                self.coordinator.data
            ).items()
            if value is not None
        }
