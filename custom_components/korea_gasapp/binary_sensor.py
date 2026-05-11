"""Binary sensors for Korea Gas App."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import KoreaGasAppDataUpdateCoordinator
from .entity_helper import build_device_info, get_account_id

_LOGGER = logging.getLogger(__name__)

# ── Attribute key constants ───────────────────────────────────────────────────
ATTR_LAST_ATTEMPT_AT = "last_attempt_at"
ATTR_READING = "reading"
ATTR_RESULT_MESSAGE = "result_message"
ATTR_FAILURE_REASON = "failure_reason"
ATTR_SOURCE = "source"   # "auto" | "manual"

_RESTORE_ATTRS = frozenset({
    ATTR_LAST_ATTEMPT_AT,
    ATTR_READING,
    ATTR_RESULT_MESSAGE,
    ATTR_FAILURE_REASON,
    ATTR_SOURCE,
})


async def async_setup_entry(
    hass,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Korea Gas App binary sensors.

    The submission-result sensor is created only for accounts registered for
    the self-reading service.  A coordinator listener watches for the account
    signing up later and adds the entity automatically on the next refresh.
    """
    coordinator: KoreaGasAppDataUpdateCoordinator = entry.runtime_data
    added_uids: set[str] = set()

    def _add_submission_sensor_if_needed() -> None:
        if coordinator.data is None:
            return
        if not coordinator.data.indication.self_reading_registered:
            return
        uid = f"submission_result_{get_account_id(coordinator)}"
        if uid in added_uids:
            return
        _LOGGER.debug("Adding submission-result binary sensor (%s)", uid)
        added_uids.add(uid)
        sensor = KoreaGasAppSubmissionResultBinarySensor(coordinator)
        # Store a reference so __init__.py can update the sensor after submissions
        # without needing to query the entity registry.
        coordinator.submission_result_sensor = sensor
        async_add_entities([sensor])

    _add_submission_sensor_if_needed()
    entry.async_on_unload(
        coordinator.async_add_listener(_add_submission_sensor_if_needed)
    )


class KoreaGasAppSubmissionResultBinarySensor(
    CoordinatorEntity[KoreaGasAppDataUpdateCoordinator],
    BinarySensorEntity,
    RestoreEntity,
):
    """Binary sensor that tracks the outcome of the last self-reading submission.

    on  = last submission was accepted by the Gas App API
    off = last submission was rejected / failed, or no submission made yet

    The sensor state is driven entirely by explicit calls to set_success() /
    set_failure() from __init__.py — coordinator refreshes do not change it.
    State is persisted via RestoreEntity so HA restarts preserve the last result.
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
        # Guard: only call async_write_ha_state once the entity is registered
        self._ready = False

    # ── Lifecycle ─────────────────────────────────────────────────────────

    async def async_added_to_hass(self) -> None:
        """Restore the previous state and mark the entity as ready for writes."""
        await super().async_added_to_hass()

        last = await self.async_get_last_state()
        if last is not None:
            self._success = last.state == "on"
            self._extra = {
                k: v for k, v in last.attributes.items() if k in _RESTORE_ATTRS
            }

        self._ready = True

    # ── HA properties ─────────────────────────────────────────────────────

    @property
    def is_on(self) -> bool | None:
        return self._success

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self._extra

    # ── Public update API called by __init__.py ───────────────────────────

    def set_success(self, *, reading: int, message: str | None, source: str) -> None:
        """Record a successful submission and push the state to HA."""
        self._success = True
        self._extra = {
            ATTR_LAST_ATTEMPT_AT: _now_iso(),
            ATTR_READING: reading,
            ATTR_RESULT_MESSAGE: message or "성공",
            ATTR_SOURCE: source,
        }
        self._write_state()

    def set_failure(self, *, reading: int | None, reason: str, source: str) -> None:
        """Record a failed submission and push the state to HA."""
        self._success = False
        self._extra = {
            ATTR_LAST_ATTEMPT_AT: _now_iso(),
            ATTR_FAILURE_REASON: reason,
            ATTR_SOURCE: source,
        }
        if reading is not None:
            self._extra[ATTR_READING] = reading
        self._write_state()

    def _write_state(self) -> None:
        """Call async_write_ha_state only after the entity is fully registered."""
        if self._ready:
            self.async_write_ha_state()


def _now_iso() -> str:
    """Return the current local time as an ISO-8601 string (seconds precision)."""
    return datetime.now().isoformat(timespec="seconds")
