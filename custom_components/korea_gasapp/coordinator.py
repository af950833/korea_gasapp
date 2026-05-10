"""Data coordinator for Korea Gas App."""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import GasUsageSnapshot, KoreaGasAppApiError, KoreaGasAppClient
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class KoreaGasAppDataUpdateCoordinator(DataUpdateCoordinator[GasUsageSnapshot]):
    """Coordinate polling Korea Gas App data."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: KoreaGasAppClient,
        poll_interval_minutes: int,
    ) -> None:
        super().__init__(
            hass,
            logger=_LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=poll_interval_minutes),
        )
        self.client = client

    async def _async_update_data(self) -> GasUsageSnapshot:
        try:
            return await self.client.async_get_usage()
        except KoreaGasAppApiError as err:
            raise UpdateFailed(str(err)) from err
