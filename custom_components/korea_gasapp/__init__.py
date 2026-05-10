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
        _validate_reading_range(entry, coordinator, call.data[ATTR_READING])
        try:
            result = await coordinator.client.async_submit_meter_reading(call.data[ATTR_READING])
        except KoreaGasAppApiError as err:
            raise HomeAssistantError(str(err)) from err
        _LOGGER.info(
            "Submitted Korea Gas App meter reading: input_yn=%s usage=%s message=%s",
            result.input_yn,
            result.usage,
            result.return_message,
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
    """Register a single daily callback at FIXED_UPDATE_HOUR:MM:SS (local time).

    At 08:00 each day this callback:
      1. Refreshes all coordinator data (billing + indication info).
      2. If today is the self-reading submission day (period_start + 1),
         submits the meter reading automatically.
    """
    reading_round = _entry_value(entry, CONF_READING_ROUND, DEFAULT_READING_ROUND)

    async def _handle_daily(now: datetime) -> None:
        # ── 1. Refresh data ──────────────────────────────────────────────
        _LOGGER.debug("Korea Gas App daily refresh triggered for entry %s", entry.title)
        await coordinator.async_request_refresh()

        # ── 2. Auto self-reading submission ──────────────────────────────
        if coordinator.data is None:
            return
        if not coordinator.data.indication.self_reading_registered:
            return

        target_day = _resolve_submit_day(coordinator)
        if target_day is None or now.day != target_day:
            return

        entity_id = _entry_value(entry, CONF_READING_ENTITY_ID)
        if not entity_id:
            _LOGGER.warning(
                "Skipping Korea Gas App auto submission: no reading entity configured"
            )
            return

        state = hass.states.get(entity_id)
        if state is None:
            _LOGGER.warning(
                "Skipping Korea Gas App auto submission: entity %s not found", entity_id
            )
            return

        reading = _state_to_reading(state.state, reading_round)
        if reading is None:
            _LOGGER.warning(
                "Skipping Korea Gas App auto submission: entity %s has non-numeric state %s",
                entity_id,
                state.state,
            )
            return

        try:
            _validate_reading_range(entry, coordinator, reading)
        except HomeAssistantError as err:
            _LOGGER.warning("Skipping Korea Gas App auto submission: %s", err)
            return

        try:
            result = await coordinator.client.async_submit_meter_reading(reading)
        except KoreaGasAppApiError as err:
            _LOGGER.error("Korea Gas App auto submission failed: %s", err)
            return

        _LOGGER.info(
            "Korea Gas App auto submission succeeded: reading=%s usage=%s message=%s",
            result.this_month_indicator,
            result.usage,
            result.return_message,
        )
        # Refresh again so sensors reflect the submitted reading
        await coordinator.async_request_refresh()

    _LOGGER.info(
        "Scheduled Korea Gas App daily update at %02d:%02d:%02d for entry '%s'",
        FIXED_UPDATE_HOUR,
        FIXED_UPDATE_MINUTE,
        FIXED_UPDATE_SECOND,
        entry.title,
    )
    return async_track_time_change(
        hass,
        _handle_daily,
        hour=FIXED_UPDATE_HOUR,
        minute=FIXED_UPDATE_MINUTE,
        second=FIXED_UPDATE_SECOND,
    )


def _resolve_submit_day(coordinator: KoreaGasAppDataUpdateCoordinator) -> int | None:
    """Return the day-of-month on which to submit the reading (period_start + 1).

    Returns None when period_start is unavailable, which suppresses submission.
    """
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
    entry: KoreaGasAppConfigEntry,
    coordinator: KoreaGasAppDataUpdateCoordinator,
    reading: int,
) -> None:
    """Validate submitted reading is within [last, last + 500]."""
    if coordinator.data is None or coordinator.data.last_meter_reading_m3 is None:
        raise HomeAssistantError(
            "Cannot validate meter reading because last meter reading is unavailable"
        )
    last_reading = int(coordinator.data.last_meter_reading_m3)
    # Hard-coded maximum delta of 500 m³ (no longer user-configurable)
    max_reading = last_reading + 500
    if last_reading <= reading <= max_reading:
        return
    raise HomeAssistantError(
        f"Meter reading {reading} is outside allowed range {last_reading}–{max_reading}"
    )


def _state_to_reading(value: str, reading_round: str) -> int | None:
    if value in {"unknown", "unavailable", ""}:
        return None
    try:
        fval = float(value.replace(",", "").strip())
    except ValueError:
        return None
    return math.ceil(fval) if reading_round == READING_ROUND_UP else math.floor(fval)
