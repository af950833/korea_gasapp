"""Home Assistant integration for Korea Gas App."""

from __future__ import annotations

import logging
from datetime import datetime, time
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
    CONF_MAX_READING_DELTA,
    CONF_POLL_INTERVAL,
    CONF_READING_ENTITY_ID,
    CONF_SUBMIT_DAY,
    CONF_SUBMIT_TIME,
    CONF_USE_CONTRACT_NUM,
    DEFAULT_MAX_READING_DELTA,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_SUBMIT_DAY,
    DEFAULT_SUBMIT_TIME,
    DOMAIN,
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
        """Handle the meter reading submission service."""
        account = call.data.get(ATTR_ACCOUNT)
        entries = [
            entry
            for entry in hass.config_entries.async_entries(DOMAIN)
            if entry.state is ConfigEntryState.LOADED
        ]
        if account is not None:
            entries = [
                entry for entry in entries if _entry_matches_account(entry, account)
            ]
        if not entries:
            raise HomeAssistantError("No loaded Korea Gas App config entry found")
        if len(entries) > 1:
            raise HomeAssistantError(
                "Multiple Korea Gas App entries found; pass account"
            )

        entry = entries[0]
        coordinator = entry.runtime_data
        _validate_reading_range(entry, coordinator, call.data[ATTR_READING])
        try:
            result = await coordinator.client.async_submit_meter_reading(
                call.data[ATTR_READING],
            )
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
    """Return whether a config entry matches a user-facing account value."""
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
    return normalized in {str(value) for value in values if value not in (None, "")}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KoreaGasAppConfigEntry,
) -> bool:
    """Set up Korea Gas App from a config entry."""
    poll_interval = entry.options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
    client = KoreaGasAppClient.from_config_entry(hass, entry)
    coordinator = KoreaGasAppDataUpdateCoordinator(hass, client, poll_interval)

    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    entry.async_on_unload(_schedule_auto_submission(hass, entry, coordinator))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant,
    entry: KoreaGasAppConfigEntry,
) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(
    hass: HomeAssistant,
    entry: KoreaGasAppConfigEntry,
) -> None:
    """Reload the integration when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


def _schedule_auto_submission(
    hass: HomeAssistant,
    entry: KoreaGasAppConfigEntry,
    coordinator: KoreaGasAppDataUpdateCoordinator,
) -> CALLBACK_TYPE:
    """Schedule the configured monthly self-reading submission."""
    submit_time = _parse_submit_time(
        _entry_value(entry, CONF_SUBMIT_TIME, DEFAULT_SUBMIT_TIME)
    )
    submit_day = int(_entry_value(entry, CONF_SUBMIT_DAY, DEFAULT_SUBMIT_DAY))

    async def _handle_time(now: datetime) -> None:
        if now.day != submit_day:
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
                "Skipping Korea Gas App auto submission: entity %s was not found",
                entity_id,
            )
            return

        reading = _state_to_reading(state.state)
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
        await coordinator.async_request_refresh()

    _LOGGER.info(
        "Scheduled Korea Gas App auto submission for day %s at %s using %s",
        submit_day,
        submit_time.isoformat(),
        _entry_value(entry, CONF_READING_ENTITY_ID, "no entity"),
    )
    return async_track_time_change(
        hass,
        _handle_time,
        hour=submit_time.hour,
        minute=submit_time.minute,
        second=submit_time.second,
    )


def _entry_value(
    entry: KoreaGasAppConfigEntry,
    key: str,
    default: Any | None = None,
) -> Any:
    """Return an option value, falling back to config-entry data."""
    return entry.options.get(key, entry.data.get(key, default))


def _validate_reading_range(
    entry: KoreaGasAppConfigEntry,
    coordinator: KoreaGasAppDataUpdateCoordinator,
    reading: int,
) -> None:
    """Validate a submitted reading against the latest meter reading."""
    if coordinator.data is None or coordinator.data.last_meter_reading_m3 is None:
        raise HomeAssistantError(
            "Cannot validate meter reading because last meter reading is unavailable"
        )

    last_reading = int(coordinator.data.last_meter_reading_m3)
    max_delta = int(
        _entry_value(entry, CONF_MAX_READING_DELTA, DEFAULT_MAX_READING_DELTA)
    )
    max_reading = last_reading + max_delta
    if last_reading <= reading <= max_reading:
        return

    raise HomeAssistantError(
        f"Meter reading {reading} is outside allowed range "
        f"{last_reading}-{max_reading}"
    )


def _parse_submit_time(value: Any) -> time:
    """Parse a config-flow time value."""
    if isinstance(value, time):
        return value
    parts = [int(part) for part in str(value).split(":")]
    if len(parts) == 2:
        parts.append(0)
    return time(parts[0], parts[1], parts[2])


def _state_to_reading(value: str) -> int | None:
    """Convert an entity state to a meter reading integer."""
    if value in {"unknown", "unavailable", ""}:
        return None
    try:
        return int(float(value.replace(",", "").strip()))
    except ValueError:
        return None
