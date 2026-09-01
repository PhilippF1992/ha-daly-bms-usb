"""DataUpdateCoordinator for the Daly BMS USB integration."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .client import (
    DalyBmsClient,
    DalyClientError,
    DalyConnectionError,
    DalyData,
)
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class DalyBmsCoordinator(DataUpdateCoordinator[DalyData]):
    """Owns the single Daly client and pushes DalyData snapshots to entities."""

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        config_entry: ConfigEntry | None,
        client: DalyBmsClient,
        poll_interval_seconds: int,
        entry_title: str,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=f"{DOMAIN} ({entry_title})",
            update_interval=timedelta(seconds=poll_interval_seconds),
        )
        self._client = client
        # asyncio-level lock so a manual write cannot start during a poll and
        # vice versa. Serial-level locking already exists inside the client
        # (a threading.Lock), but the asyncio lock avoids scheduling overlaps
        # and forces write callers to await pending polls cleanly.
        self._io_lock = asyncio.Lock()
        self._unavailable_warned = False
        self.last_success_at: datetime | None = None

    @property
    def client(self) -> DalyBmsClient:
        return self._client

    @property
    def io_lock(self) -> asyncio.Lock:
        return self._io_lock

    async def _async_update_data(self) -> DalyData:
        async with self._io_lock:
            try:
                if not self._client.is_connected:
                    await self.hass.async_add_executor_job(self._client.connect)
                data = await self.hass.async_add_executor_job(self._client.poll)
            except DalyConnectionError as err:
                # Try to close a possibly-dead handle before raising.
                await self.hass.async_add_executor_job(self._client.disconnect)
                if not self._unavailable_warned:
                    _LOGGER.warning("Daly BMS connection lost: %s", err)
                    self._unavailable_warned = True
                raise UpdateFailed(str(err)) from err
            except DalyClientError as err:
                if not self._unavailable_warned:
                    _LOGGER.warning("Daly BMS communication error: %s", err)
                    self._unavailable_warned = True
                raise UpdateFailed(str(err)) from err
        if self._unavailable_warned:
            _LOGGER.info("Daly BMS connection restored")
            self._unavailable_warned = False
        self.last_success_at = datetime.now(tz=UTC)
        return data

    async def async_shutdown_client(self) -> None:
        """Close the serial port cleanly on unload."""
        await self.hass.async_add_executor_job(self._client.disconnect)
