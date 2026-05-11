"""Sensors for Korea Gas App."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import KoreaGasAppDataUpdateCoordinator
from .entity_helper import build_device_info, get_account_id

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Korea Gas App sensors.

    Billing sensors are always created.  The indication-history sensor is only
    created for accounts registered for the self-reading service; a coordinator
    listener adds it automatically when registration is detected.
    """
    coordinator: KoreaGasAppDataUpdateCoordinator = entry.runtime_data
    added_uids: set[str] = set()

    async_add_entities([
        KoreaGasAppCurrentBillSensor(coordinator),
        KoreaGasAppAnnualBillSensor(coordinator),
    ])

    def _add_history_sensor_if_needed() -> None:
        if coordinator.data is None:
            return
        if not coordinator.data.indication.self_reading_registered:
            return
        uid = f"indication_history_{get_account_id(coordinator)}"
        if uid in added_uids:
            return
        _LOGGER.debug("Adding indication-history sensor (%s)", uid)
        added_uids.add(uid)
        async_add_entities([KoreaGasAppIndicationHistorySensor(coordinator)])

    _add_history_sensor_if_needed()
    entry.async_on_unload(
        coordinator.async_add_listener(_add_history_sensor_if_needed)
    )


# ── Base class ────────────────────────────────────────────────────────────────

class _KoreaGasAppSensorBase(
    CoordinatorEntity[KoreaGasAppDataUpdateCoordinator],
    SensorEntity,
):
    _attr_has_entity_name = False

    def __init__(self, coordinator: KoreaGasAppDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_device_info = build_device_info(get_account_id(coordinator))


# ── Current-month bill sensor ─────────────────────────────────────────────────

class KoreaGasAppCurrentBillSensor(_KoreaGasAppSensorBase):
    """당월 청구금액 센서.

    State      : 당월 청구금액 (KRW)
    Attributes : 요금 세부 내역 전체 (기본요금, 사용요금, 부가세 등)
    """

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
        return _compact({
            "title":                   bill.title,
            "status":                  bill.status,
            "payable":                 bill.payable,
            "basic_charge_krw":        d.basic_charge,
            "usage_charge_krw":        d.usage_charge,
            "vat_krw":                 d.vat,
            "discount_krw":            d.discount,
            "truncation_krw":          d.truncation,
            "unpaid_krw":              d.unpaid,
            "usage_period":            d.usage_period,
            "due_date":                d.due_date,
            "this_month_indicator_m3": d.this_month_indicator,
            "last_month_indicator_m3": d.last_month_indicator,
            "monthly_usage_m3":        d.monthly_usage,
            "correction_factor":       d.correction_factor,
            "correction_usage_m3":     d.correction_usage,
            "avg_calorific_mj_m3":     d.avg_calorific,
            "used_calorific_mj":       d.used_calorific,
            "meter_id":                d.meter_id,
            "reading_day":             d.reading_day,
            "reading_method":          d.reading_method,
            "prev_month_usage":        d.prev_month_usage,
            "prev_year_usage":         d.prev_year_usage,
            "discount_type":           d.discount_type,
        })


# ── Annual bill history sensor ────────────────────────────────────────────────

class KoreaGasAppAnnualBillSensor(_KoreaGasAppSensorBase):
    """연간 청구 이력 센서.

    State      : 가장 최신 청구연월의 청구금액 (KRW)
    Attributes :
        monthly_usage_m3   — {YYYY-MM: 사용량 m³}
        monthly_charge_krw — {YYYY-MM: 청구금액 KRW}
    """

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
        bills = self.coordinator.data.annual_bills
        return {
            "monthly_usage_m3": {
                b.request_ym: b.usage_qty
                for b in bills if b.usage_qty is not None
            },
            "monthly_charge_krw": {
                b.request_ym: b.charge_amt_qty
                for b in bills if b.charge_amt_qty is not None
            },
        }


# ── Indication-history sensor (self-reading accounts only) ────────────────────

class KoreaGasAppIndicationHistorySensor(_KoreaGasAppSensorBase):
    """자가검침 이력 센서 — 자가검침 등록 계정에만 생성.

    State      : 가장 최근 검침일 (YYYY-MM-DD, SensorDeviceClass.DATE)
    Attributes : history — [{reading_date, request_ym, indicator_m3, method}]
    """

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
        return {
            "history": [
                _compact({
                    "reading_date": item.reading_date,
                    "request_ym":   item.request_ym or None,
                    "indicator_m3": item.indicator,
                    "method":       item.method,
                })
                for item in self.coordinator.data.indication_history
            ]
        }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _compact(d: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of d with None values removed."""
    return {k: v for k, v in d.items() if v is not None}
