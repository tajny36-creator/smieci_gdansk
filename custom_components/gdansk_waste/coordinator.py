from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    GdanskWasteAddressNotFoundError,
    GdanskWasteApiClient,
    GdanskWasteApiError,
    GdanskWasteConnectionError,
    GdanskWasteNoScheduleError,
    ResolvedAddress,
    ScheduleData,
)
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class GdanskWasteDataUpdateCoordinator(DataUpdateCoordinator[ScheduleData]):
    """Fetch and cache Gdansk waste schedule data."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            logger=_LOGGER,
            name=DOMAIN,
            update_interval=DEFAULT_SCAN_INTERVAL,
        )
        self.config_entry = entry
        self.api = GdanskWasteApiClient(async_get_clientsession(hass))

    @property
    def waste_types(self) -> list[str]:
        if not self.data:
            return []
        return self.data.waste_types

    async def _async_update_data(self) -> ScheduleData:
        address = ResolvedAddress.from_entry_data(dict(self.config_entry.data))

        try:
            current_period = await self.api.async_get_current_period()
            if str(current_period["id"]) != address.schedule_period_id:
                address = await self.api.async_select_address(
                    street=address.street_name,
                    house_number=address.house_number,
                    preferred_group=address.group_name,
                    preferred_street_id=address.street_id,
                )

            schedule = await self.api.async_fetch_schedule(address)
            if not schedule.upcoming_events:
                address = await self.api.async_select_address(
                    street=address.street_name,
                    house_number=address.house_number,
                    preferred_group=address.group_name,
                    preferred_street_id=address.street_id,
                )
                schedule = await self.api.async_fetch_schedule(address)

            self._store_resolved_address(schedule.address)
            return schedule
        except (GdanskWasteAddressNotFoundError, GdanskWasteNoScheduleError, GdanskWasteApiError):
            try:
                # IDs and group mappings can change server-side without notice.
                refreshed_address = await self.api.async_select_address(
                    street=address.street_name,
                    house_number=address.house_number,
                    preferred_group=address.group_name,
                    preferred_street_id=address.street_id,
                )
                schedule = await self.api.async_fetch_schedule(refreshed_address)
                self._store_resolved_address(schedule.address)
                return schedule
            except (
                GdanskWasteAddressNotFoundError,
                GdanskWasteApiError,
                GdanskWasteConnectionError,
                GdanskWasteNoScheduleError,
            ) as err:
                if self.data is not None:
                    _LOGGER.warning(
                        "Update failed for %s, keeping last known schedule: %s",
                        address.label,
                        err,
                    )
                    return self.data
                raise UpdateFailed(str(err)) from err
        except GdanskWasteConnectionError as err:
            if self.data is not None:
                _LOGGER.warning(
                    "Connection issue for %s, keeping last known schedule: %s",
                    address.label,
                    err,
                )
                return self.data
            raise UpdateFailed(str(err)) from err
        except Exception as err:
            if self.data is not None:
                _LOGGER.exception(
                    "Unexpected update error for %s, keeping last known schedule",
                    address.label,
                )
                return self.data
            raise UpdateFailed(str(err)) from err


    def _store_resolved_address(self, address: ResolvedAddress) -> None:
        current_data = dict(self.config_entry.data)
        new_data: dict[str, Any] = {
            **current_data,
            **address.as_entry_data(str(current_data.get(CONF_NAME, address.label))),
        }
        if new_data == current_data:
            return

        self.hass.config_entries.async_update_entry(self.config_entry, data=new_data)
        updated_entry = self.hass.config_entries.async_get_entry(self.config_entry.entry_id)
        if updated_entry is not None:
            self.config_entry = updated_entry
