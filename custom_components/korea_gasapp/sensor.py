"""Sensors for Korea Gas App."""

from __future__ import annotations

import datetime
import logging
import re
from typing import Any

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

    State      : 당월 청구금액 (원)
    Attributes : API 응답의 모든 항목을 가독성 있게 가공하여 표시
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
        attrs: dict[str, Any] = {}
        if bill.title:
            attrs["청구 제목"] = bill.title
        if bill.status:
            attrs["납부 상태"] = bill.status
        if bill.payable is not None:
            attrs["납부 가능"] = bill.payable
        # API raw 항목을 가독성 있게 가공
        for key, value in bill.raw_areas.items():
            new_key, new_value = _format_bill_item(key, value)
            attrs[new_key] = new_value
            # 사용량 비교 항목은 증감율을 추가 속성으로 삽입
            extra = _format_bill_item_extra(key, value)
            if extra is not None:
                attrs[extra[0]] = extra[1]
        return attrs


# ── Previous-month bill sensor ────────────────────────────────────────────────

class KoreaGasAppAnnualBillSensor(_KoreaGasAppSensorBase):
    """전월 가스 청구금액 센서.

    State      : 전월(두 번째로 최신) 청구금액 (원)
    Attributes : 당월·전월을 제외한 나머지 청구 이력
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
        return bills[1].charge_amt_qty if len(bills) >= 2 else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if self.coordinator.data is None:
            return {}
        bills = self.coordinator.data.annual_bills
        attrs: dict[str, Any] = {}
        for bill in bills[2:]:
            ym_key = bill.request_ym.replace("-", "")  # "2024-06" → "202406"
            if bill.charge_amt_qty is not None:
                attrs[f"{ym_key} 청구액(원)"] = bill.charge_amt_qty
            if bill.usage_qty is not None:
                attrs[f"{ym_key} 사용량(m³)"] = bill.usage_qty
        return attrs


# ── Indication-history sensor (self-reading accounts only) ────────────────────

class KoreaGasAppIndicationHistorySensor(_KoreaGasAppSensorBase):
    """자가검침 이력 센서 — 자가검침 등록 계정에만 생성.

    State      : 가장 최근 검침일 (datetime.date)
    Attributes : 검침 이력 목록 (가독성 있는 키 형식)
    """

    def __init__(self, coordinator: KoreaGasAppDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        aid = get_account_id(coordinator)
        self._attr_unique_id = f"indication_history_{aid}"
        self.entity_id = f"sensor.indication_history_{aid}"
        self._attr_name = "가스미터 검침 이력"

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
        attrs: dict[str, Any] = {}
        for i, item in enumerate(self.coordinator.data.indication_history):
            try:
                d = datetime.date.fromisoformat(item.reading_date)
                date_label = f"{d.year}년 {d.month}월 {d.day}일"
            except (ValueError, TypeError):
                date_label = item.reading_date

            prefix = f"{i + 1}회"
            attrs[f"{prefix} 자가검침일"] = date_label
            if item.indicator is not None:
                attrs[f"{prefix} 지침(m³)"] = item.indicator
            if item.request_ym:
                attrs[f"{prefix} 청구연월"] = item.request_ym
        return attrs


# ── Attribute formatting helpers ──────────────────────────────────────────────

# 값에 포함된 단위 → 속성명에 붙일 단위 문자열 매핑
# "값 단위" 형태의 값에서 단위를 추출해 키에 붙이고, 값은 숫자만 남김
_UNIT_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"^([\d,.]+)\s*MJ/m³$"),   "MJ/m³"),
    (re.compile(r"^([\d,.]+)\s*MJ$"),       "MJ"),
    (re.compile(r"^([\d,.]+)\s*m³$"),       "m³"),
    (re.compile(r"^(-?[\d,]+)\s*원$"),      "원"),
]

# "N m³ (X% 증가/감소)" 패턴 — 전월/전년 사용량 비교
_USAGE_COMPARE_RE = re.compile(
    r"^([\d,.]+)\s*m³\s*\(([-\d.]+)%\s*(증가|감소|동일)?\)?$"
)

# 전월/전년 사용량 비교가 적용될 원본 키 매핑
_COMPARE_KEY_MAP: dict[str, tuple[str, str]] = {
    "전월 사용량":       ("전월 사용량(m³)",    "전월 대비 증감(%)"),
    "전년 동월 사용량":  ("전년 동월 사용량(m³)", "전년 동월 대비 증감(%)"),
}


def _format_bill_item(key: str, value: str) -> tuple[str, Any]:
    """단일 청구서 항목의 키·값을 가독성 있게 변환한다.

    - 단위를 값에서 속성명으로 이동: '42.67 MJ/m³' → 키='평균열량(MJ/m³)', 값=42.67
    - 사용량 비교 문자열 분리:
        '15 m³ (0.0% 증가)' → 키='전월 사용량(m³)', 값=15.0
        (증감율은 별도 키로 추가 — 호출측에서 두 번 호출되도록 구현)
    - 원화 값에서 쉼표 제거 후 정수화: '2,500 원' → 키='기본요금(원)', 값=2500
    """
    stripped = value.strip()

    # 전월/전년 사용량 비교 패턴 처리
    if key in _COMPARE_KEY_MAP:
        m = _USAGE_COMPARE_RE.match(stripped)
        if m:
            usage_key, _ = _COMPARE_KEY_MAP[key]
            num = _to_number(m.group(1))
            return usage_key, num

    # 단위 패턴 처리
    for pattern, unit in _UNIT_PATTERNS:
        m = pattern.match(stripped)
        if m:
            new_key = f"{key}({unit})"
            num = _to_number(m.group(1))
            return new_key, num

    # 변환 불필요 — 원본 그대로
    return key, stripped


def _format_bill_item_extra(key: str, value: str) -> tuple[str, Any] | None:
    """사용량 비교 항목에서 증감율 항목을 추가로 반환한다.

    해당 없으면 None 반환.
    """
    if key not in _COMPARE_KEY_MAP:
        return None
    m = _USAGE_COMPARE_RE.match(value.strip())
    if not m:
        return None
    _, rate_key = _COMPARE_KEY_MAP[key]
    direction = m.group(3) or ""
    rate = float(m.group(2))
    if direction == "감소":
        rate = -abs(rate)
    return rate_key, rate


def _to_number(s: str) -> int | float:
    """쉼표 제거 후 가능하면 int, 아니면 float으로 변환."""
    cleaned = s.replace(",", "")
    try:
        f = float(cleaned)
        return int(f) if f == int(f) else f
    except ValueError:
        return s  # type: ignore[return-value]


def _compact(d: dict[str, Any]) -> dict[str, Any]:
    """None 값을 제거한 복사본을 반환한다."""
    return {k: v for k, v in d.items() if v is not None}
