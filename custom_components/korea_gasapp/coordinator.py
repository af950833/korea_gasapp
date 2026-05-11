"""Data coordinator for Korea Gas App."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN

# api is NOT imported at module level — see __init__.py for the explanation.
# All api symbols are used only inside method bodies (lazy import) or in
# TYPE_CHECKING blocks (annotations only, never evaluated at runtime).
if TYPE_CHECKING:
    from .api import GasUsageSnapshot, KoreaGasAppClient
    from .binary_sensor import KoreaGasAppSubmissionResultBinarySensor

_LOGGER = logging.getLogger(__name__)


class KoreaGasAppDataUpdateCoordinator(DataUpdateCoordinator):
    """Coordinator for Korea Gas App sensor data.

    Typed as DataUpdateCoordinator without the generic parameter at runtime
    because GasUsageSnapshot lives in api.py which must not be imported at
    module level (circular-import risk during HA platform loading).

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
        from .api import KoreaGasAppApiError  # lazy import — api is fully loaded by now

        try:
            return await self.client.async_get_usage()
        except KoreaGasAppApiError as err:
            raise UpdateFailed(str(err)) from err
