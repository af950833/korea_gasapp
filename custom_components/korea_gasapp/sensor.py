"""Sensors for Korea Gas App."""

from __future__ import annotations

import logging
from typing import Any

import datetime

from homeassistant.components.sensor import SensorEntity, SensorStateClass
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
        self._attr_name = "당월 가스 청구금액"
        self._attr_native_unit_of_measurement = "원"
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
        # API 응답의 모든 항목을 그대로 속성으로 출력.
        # 추가로 청구 제목, 납부 상태, 납부 가능 여부를 앞에 붙임.
        attrs: dict[str, Any] = {}
        if bill.title:
            attrs["청구 제목"] = bill.title
        if bill.status:
            attrs["납부 상태"] = bill.status
        if bill.payable is not None:
            attrs["납부 가능"] = bill.payable
        attrs.update(bill.raw_areas)
        return attrs


# ── Previous-month bill sensor ────────────────────────────────────────────────

class KoreaGasAppAnnualBillSensor(_KoreaGasAppSensorBase):
    """전월 가스 청구금액 센서.

    State      : 전월(두 번째로 최신) 청구금액 (KRW)
    Attributes : 당월·전월을 제외한 나머지 청구 이력
                 키 형식: "YYYYMM 청구액" / "YYYYMM 사용량(m³)"
    """

    def __init__(self, coordinator: KoreaGasAppDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        aid = get_account_id(coordinator)
        self._attr_unique_id = f"annual_bill_charge_{aid}"
        self.entity_id = f"sensor.annual_bill_charge_{aid}"
        self._attr_name = "전월 가스 청구금액"
        self._attr_native_unit_of_measurement = "원"
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> int | None:
        if self.coordinator.data is None:
            return None
        bills = self.coordinator.data.annual_bills
        # bills[0] = 당월, bills[1] = 전월
        return bills[1].charge_amt_qty if len(bills) >= 2 else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if self.coordinator.data is None:
            return {}
        bills = self.coordinator.data.annual_bills
        # 당월(0)·전월(1) 제외, 나머지를 가독성 있는 키로
        attrs: dict[str, Any] = {}
        for bill in bills[2:]:
            ym_key = bill.request_ym.replace("-", "")  # "2024-06" → "202406"
            if bill.charge_amt_qty is not None:
                attrs[f"{ym_key} 청구액"] = bill.charge_amt_qty
            if bill.usage_qty is not None:
                attrs[f"{ym_key} 사용량(m³)"] = bill.usage_qty
        return attrs



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
        self._attr_name = "가스미터 검침 이력"
        # device_class을 DATE로 쓰려면 native_value가 datetime.date 객체여야 함.
        # API 응답이 "YYYY-MM-DD" 문자열이므로 변환 후 반환.

    @property
    def native_value(self) -> datetime.date | None:
        if self.coordinator.data is None:
            return None
        history = self.coordinator.data.indication_history
        if not history:
            return None
        try:
            return datetime.date.fromisoformat(history[0].reading_date)
        except (ValueError, TypeError):
            return None

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
