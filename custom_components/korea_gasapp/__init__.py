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
_ATTR_ACCOUNT = "account"
_ATTR_READING = "reading"

_SUBMIT_SCHEMA = vol.Schema(
    {
        vol.Optional(_ATTR_ACCOUNT): cv.string,
        vol.Required(_ATTR_READING): vol.All(vol.Coerce(int), vol.Range(min=0)),
    }
)


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Register the submit_meter_reading service."""

    async def _handle_submit(call: ServiceCall) -> None:
        coordinator = _resolve_coordinator(hass, call.data.get(_ATTR_ACCOUNT))
        reading: int = call.data[_ATTR_READING]

        try:
            result = await coordinator.client.async_submit_meter_reading(reading)
        except KoreaGasAppApiError as err:
            _notify_sensor_failure(coordinator, reading=reading, reason=str(err), source="manual")
            raise HomeAssistantError(str(err)) from err

        _LOGGER.info(
            "Manual meter reading submitted: reading=%s usage=%s message=%s",
            reading,
            result.usage,
            result.return_message,
        )
        _notify_sensor_success(coordinator, reading=reading, message=result.return_message, source="manual")
        await coordinator.async_request_refresh()

    hass.services.async_register(DOMAIN, SERVICE_SUBMIT_METER_READING, _handle_submit, schema=_SUBMIT_SCHEMA)
    return True


def _resolve_coordinator(
    hass: HomeAssistant,
    account: str | None,
) -> KoreaGasAppDataUpdateCoordinator:
    """Return the coordinator for the requested account, raising on ambiguity."""
    loaded = [
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.state is ConfigEntryState.LOADED
    ]
    if account is not None:
        loaded = [e for e in loaded if _entry_matches_account(e, account)]

    if not loaded:
        raise HomeAssistantError("No loaded Korea Gas App config entry found")
    if len(loaded) > 1:
        raise HomeAssistantError(
            "Multiple Korea Gas App entries match; pass 'account' to specify one"
        )
    return loaded[0].runtime_data


def _entry_matches_account(entry: ConfigEntry, account: str) -> bool:
    """Return True if the entry's identifiers contain the given account string."""
    normalized = account.strip()
    use_contract_num = entry.data.get(CONF_USE_CONTRACT_NUM)
    customer_no = entry.data.get(CONF_CUSTOMER_NO)
    account_id = entry.data.get(CONF_ACCOUNT_ID)
    candidates = {
        entry.title,
        account_id,
        use_contract_num,
        customer_no,
        f"Gas account {use_contract_num or customer_no or account_id}",
    }
    return normalized in {str(v) for v in candidates if v not in (None, "")}


async def async_setup_entry(hass: HomeAssistant, entry: KoreaGasAppConfigEntry) -> bool:
    """Set up a Korea Gas App config entry."""
    client = KoreaGasAppClient.from_config_entry(hass, entry)
    coordinator = KoreaGasAppDataUpdateCoordinator(hass, client)

    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    entry.async_on_unload(entry.add_update_listener(_handle_options_update))
    entry.async_on_unload(_schedule_daily(hass, entry, coordinator))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: KoreaGasAppConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _handle_options_update(hass: HomeAssistant, entry: KoreaGasAppConfigEntry) -> None:
    """Reload the entry when options change so the new reading entity/round takes effect."""
    await hass.config_entries.async_reload(entry.entry_id)


def _schedule_daily(
    hass: HomeAssistant,
    entry: KoreaGasAppConfigEntry,
    coordinator: KoreaGasAppDataUpdateCoordinator,
) -> CALLBACK_TYPE:
    """Register a time-change callback that fires once a day at FIXED_UPDATE_HOUR.

    Each day the callback:
      1. Refreshes all coordinator data (bills + indication info).
      2. If the account is registered for self-reading and today is
         period_start + 1, attempts automatic submission.  Any outcome
         (success or failure) is written to the submission-result sensor.
    """
    reading_round = _entry_value(entry, CONF_READING_ROUND, DEFAULT_READING_ROUND)

    async def _daily_callback(now: datetime) -> None:
        _LOGGER.debug("Daily refresh triggered for '%s'", entry.title)
        await coordinator.async_request_refresh()
        await _attempt_auto_submission(hass, entry, coordinator, now, reading_round)

    _LOGGER.info(
        "Scheduled daily update at %02d:%02d:%02d for entry '%s'",
        FIXED_UPDATE_HOUR, FIXED_UPDATE_MINUTE, FIXED_UPDATE_SECOND, entry.title,
    )
    return async_track_time_change(
        hass,
        _daily_callback,
        hour=FIXED_UPDATE_HOUR,
        minute=FIXED_UPDATE_MINUTE,
        second=FIXED_UPDATE_SECOND,
    )


