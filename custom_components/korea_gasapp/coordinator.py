"""Data coordinator for Korea Gas App."""

from __future__ import annotations

from asyncio import sleep
from datetime import timedelta
import logging

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    GasUsageSnapshot,
    KoreaGasAppApiError,
    KoreaGasAppAuthError,
    KoreaGasAppClient,
)
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

UPDATE_RETRY_ATTEMPTS = 3
UPDATE_RETRY_DELAY_SECONDS = 10


class KoreaGasAppDataUpdateCoordinator(DataUpdateCoordinator[GasUsageSnapshot]):
    """Coordinate polling Korea Gas App data."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: KoreaGasAppClient,
        poll_interval_minutes: int,
    ) -> None:
        """Initialize coordinator."""
        super().__init__(
            hass,
            logger=_LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=poll_interval_minutes),
        )
        self.client = client

    async def _async_update_data(self) -> GasUsageSnapshot:
        """Fetch the newest data."""
        last_api_error: KoreaGasAppApiError | None = None
        for attempt in range(1, UPDATE_RETRY_ATTEMPTS + 1):
            try:
                return await self.client.async_get_usage()
            except KoreaGasAppApiError as err:
                last_api_error = err
                if attempt >= UPDATE_RETRY_ATTEMPTS:
                    break
                _LOGGER.debug(
                    "Gas App update attempt %s/%s failed; retrying in %s seconds: %s",
                    attempt,
                    UPDATE_RETRY_ATTEMPTS,
                    UPDATE_RETRY_DELAY_SECONDS,
                    err,
                )
                await sleep(UPDATE_RETRY_DELAY_SECONDS)

        if isinstance(last_api_error, KoreaGasAppAuthError):
            raise ConfigEntryAuthFailed(str(last_api_error)) from last_api_error
        raise UpdateFailed(str(last_api_error or "Gas App update failed"))
