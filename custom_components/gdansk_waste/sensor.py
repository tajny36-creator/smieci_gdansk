from __future__ import annotations

from datetime import date
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from .api import WasteEvent, normalize_text
from .const import DOMAIN, UPCOMING_LIMIT
from .coordinator import GdanskWasteDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Gdansk waste sensors."""
    coordinator: GdanskWasteDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    known_types: dict[str, GdanskWasteTypeSensor] = {}
    entities: list[SensorEntity] = [GdanskWasteNextPickupSensor(coordinator, entry)]

    for waste_type in coordinator.waste_types:
        entity = GdanskWasteTypeSensor(coordinator, entry, waste_type)
        known_types[waste_type] = entity
        entities.append(entity)

    async_add_entities(entities)

    @callback
    def _add_missing_type_sensors() -> None:
        new_entities: list[SensorEntity] = []
        for waste_type in coordinator.waste_types:
            if waste_type in known_types:
                continue
            entity = GdanskWasteTypeSensor(coordinator, entry, waste_type)
            known_types[waste_type] = entity
            new_entities.append(entity)

        if new_entities:
            async_add_entities(new_entities)

    entry.async_on_unload(coordinator.async_add_listener(_add_missing_type_sensors))


class GdanskWasteBaseSensor(CoordinatorEntity[GdanskWasteDataUpdateCoordinator], SensorEntity):
    """Shared base class for Gdansk waste sensors."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.DATE

    def __init__(
        self,
        coordinator: GdanskWasteDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._device_identifier = entry.unique_id or entry.entry_id

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_identifier)},
            name=str(self._entry.data.get(CONF_NAME, self._entry.title)),
            manufacturer="Miasto Gdansk / ecoHarmonogram",
            model="Harmonogram odbioru odpadow",
            configuration_url="https://czystemiasto.gdansk.pl/harmonogram-odbioru-odpadow/",
        )

    def _days_remaining(self, event: WasteEvent | None) -> int | None:
        if event is None:
            return None
        return (event.collection_date - date.today()).days

    def _common_attributes(self, event: WasteEvent | None) -> dict[str, Any]:
        data = self.coordinator.data
        address = data.address
        attributes: dict[str, Any] = {
            "address": address.label,
            "street": address.street_name,
            "house_number": address.house_number,
            "district": address.district,
            "group": data.group_name,
            "group_description": data.group_description,
            "days_remaining": self._days_remaining(event),
            "period_start": data.period_start,
            "period_end": data.period_end,
        }
        if event is not None:
            attributes["color"] = event.color
            attributes["description"] = event.description
        return attributes


class GdanskWasteNextPickupSensor(GdanskWasteBaseSensor):
    """Sensor exposing the next pickup date across all waste types."""

    _attr_name = "Najblizszy odbior"
    _attr_icon = "mdi:trash-can-clock"

    def __init__(
        self,
        coordinator: GdanskWasteDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{self._device_identifier}-next_pickup"

    @property
    def native_value(self) -> date | None:
        next_event = self._next_event
        return None if next_event is None else next_event.collection_date

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        next_event = self._next_event
        attributes = self._common_attributes(next_event)
        attributes["next_type"] = None if next_event is None else next_event.waste_type
        attributes["upcoming_pickups"] = [
            {
                "date": event.collection_date.isoformat(),
                "type": event.waste_type,
                "color": event.color,
            }
            for event in self.coordinator.data.upcoming_events[:UPCOMING_LIMIT]
        ]
        return attributes

    @property
    def _next_event(self) -> WasteEvent | None:
        upcoming = self.coordinator.data.upcoming_events
        return upcoming[0] if upcoming else None


class GdanskWasteTypeSensor(GdanskWasteBaseSensor):
    """Sensor exposing the next pickup date for a single waste type."""

    def __init__(
        self,
        coordinator: GdanskWasteDataUpdateCoordinator,
        entry: ConfigEntry,
        waste_type: str,
    ) -> None:
        super().__init__(coordinator, entry)
        self._waste_type = waste_type
        self._attr_name = waste_type
        self._attr_unique_id = f"{self._device_identifier}-{slugify(waste_type)}"
        self._attr_icon = self._icon_for_waste_type(waste_type)

    @property
    def native_value(self) -> date | None:
        next_event = self._next_event
        return None if next_event is None else next_event.collection_date

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        next_event = self._next_event
        attributes = self._common_attributes(next_event)
        attributes["waste_type"] = self._waste_type
        attributes["upcoming_dates"] = [
            event.collection_date.isoformat()
            for event in self.coordinator.data.upcoming_events
            if event.waste_type == self._waste_type
        ][:UPCOMING_LIMIT]
        return attributes

    @property
    def _next_event(self) -> WasteEvent | None:
        return self.coordinator.data.next_event_for_type(self._waste_type)

    def _icon_for_waste_type(self, waste_type: str) -> str:
        normalized_name = normalize_text(waste_type)
        if "papier" in normalized_name:
            return "mdi:file-outline"
        if "szklo" in normalized_name:
            return "mdi:bottle-wine-outline"
        if "bio" in normalized_name or "zielone" in normalized_name:
            return "mdi:leaf"
        if "metale" in normalized_name or "tworzywa" in normalized_name:
            return "mdi:recycle"
        if "wielkogabaryt" in normalized_name:
            return "mdi:sofa-outline"
        return "mdi:trash-can-outline"
