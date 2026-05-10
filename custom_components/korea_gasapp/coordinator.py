"""Data coordinator for Korea Gas App."""

from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import GasUsageSnapshot, KoreaGasAppApiError, KoreaGasAppClient
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class KoreaGasAppDataUpdateCoordinator(DataUpdateCoordinator[GasUsageSnapshot]):
    """Coordinate Korea Gas App data.

    Data is refreshed once a day at 08:00 by a time-change listener set up in
    __init__.py.  The update_interval is intentionally left as None so the
    coordinator never polls on its own schedule.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        client: KoreaGasAppClient,
    ) -> None:
        super().__init__(
            hass,
            logger=_LOGGER,
            name=DOMAIN,
            update_interval=None,   # driven by fixed-time trigger, not interval
        )
        self.client = client

    async def _async_update_data(self) -> GasUsageSnapshot:
        try:
            return await self.client.async_get_usage()
        except KoreaGasAppApiError as err:
            raise UpdateFailed(str(err)) from err
