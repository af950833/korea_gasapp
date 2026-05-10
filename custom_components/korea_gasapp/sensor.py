"""Sensors for Korea Gas App."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import KoreaGasAppConfigEntry
from .coordinator import KoreaGasAppDataUpdateCoordinator


def _account_id(coordinator: KoreaGasAppDataUpdateCoordinator) -> str:
    if coordinator.data:
        return coordinator.data.use_contract_num or coordinator.data.customer_no or "unknown"
    return "unknown"


async def async_setup_entry(
    hass,
    entry: KoreaGasAppConfigEntry,
    async_add_entities,
) -> None:
    """Set up Korea Gas App sensors."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            KoreaGasAppCurrentBillSensor(coordinator),
            KoreaGasAppAnnualBillSensor(coordinator),
            KoreaGasAppIndicationHistorySensor(coordinator),
        ]
    )


class _KoreaGasAppBaseSensor(
    CoordinatorEntity[KoreaGasAppDataUpdateCoordinator],
    SensorEntity,
):
    """Base class for Korea Gas App sensors."""

    _attr_has_entity_name = False

    def __init__(self, coordinator: KoreaGasAppDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        aid = _account_id(coordinator)
        self._attr_device_info = {
            "identifiers": {("korea_gasapp", aid)},
            "name": f"Gas account {aid}",
            "manufacturer": "Korea Gas App",
        }


class KoreaGasAppCurrentBillSensor(_KoreaGasAppBaseSensor):
    """Current month bill charge sensor with detailed breakdown attributes."""

    def __init__(self, coordinator: KoreaGasAppDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        aid = _account_id(coordinator)
        self._attr_unique_id = f"current_bill_charge_{aid}"
        self.entity_id = f"sensor.current_bill_charge_{aid}"
        self._attr_name = "Current bill gas charge"
        self._attr_native_unit_of_measurement = "KRW"
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> int | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.current_bill.charge_krw

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if self.coordinator.data is None:
            return {}
        bill = self.coordinator.data.current_bill
        d = bill.detail
        attrs: dict[str, Any] = {}
        if bill.title is not None:
            attrs["title"] = bill.title
        if bill.status is not None:
            attrs["status"] = bill.status
        if bill.payable is not None:
            attrs["payable"] = bill.payable
        # Detail breakdown
        _add_if_not_none(attrs, "basic_charge_krw", d.basic_charge)
        _add_if_not_none(attrs, "usage_charge_krw", d.usage_charge)
        _add_if_not_none(attrs, "vat_krw", d.vat)
        _add_if_not_none(attrs, "discount_krw", d.discount)
        _add_if_not_none(attrs, "truncation_krw", d.truncation)
        _add_if_not_none(attrs, "unpaid_krw", d.unpaid)
        _add_if_not_none(attrs, "usage_period", d.usage_period)
        _add_if_not_none(attrs, "due_date", d.due_date)
        _add_if_not_none(attrs, "this_month_indicator_m3", d.this_month_indicator)
        _add_if_not_none(attrs, "last_month_indicator_m3", d.last_month_indicator)
        _add_if_not_none(attrs, "monthly_usage_m3", d.monthly_usage)
        _add_if_not_none(attrs, "correction_factor", d.correction_factor)
        _add_if_not_none(attrs, "correction_usage_m3", d.correction_usage)
        _add_if_not_none(attrs, "avg_calorific_mj_m3", d.avg_calorific)
        _add_if_not_none(attrs, "used_calorific_mj", d.used_calorific)
        _add_if_not_none(attrs, "meter_id", d.meter_id)
        _add_if_not_none(attrs, "reading_day", d.reading_day)
        _add_if_not_none(attrs, "reading_method", d.reading_method)
        _add_if_not_none(attrs, "prev_month_usage", d.prev_month_usage)
        _add_if_not_none(attrs, "prev_year_usage", d.prev_year_usage)
        _add_if_not_none(attrs, "discount_type", d.discount_type)
        return attrs


class KoreaGasAppAnnualBillSensor(_KoreaGasAppBaseSensor):
    """Annual bill history sensor.

    State = most recent month's charge amount.
    Attributes = per-month usage and charge history.
    """

    def __init__(self, coordinator: KoreaGasAppDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        aid = _account_id(coordinator)
        self._attr_unique_id = f"annual_bill_charge_{aid}"
        self.entity_id = f"sensor.annual_bill_charge_{aid}"
        self._attr_name = "Annual bill gas charge"
        self._attr_native_unit_of_measurement = "KRW"
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> int | None:
        if self.coordinator.data is None:
            return None
        bills = self.coordinator.data.annual_bills
        if not bills:
            return None
        # Bills are sorted newest-first
        return bills[0].charge_amt_qty

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if self.coordinator.data is None:
            return {}
        bills = self.coordinator.data.annual_bills
        # Build two attribute lists: usage and charge per month
        usage_by_month: dict[str, Any] = {}
        charge_by_month: dict[str, Any] = {}
        for entry in bills:
            if entry.usage_qty is not None:
                usage_by_month[entry.request_ym] = entry.usage_qty
            if entry.charge_amt_qty is not None:
                charge_by_month[entry.request_ym] = entry.charge_amt_qty
        return {
            "monthly_usage_m3": usage_by_month,
            "monthly_charge_krw": charge_by_month,
        }


class KoreaGasAppIndicationHistorySensor(_KoreaGasAppBaseSensor):
    """Self-reading history sensor.

    State = most recent reading date (YYYY-MM-DD).
    Attributes = per-entry reading date and indicator value.
    """

    def __init__(self, coordinator: KoreaGasAppDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        aid = _account_id(coordinator)
        self._attr_unique_id = f"indication_history_{aid}"
        self.entity_id = f"sensor.indication_history_{aid}"
        self._attr_name = "Gas meter indication history"
        self._attr_device_class = SensorDeviceClass.DATE

    @property
    def native_value(self) -> str | None:
        if self.coordinator.data is None:
            return None
        history = self.coordinator.data.indication_history
        if not history:
            return None
        return history[0].reading_date

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if self.coordinator.data is None:
            return {}
        history = self.coordinator.data.indication_history
        entries = []
        for item in history:
            entry: dict[str, Any] = {"reading_date": item.reading_date}
            if item.request_ym:
                entry["request_ym"] = item.request_ym
            if item.indicator is not None:
                entry["indicator_m3"] = item.indicator
            if item.method:
                entry["method"] = item.method
            entries.append(entry)
        return {"history": entries}


def _add_if_not_none(d: dict[str, Any], key: str, value: Any) -> None:
    if value is not None:
        d[key] = value
