"""Sensors for Korea Gas App."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
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
    """Set up Korea Gas App sensors.

    current_bill_charge and annual_bill_charge are always created.
    indication_history is only created for accounts registered for self-reading;
    if the account registers later the coordinator listener adds it automatically.
    """
    coordinator = entry.runtime_data
    added_history: set[str] = set()

    async_add_entities([
        KoreaGasAppCurrentBillSensor(coordinator),
        KoreaGasAppAnnualBillSensor(coordinator),
    ])

    def _add_history_if_needed() -> None:
        if coordinator.data is None:
            return
        if not coordinator.data.indication.self_reading_registered:
            return
        uid = f"indication_history_{get_account_id(coordinator)}"
        if uid in added_history:
            return
        _LOGGER.debug("Adding indication history sensor for %s", uid)
        added_history.add(uid)
        async_add_entities([KoreaGasAppIndicationHistorySensor(coordinator)])

    _add_history_if_needed()
    entry.async_on_unload(coordinator.async_add_listener(lambda: _add_history_if_needed()))


class _KoreaGasAppBaseSensor(CoordinatorEntity[KoreaGasAppDataUpdateCoordinator], SensorEntity):
    _attr_has_entity_name = False

    def __init__(self, coordinator: KoreaGasAppDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_device_info = build_device_info(get_account_id(coordinator))


class KoreaGasAppCurrentBillSensor(_KoreaGasAppBaseSensor):
    """당월 청구금액 센서."""

    def __init__(self, coordinator: KoreaGasAppDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        aid = get_account_id(coordinator)
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
        _set(attrs, "title", bill.title)
        _set(attrs, "status", bill.status)
        _set(attrs, "payable", bill.payable)
        _set(attrs, "basic_charge_krw", d.basic_charge)
        _set(attrs, "usage_charge_krw", d.usage_charge)
        _set(attrs, "vat_krw", d.vat)
        _set(attrs, "discount_krw", d.discount)
        _set(attrs, "truncation_krw", d.truncation)
        _set(attrs, "unpaid_krw", d.unpaid)
        _set(attrs, "usage_period", d.usage_period)
        _set(attrs, "due_date", d.due_date)
        _set(attrs, "this_month_indicator_m3", d.this_month_indicator)
        _set(attrs, "last_month_indicator_m3", d.last_month_indicator)
        _set(attrs, "monthly_usage_m3", d.monthly_usage)
        _set(attrs, "correction_factor", d.correction_factor)
        _set(attrs, "correction_usage_m3", d.correction_usage)
        _set(attrs, "avg_calorific_mj_m3", d.avg_calorific)
        _set(attrs, "used_calorific_mj", d.used_calorific)
        _set(attrs, "meter_id", d.meter_id)
        _set(attrs, "reading_day", d.reading_day)
        _set(attrs, "reading_method", d.reading_method)
        _set(attrs, "prev_month_usage", d.prev_month_usage)
        _set(attrs, "prev_year_usage", d.prev_year_usage)
        _set(attrs, "discount_type", d.discount_type)
        return attrs


class KoreaGasAppAnnualBillSensor(_KoreaGasAppBaseSensor):
    """연간 청구 이력 센서."""

    def __init__(self, coordinator: KoreaGasAppDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        aid = get_account_id(coordinator)
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
        return bills[0].charge_amt_qty if bills else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if self.coordinator.data is None:
            return {}
        usage: dict[str, Any] = {}
        charge: dict[str, Any] = {}
        for entry in self.coordinator.data.annual_bills:
            if entry.usage_qty is not None:
                usage[entry.request_ym] = entry.usage_qty
            if entry.charge_amt_qty is not None:
                charge[entry.request_ym] = entry.charge_amt_qty
        return {"monthly_usage_m3": usage, "monthly_charge_krw": charge}


class KoreaGasAppIndicationHistorySensor(_KoreaGasAppBaseSensor):
    """자가검침 이력 센서 — 자가검침 등록 계정에만 생성."""

    def __init__(self, coordinator: KoreaGasAppDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        aid = get_account_id(coordinator)
        self._attr_unique_id = f"indication_history_{aid}"
        self.entity_id = f"sensor.indication_history_{aid}"
        self._attr_name = "Gas meter indication history"
        self._attr_device_class = SensorDeviceClass.DATE

    @property
    def native_value(self) -> str | None:
        if self.coordinator.data is None:
            return None
        history = self.coordinator.data.indication_history
        return history[0].reading_date if history else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if self.coordinator.data is None:
            return {}
        entries = []
        for item in self.coordinator.data.indication_history:
            entry: dict[str, Any] = {"reading_date": item.reading_date}
            if item.request_ym:
                entry["request_ym"] = item.request_ym
            if item.indicator is not None:
                entry["indicator_m3"] = item.indicator
            if item.method:
                entry["method"] = item.method
            entries.append(entry)
        return {"history": entries}


def _set(d: dict[str, Any], key: str, value: Any) -> None:
    if value is not None:
        d[key] = value
