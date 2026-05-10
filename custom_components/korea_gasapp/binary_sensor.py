"""Binary sensors for Korea Gas App."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import KoreaGasAppConfigEntry
from .coordinator import KoreaGasAppDataUpdateCoordinator
from .entity_helper import build_device_info, get_account_id

_LOGGER = logging.getLogger(__name__)

ATTR_LAST_ATTEMPT_AT = "last_attempt_at"
ATTR_READING = "reading"
ATTR_RESULT_MESSAGE = "result_message"
ATTR_FAILURE_REASON = "failure_reason"
ATTR_SOURCE = "source"   # "auto" | "manual"


async def async_setup_entry(
    hass,
    entry: KoreaGasAppConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Korea Gas App binary sensors.

    The submission-result sensor is created only for accounts that have
    registered for the self-reading service.  If the account registers later
    the coordinator listener adds it automatically.
    """
    coordinator = entry.runtime_data
    added: set[str] = set()

    def _add_if_needed() -> None:
        if coordinator.data is None:
            return
        if not coordinator.data.indication.self_reading_registered:
            return
        uid = f"submission_result_{get_account_id(coordinator)}"
        if uid in added:
            return
        _LOGGER.debug("Adding submission-result binary sensor for %s", uid)
        added.add(uid)
        sensor = KoreaGasAppSubmissionResultBinarySensor(coordinator)
        # Expose the sensor so __init__.py can call set_success / set_failure
        coordinator.submission_result_sensor = sensor
        async_add_entities([sensor])

    _add_if_needed()
    entry.async_on_unload(coordinator.async_add_listener(lambda: _add_if_needed()))


class KoreaGasAppSubmissionResultBinarySensor(
    CoordinatorEntity[KoreaGasAppDataUpdateCoordinator],
    BinarySensorEntity,
    RestoreEntity,
):
    """Tracks the last self-meter-reading submission result.

    on  = last submission succeeded
    off = last submission failed, or no submission attempted yet

    State is persisted across HA restarts via RestoreEntity.
    Updated by __init__.py after every automatic or manual submission.
    """

    _attr_has_entity_name = False
    _attr_name = "Gas meter submission result"

    def __init__(self, coordinator: KoreaGasAppDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        aid = get_account_id(coordinator)
        self._attr_unique_id = f"submission_result_{aid}"
        self.entity_id = f"binary_sensor.gas_meter_submission_result_{aid}"
        self._attr_device_info = build_device_info(aid)
        self._success: bool | None = None
        self._extra: dict[str, Any] = {}

    # ------------------------------------------------------------------ #
    # RestoreEntity                                                         #
    # ------------------------------------------------------------------ #

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is None:
            return
        self._success = last.state == "on"
        # Restore all persisted attributes
        self._extra = {k: v for k, v in last.attributes.items()
                       if k in (ATTR_LAST_ATTEMPT_AT, ATTR_READING,
                                ATTR_RESULT_MESSAGE, ATTR_FAILURE_REASON, ATTR_SOURCE)}

    # ------------------------------------------------------------------ #
    # HA properties                                                         #
    # ------------------------------------------------------------------ #

    @property
    def is_on(self) -> bool | None:
        return self._success

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self._extra

    # ------------------------------------------------------------------ #
    # Public API used by __init__.py                                        #
    # ------------------------------------------------------------------ #

    def set_success(self, *, reading: int, message: str | None, source: str) -> None:
        """Mark the last submission as successful."""
        self._success = True
        self._extra = {
            ATTR_LAST_ATTEMPT_AT: datetime.now().isoformat(timespec="seconds"),
            ATTR_READING: reading,
            ATTR_RESULT_MESSAGE: message or "성공",
            ATTR_SOURCE: source,
        }
        self.async_write_ha_state()

    def set_failure(self, *, reading: int | None, reason: str, source: str) -> None:
        """Mark the last submission as failed."""
        self._success = False
        self._extra = {
            ATTR_LAST_ATTEMPT_AT: datetime.now().isoformat(timespec="seconds"),
            ATTR_FAILURE_REASON: reason,
            ATTR_SOURCE: source,
        }
        if reading is not None:
            self._extra[ATTR_READING] = reading
        self.async_write_ha_state()
