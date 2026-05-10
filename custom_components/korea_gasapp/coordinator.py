"""Data coordinator for Korea Gas App."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import GasUsageSnapshot, KoreaGasAppApiError, KoreaGasAppClient
from .const import DOMAIN

if TYPE_CHECKING:
    from .binary_sensor import KoreaGasAppSubmissionResultBinarySensor

_LOGGER = logging.getLogger(__name__)


class KoreaGasAppDataUpdateCoordinator(DataUpdateCoordinator[GasUsageSnapshot]):
    """Coordinator for Korea Gas App sensor data.

    Data is refreshed once a day at 08:00 local time by a time-change listener
    registered in __init__.py.  update_interval is intentionally None so the
    coordinator never polls autonomously between those daily refreshes.
    """

    # Populated by binary_sensor.py when the submission-result entity is added.
    # __init__.py calls set_success / set_failure on it after each submission.
    submission_result_sensor: KoreaGasAppSubmissionResultBinarySensor | None = None

    def __init__(self, hass: HomeAssistant, client: KoreaGasAppClient) -> None:
        super().__init__(
            hass,
            logger=_LOGGER,
            name=DOMAIN,
            update_interval=None,
        )
        self.client = client

    async def _async_update_data(self) -> GasUsageSnapshot:
        try:
            return await self.client.async_get_usage()
        except KoreaGasAppApiError as err:
            raise UpdateFailed(str(err)) from err
