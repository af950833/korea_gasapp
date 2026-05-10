"""Home Assistant integration for Korea Gas App."""

from __future__ import annotations

import logging
import math
from datetime import date, datetime, timedelta
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import Platform
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.event import async_track_time_change

from .api import KoreaGasAppApiError, KoreaGasAppClient
from .const import (
    CONF_ACCOUNT_ID,
    CONF_CUSTOMER_NO,
    CONF_READING_ENTITY_ID,
    CONF_READING_ROUND,
    CONF_USE_CONTRACT_NUM,
    DEFAULT_READING_ROUND,
    DOMAIN,
    FIXED_UPDATE_HOUR,
    FIXED_UPDATE_MINUTE,
    FIXED_UPDATE_SECOND,
    READING_ROUND_UP,
)
from .coordinator import KoreaGasAppDataUpdateCoordinator

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.SENSOR]

type KoreaGasAppConfigEntry = ConfigEntry[KoreaGasAppDataUpdateCoordinator]

_LOGGER = logging.getLogger(__name__)

SERVICE_SUBMIT_METER_READING = "submit_meter_reading"
ATTR_ACCOUNT = "account"
ATTR_READING = "reading"

SUBMIT_METER_READING_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ACCOUNT): cv.string,
        vol.Required(ATTR_READING): vol.All(vol.Coerce(int), vol.Range(min=0)),
    }
)


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up Korea Gas App services."""

    async def handle_submit_meter_reading(call: ServiceCall) -> None:
        account = call.data.get(ATTR_ACCOUNT)
        entries = [
            entry
            for entry in hass.config_entries.async_entries(DOMAIN)
            if entry.state is ConfigEntryState.LOADED
        ]
        if account is not None:
            entries = [e for e in entries if _entry_matches_account(e, account)]
        if not entries:
            raise HomeAssistantError("No loaded Korea Gas App config entry found")
        if len(entries) > 1:
            raise HomeAssistantError(
                "Multiple Korea Gas App entries found; pass account to specify one"
            )

        entry = entries[0]
        coordinator = entry.runtime_data
        reading: int = call.data[ATTR_READING]

        try:
            _validate_reading_range(coordinator, reading)
        except HomeAssistantError as err:
            _update_sensor_failure(coordinator, reading=reading, reason=str(err), source="manual")
            raise

        try:
            result = await coordinator.client.async_submit_meter_reading(reading)
        except KoreaGasAppApiError as err:
            _update_sensor_failure(coordinator, reading=reading, reason=str(err), source="manual")
            raise HomeAssistantError(str(err)) from err

        _LOGGER.info(
            "Submitted Korea Gas App meter reading (manual): input_yn=%s usage=%s message=%s",
            result.input_yn,
            result.usage,
            result.return_message,
        )
        _update_sensor_success(
            coordinator,
            reading=reading,
            message=result.return_message,
            source="manual",
        )
        await coordinator.async_request_refresh()

    hass.services.async_register(
        DOMAIN,
        SERVICE_SUBMIT_METER_READING,
        handle_submit_meter_reading,
        schema=SUBMIT_METER_READING_SCHEMA,
    )
    return True


def _entry_matches_account(entry: ConfigEntry, account: str) -> bool:
    normalized = account.strip()
    account_id = entry.data.get(CONF_ACCOUNT_ID)
    use_contract_num = entry.data.get(CONF_USE_CONTRACT_NUM)
    customer_no = entry.data.get(CONF_CUSTOMER_NO)
    values = {
        entry.title,
        account_id,
        use_contract_num,
        customer_no,
        f"Gas account {use_contract_num or customer_no or account_id}",
    }
    return normalized in {str(v) for v in values if v not in (None, "")}


async def async_setup_entry(hass: HomeAssistant, entry: KoreaGasAppConfigEntry) -> bool:
    """Set up Korea Gas App from a config entry."""
    client = KoreaGasAppClient.from_config_entry(hass, entry)
    coordinator = KoreaGasAppDataUpdateCoordinator(hass, client)

    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    entry.async_on_unload(_schedule_daily(hass, entry, coordinator))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: KoreaGasAppConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(hass: HomeAssistant, entry: KoreaGasAppConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


def _schedule_daily(
    hass: HomeAssistant,
    entry: KoreaGasAppConfigEntry,
    coordinator: KoreaGasAppDataUpdateCoordinator,
) -> CALLBACK_TYPE:
    """Register a single daily callback at 08:00 local time.

    At 08:00 each day:
      1. Refresh all coordinator data.
      2. If today is period_start + 1, attempt auto self-reading submission.
         On success → sensor on, on any failure → sensor off with reason.
    """
    reading_round = _entry_value(entry, CONF_READING_ROUND, DEFAULT_READING_ROUND)

    async def _handle_daily(now: datetime) -> None:
        # 1. Refresh data
        _LOGGER.debug("Korea Gas App daily refresh for '%s'", entry.title)
        await coordinator.async_request_refresh()

        # 2. Auto submission guard
        if coordinator.data is None:
            return
        if not coordinator.data.indication.self_reading_registered:
            return

        target_day = _resolve_submit_day(coordinator)
        if target_day is None or now.day != target_day:
            return

        entity_id = _entry_value(entry, CONF_READING_ENTITY_ID)
        if not entity_id:
            reason = "자가검침 엔티티가 설정되지 않았습니다."
            _LOGGER.warning("Skipping auto submission: %s", reason)
            _update_sensor_failure(coordinator, reading=None, reason=reason, source="auto")
            return

        state = hass.states.get(entity_id)
        if state is None:
            reason = f"엔티티 {entity_id}를 찾을 수 없습니다."
            _LOGGER.warning("Skipping auto submission: %s", reason)
            _update_sensor_failure(coordinator, reading=None, reason=reason, source="auto")
            return

        reading = _state_to_reading(state.state, reading_round)
        if reading is None:
            reason = f"엔티티 {entity_id}의 상태값({state.state})을 숫자로 변환할 수 없습니다."
            _LOGGER.warning("Skipping auto submission: %s", reason)
            _update_sensor_failure(coordinator, reading=None, reason=reason, source="auto")
            return

        try:
            _validate_reading_range(coordinator, reading)
        except HomeAssistantError as err:
            reason = str(err)
            _LOGGER.warning("Skipping auto submission: %s", reason)
            _update_sensor_failure(coordinator, reading=reading, reason=reason, source="auto")
            return

        try:
            result = await coordinator.client.async_submit_meter_reading(reading)
        except KoreaGasAppApiError as err:
            reason = str(err)
            _LOGGER.error("Auto submission failed: %s", reason)
            _update_sensor_failure(coordinator, reading=reading, reason=reason, source="auto")
            return

        _LOGGER.info(
            "Auto submission succeeded: reading=%s usage=%s message=%s",
            result.this_month_indicator,
            result.usage,
            result.return_message,
        )
        _update_sensor_success(
            coordinator,
            reading=reading,
            message=result.return_message,
            source="auto",
        )
        await coordinator.async_request_refresh()

    _LOGGER.info(
        "Scheduled Korea Gas App daily update at %02d:%02d:%02d for '%s'",
        FIXED_UPDATE_HOUR, FIXED_UPDATE_MINUTE, FIXED_UPDATE_SECOND, entry.title,
    )
    return async_track_time_change(
        hass,
        _handle_daily,
        hour=FIXED_UPDATE_HOUR,
        minute=FIXED_UPDATE_MINUTE,
        second=FIXED_UPDATE_SECOND,
    )


# --------------------------------------------------------------------------- #
# Sensor update helpers                                                         #
# --------------------------------------------------------------------------- #

def _update_sensor_success(
    coordinator: KoreaGasAppDataUpdateCoordinator,
    *,
    reading: int,
    message: str | None,
    source: str,
) -> None:
    sensor = coordinator.submission_result_sensor
    if sensor is None:
        return
    sensor.set_success(reading=reading, message=message, source=source)


def _update_sensor_failure(
    coordinator: KoreaGasAppDataUpdateCoordinator,
    *,
    reading: int | None,
    reason: str,
    source: str,
) -> None:
    sensor = coordinator.submission_result_sensor
    if sensor is None:
        return
    sensor.set_failure(reading=reading, reason=reason, source=source)


# --------------------------------------------------------------------------- #
# Pure helpers                                                                  #
# --------------------------------------------------------------------------- #

def _resolve_submit_day(coordinator: KoreaGasAppDataUpdateCoordinator) -> int | None:
    if coordinator.data is None:
        return None
    period_start = coordinator.data.indication.period_start
    if not period_start:
        return None
    try:
        return (date.fromisoformat(period_start) + timedelta(days=1)).day
    except (ValueError, TypeError):
        return None


def _entry_value(entry: KoreaGasAppConfigEntry, key: str, default: Any = None) -> Any:
    return entry.options.get(key, entry.data.get(key, default))


def _validate_reading_range(
    coordinator: KoreaGasAppDataUpdateCoordinator,
    reading: int,
) -> None:
    """Raise HomeAssistantError when reading is outside [last, last+500]."""
    if coordinator.data is None or coordinator.data.last_meter_reading_m3 is None:
        raise HomeAssistantError(
            "최근 검침값을 가져올 수 없어 범위 검증이 불가능합니다."
        )
    last_reading = int(coordinator.data.last_meter_reading_m3)
    max_reading = last_reading + 500
    if last_reading <= reading <= max_reading:
        return
    raise HomeAssistantError(
        f"검침값 {reading}이 허용 범위({last_reading}–{max_reading}) 밖입니다."
    )


def _state_to_reading(value: str, reading_round: str) -> int | None:
    if value in {"unknown", "unavailable", ""}:
        return None
    try:
        fval = float(value.replace(",", "").strip())
    except ValueError:
        return None
    return math.ceil(fval) if reading_round == READING_ROUND_UP else math.floor(fval)
