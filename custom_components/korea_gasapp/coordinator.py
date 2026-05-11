"""Data coordinator for Korea Gas App."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN

# api is NOT imported at module level — see __init__.py for the explanation.
# GasUsageSnapshot and KoreaGasAppClient are referenced only in type annotations
# (safe because of `from __future__ import annotations`) or inside methods.
if TYPE_CHECKING:
    from .api import GasUsageSnapshot, KoreaGasAppClient
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
        from .api import KoreaGasAppApiError  # lazy import — api must be fully loaded by now

        try:
            return await self.client.async_get_usage()
        except KoreaGasAppApiError as err:
            raise UpdateFailed(str(err)) from err