async def _attempt_auto_submission(
    hass: HomeAssistant,
    entry: KoreaGasAppConfigEntry,
    coordinator: KoreaGasAppDataUpdateCoordinator,
    now: datetime,
    reading_round: str,
) -> None:
    """Try to auto-submit a self-reading; write result to sensor regardless of outcome."""
    if coordinator.data is None:
        return
    if not coordinator.data.indication.self_reading_registered:
        return

    submit_day = _resolve_submit_day(coordinator)
    if submit_day is None or now.day != submit_day:
        return

    entity_id = _entry_value(entry, CONF_READING_ENTITY_ID)
    if not entity_id:
        _fail("자가검침 엔티티가 설정되지 않았습니다.", coordinator, reading=None)
        return

    state = hass.states.get(entity_id)
    if state is None:
        _fail(f"엔티티 {entity_id}를 찾을 수 없습니다.", coordinator, reading=None)
        return

    reading = _state_to_reading(state.state, reading_round)
    if reading is None:
        _fail(
            f"엔티티 {entity_id}의 상태값({state.state!r})을 숫자로 변환할 수 없습니다.",
            coordinator,
            reading=None,
        )
        return

    try:
        result = await coordinator.client.async_submit_meter_reading(reading)
    except KoreaGasAppApiError as err:
        _LOGGER.error("Auto submission failed for '%s': %s", entry.title, err)
        _notify_sensor_failure(coordinator, reading=reading, reason=str(err), source="auto")
        return

    _LOGGER.info(
        "Auto submission succeeded for '%s': reading=%s usage=%s message=%s",
        entry.title, reading, result.usage, result.return_message,
    )
    _notify_sensor_success(coordinator, reading=reading, message=result.return_message, source="auto")
    await coordinator.async_request_refresh()


def _fail(reason: str, coordinator: KoreaGasAppDataUpdateCoordinator, *, reading: int | None) -> None:
    """Log a warning and record failure on the result sensor."""
    _LOGGER.warning("Auto submission skipped: %s", reason)
    _notify_sensor_failure(coordinator, reading=reading, reason=reason, source="auto")


# ── Sensor notification helpers ───────────────────────────────────────────────

def _notify_sensor_success(
    coordinator: KoreaGasAppDataUpdateCoordinator,
    *,
    reading: int,
    message: str | None,
    source: str,
) -> None:
    if coordinator.submission_result_sensor is not None:
        coordinator.submission_result_sensor.set_success(
            reading=reading, message=message, source=source
        )


def _notify_sensor_failure(
    coordinator: KoreaGasAppDataUpdateCoordinator,
    *,
    reading: int | None,
    reason: str,
    source: str,
) -> None:
    if coordinator.submission_result_sensor is not None:
        coordinator.submission_result_sensor.set_failure(
            reading=reading, reason=reason, source=source
        )


# ── Pure helpers ──────────────────────────────────────────────────────────────

def _resolve_submit_day(coordinator: KoreaGasAppDataUpdateCoordinator) -> int | None:
    """Return the day-of-month on which to submit (period_start + 1).

    Returns None when period_start is unavailable, suppressing auto-submission
    for that day rather than guessing.
    """
    period_start = coordinator.data.indication.period_start if coordinator.data else None
    if not period_start:
        return None
    try:
        return (date.fromisoformat(period_start) + timedelta(days=1)).day
    except (ValueError, TypeError):
        _LOGGER.warning("Could not parse period_start value: %r", period_start)
        return None


def _entry_value(entry: KoreaGasAppConfigEntry, key: str, default: Any = None) -> Any:
    """Read a value from options first, falling back to config-entry data."""
    return entry.options.get(key, entry.data.get(key, default))


def _state_to_reading(value: str, reading_round: str) -> int | None:
    """Convert an entity state string to an integer using the configured rounding.

    Returns None for unavailable / non-numeric states.
    """
    if value in {"unknown", "unavailable", ""}:
        return None
    try:
        fval = float(value.replace(",", "").strip())
    except ValueError:
        return None
    return math.ceil(fval) if reading_round == READING_ROUND_UP else math.floor(fval)
