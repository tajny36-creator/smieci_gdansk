from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
import logging
import re
from typing import Any
import unicodedata

from aiohttp import ClientError, ClientSession

from .const import (
    API_BASE_URL,
    COMMUNITY_ID,
    CONF_DISTRICT,
    CONF_GROUP_DESCRIPTION,
    CONF_GROUP_NAME,
    CONF_HOUSE_NUMBER,
    CONF_NAME,
    CONF_SCHEDULE_PERIOD_ID,
    CONF_SIDES,
    CONF_STAMP,
    CONF_STREET,
    CONF_STREET_ID,
    CONF_STREET_NAME,
    CONF_TOWN_ID,
    CONF_TOWN_NAME,
    IGNORED_SCHEDULE_TYPES,
    REQUEST_TIMEOUT,
)

_LOGGER = logging.getLogger(__name__)

_PREFIX_RE = re.compile(
    r"^(?:ul(?:ica)?|al(?:eja)?|pl(?:ac)?|os(?:iedle)?|rondo|skwer)\.?\s*",
    re.IGNORECASE,
)


class GdanskWasteError(Exception):
    """Base exception for the integration."""


class GdanskWasteConnectionError(GdanskWasteError):
    """Raised when the upstream API cannot be reached."""


class GdanskWasteApiError(GdanskWasteError):
    """Raised when the upstream API returns invalid data."""


class GdanskWasteAddressNotFoundError(GdanskWasteError):
    """Raised when the requested address cannot be resolved."""


class GdanskWasteNoScheduleError(GdanskWasteError):
    """Raised when an address has no schedule data."""


def normalize_text(value: str) -> str:
    """Normalize user input for address comparisons."""
    value = value.strip().lower()
    value = "".join(
        character
        for character in unicodedata.normalize("NFKD", value)
        if not unicodedata.combining(character)
    )
    value = _PREFIX_RE.sub("", value)
    value = re.sub(r"[^0-9a-z]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def normalize_house_number(value: str) -> str:
    """Normalize a house number."""
    return value.strip().upper().replace(" ", "")


@dataclass(slots=True)
class WasteEvent:
    """Single waste collection event."""

    collection_date: date
    waste_type: str
    color: str | None
    description: str | None
    order: int


@dataclass(slots=True)
class ResolvedAddress:
    """Address resolved against the Gdansk waste API."""

    street_id: str
    street_name: str
    house_number: str
    town_id: str
    town_name: str
    schedule_period_id: str
    group_name: str
    group_description: str
    district: str
    sides: str
    stamp: str

    @property
    def unique_id(self) -> str:
        return ":".join(
            (
                self.town_id,
                normalize_text(self.street_name),
                normalize_house_number(self.house_number),
                normalize_text(self.group_name),
                normalize_text(self.sides),
            )
        )

    @property
    def label(self) -> str:
        details = [item for item in (self.group_name, self.district, self.sides) if item]
        if details:
            return f"{self.street_name} {self.house_number} ({', '.join(details)})"
        return f"{self.street_name} {self.house_number}"

    def as_entry_data(self, name: str) -> dict[str, str]:
        return {
            CONF_NAME: name,
            CONF_STREET: self.street_name,
            CONF_HOUSE_NUMBER: self.house_number,
            CONF_STREET_ID: self.street_id,
            CONF_STREET_NAME: self.street_name,
            CONF_TOWN_ID: self.town_id,
            CONF_TOWN_NAME: self.town_name,
            CONF_SCHEDULE_PERIOD_ID: self.schedule_period_id,
            CONF_GROUP_NAME: self.group_name,
            CONF_GROUP_DESCRIPTION: self.group_description,
            CONF_DISTRICT: self.district,
            CONF_SIDES: self.sides,
            CONF_STAMP: self.stamp,
        }

    @classmethod
    def from_entry_data(cls, data: dict[str, Any]) -> ResolvedAddress:
        return cls(
            street_id=str(data[CONF_STREET_ID]),
            street_name=str(data[CONF_STREET_NAME]),
            house_number=str(data[CONF_HOUSE_NUMBER]),
            town_id=str(data[CONF_TOWN_ID]),
            town_name=str(data[CONF_TOWN_NAME]),
            schedule_period_id=str(data[CONF_SCHEDULE_PERIOD_ID]),
            group_name=str(data.get(CONF_GROUP_NAME, "")),
            group_description=str(data.get(CONF_GROUP_DESCRIPTION, "")),
            district=str(data.get(CONF_DISTRICT, "")),
            sides=str(data.get(CONF_SIDES, "")),
            stamp=str(data.get(CONF_STAMP, "")),
        )


@dataclass(slots=True)
class ScheduleData:
    """Parsed schedule data for an address."""

    address: ResolvedAddress
    events: list[WasteEvent]
    group_name: str
    group_description: str
    period_start: str | None
    period_end: str | None

    @property
    def upcoming_events(self) -> list[WasteEvent]:
        today = date.today()
        return [event for event in self.events if event.collection_date >= today]

    @property
    def waste_types(self) -> list[str]:
        return sorted(
            {event.waste_type for event in self.upcoming_events},
            key=lambda waste_type: min(
                (
                    event.order
                    for event in self.events
                    if event.waste_type == waste_type
                ),
                default=999,
            ),
        )

    def next_event_for_type(self, waste_type: str) -> WasteEvent | None:
        return next(
            (event for event in self.upcoming_events if event.waste_type == waste_type),
            None,
        )


class GdanskWasteApiClient:
    """Client for the Gdansk waste schedule endpoints."""

    def __init__(self, session: ClientSession) -> None:
        self._session = session

    async def _post(self, endpoint: str, payload: dict[str, str]) -> dict[str, Any]:
        url = f"{API_BASE_URL}/{endpoint}"
        try:
            async with self._session.post(url, data=payload, timeout=REQUEST_TIMEOUT) as response:
                response.raise_for_status()
                result = await response.json(content_type=None)
        except ClientError as err:
            raise GdanskWasteConnectionError(f"Cannot reach {endpoint}") from err
        except ValueError as err:
            raise GdanskWasteApiError(f"Invalid JSON returned by {endpoint}") from err

        if not result.get("success"):
            raise GdanskWasteApiError(
                f"API error for {endpoint}: {result.get('status', 'unknown')}"
            )

        data = result.get("data")
        if not isinstance(data, dict):
            raise GdanskWasteApiError(f"Missing data payload for {endpoint}")

        return data

    async def async_get_town(self) -> dict[str, Any]:
        data = await self._post("townsForCommunity", {"communityId": COMMUNITY_ID})
        towns = data.get("towns", [])
        for town in towns:
            if normalize_text(str(town.get("name", ""))) == "gdansk":
                return town
        raise GdanskWasteApiError("Town Gdansk was not found in the API response")

    async def async_get_current_period(self) -> dict[str, Any]:
        data = await self._post(
            "schedulePeriodsWithDataForCommunity",
            {"communityId": COMMUNITY_ID},
        )
        periods = data.get("schedulePeriods", [])
        if not periods:
            raise GdanskWasteApiError("No schedule periods returned for Gdansk")
        return max(periods, key=lambda item: str(item.get("startDate", "")))

    async def async_get_streets_for_town(
        self,
        town_id: str,
        period_id: str,
    ) -> list[dict[str, Any]]:
        data = await self._post(
            "streetsForTown",
            {"townId": town_id, "periodId": period_id},
        )
        streets = data.get("streets", [])
        if not isinstance(streets, list):
            raise GdanskWasteApiError("Invalid street list returned by the API")
        return streets

    async def async_get_street_details(
        self,
        *,
        choosed_street_ids: str,
        house_number: str,
        town_id: str,
        street_name: str,
        schedule_period_id: str,
        group_id: str,
    ) -> dict[str, Any]:
        return await self._post(
            "streets",
            {
                "choosedStreetIds": choosed_street_ids,
                "number": normalize_house_number(house_number),
                "townId": town_id,
                "streetName": street_name,
                "schedulePeriodId": schedule_period_id,
                "groupId": group_id,
            },
        )

    async def async_resolve_address_candidates(
        self,
        *,
        street: str,
        house_number: str,
        preferred_group: str | None = None,
        preferred_street_id: str | None = None,
    ) -> list[ResolvedAddress]:
        town = await self.async_get_town()
        town_id = str(town["id"])
        town_name = str(town["name"])

        period = await self.async_get_current_period()
        period_id = str(period["id"])

        streets = await self.async_get_streets_for_town(town_id, period_id)
        matching_streets = self._find_matching_streets(streets, street)
        if not matching_streets:
            raise GdanskWasteAddressNotFoundError(
                f"Street '{street}' was not found in Gdansk"
            )

        api_street_name = str(matching_streets[0]["name"])
        choosed_street_ids = self._merge_choosed_street_ids(matching_streets)
        initial_result = await self.async_get_street_details(
            choosed_street_ids=choosed_street_ids,
            house_number=house_number,
            town_id=town_id,
            street_name=api_street_name,
            schedule_period_id=period_id,
            group_id="1",
        )

        groups = initial_result.get("groups", {}).get("items", [])
        candidates: list[ResolvedAddress] = []
        if groups:
            group_id = str(initial_result.get("groups", {}).get("groupId") or "g1")
            for group in groups:
                group_name = str(group.get("name", ""))
                group_result = await self.async_get_street_details(
                    choosed_street_ids=str(group.get("choosedStreetIds", "")),
                    house_number=house_number,
                    town_id=town_id,
                    street_name=str(group.get("streetName") or api_street_name),
                    schedule_period_id=period_id,
                    group_id=group_id,
                )
                candidates.extend(
                    self._parse_resolved_addresses(
                        group_result,
                        town_id=town_id,
                        town_name=town_name,
                        house_number=house_number,
                        schedule_period_id=period_id,
                        fallback_group_name=group_name,
                    )
                )
        else:
            candidates.extend(
                self._parse_resolved_addresses(
                    initial_result,
                    town_id=town_id,
                    town_name=town_name,
                    house_number=house_number,
                    schedule_period_id=period_id,
                )
            )

        deduplicated = self._deduplicate_candidates(candidates)
        if not deduplicated:
            raise GdanskWasteAddressNotFoundError(
                f"No address variants matched '{street} {house_number}'"
            )

        return sorted(
            deduplicated,
            key=lambda candidate: self._candidate_sort_key(
                candidate,
                preferred_group=preferred_group,
                preferred_street_id=preferred_street_id,
            ),
        )

    async def async_select_address(
        self,
        *,
        street: str,
        house_number: str,
        preferred_group: str | None = None,
        preferred_street_id: str | None = None,
    ) -> ResolvedAddress:
        return (
            await self.async_resolve_address_candidates(
                street=street,
                house_number=house_number,
                preferred_group=preferred_group,
                preferred_street_id=preferred_street_id,
            )
        )[0]

    async def async_fetch_schedule(self, address: ResolvedAddress) -> ScheduleData:
        data = await self._post(
            "schedules",
            {
                "number": normalize_house_number(address.house_number),
                "streetId": address.street_id,
                "townId": address.town_id,
                "streetName": address.street_name,
                "schedulePeriodId": address.schedule_period_id,
                "lng": "pl",
            },
        )

        descriptions = data.get("scheduleDescription", [])
        schedules = data.get("schedules", [])
        if not descriptions or not schedules:
            raise GdanskWasteNoScheduleError(
                f"No schedule was returned for {address.label}"
            )

        description_by_id = {
            str(description["id"]): description for description in descriptions
        }
        events: list[WasteEvent] = []

        for schedule_item in schedules:
            description = description_by_id.get(str(schedule_item.get("scheduleDescriptionId")))
            if not description:
                continue

            waste_type = str(description.get("name", "")).strip()
            if not waste_type or normalize_text(waste_type) in IGNORED_SCHEDULE_TYPES:
                continue
            if str(description.get("doNotShowDates", "0")) == "1":
                continue

            year = int(schedule_item.get("year"))
            month = int(schedule_item.get("month"))
            order = int(description.get("order") or 999)

            for raw_day in str(schedule_item.get("days", "")).split(";"):
                if not raw_day.strip():
                    continue

                try:
                    collection_date = date(year, month, int(raw_day))
                except ValueError:
                    _LOGGER.debug("Skipping invalid date entry: %s", schedule_item)
                    continue

                events.append(
                    WasteEvent(
                        collection_date=collection_date,
                        waste_type=waste_type,
                        color=str(description.get("color") or "") or None,
                        description=str(description.get("description") or "") or None,
                        order=order,
                    )
                )

        events.sort(key=lambda event: (event.collection_date, event.order, event.waste_type))
        if not events:
            raise GdanskWasteNoScheduleError(
                f"The API returned only non-pickup data for {address.label}"
            )

        group_name = str(data.get("groupname") or address.group_name)
        group_description = str(data.get("groupdescription") or address.group_description)
        schedule_period = data.get("schedulePeriod", {})

        return ScheduleData(
            address=replace(
                address,
                group_name=group_name,
                group_description=group_description,
            ),
            events=events,
            group_name=group_name,
            group_description=group_description,
            period_start=schedule_period.get("startDate"),
            period_end=schedule_period.get("endDate"),
        )

    def _find_matching_streets(
        self,
        streets: list[dict[str, Any]],
        requested_street: str,
    ) -> list[dict[str, Any]]:
        normalized_requested = normalize_text(requested_street)
        exact_matches = [
            street
            for street in streets
            if normalize_text(str(street.get("name", ""))) == normalized_requested
        ]
        if exact_matches:
            return exact_matches

        return [
            street
            for street in streets
            if normalized_requested
            and normalized_requested in normalize_text(str(street.get("name", "")))
        ]

    def _merge_choosed_street_ids(self, streets: list[dict[str, Any]]) -> str:
        identifiers: list[str] = []
        for street in streets:
            raw_ids = street.get("choosedStreetIds")
            if raw_ids in (None, "", []):
                continue
            identifiers.extend(
                part.strip()
                for part in str(raw_ids).split(",")
                if part.strip()
            )
        return ",".join(dict.fromkeys(identifiers))

    def _parse_resolved_addresses(
        self,
        details: dict[str, Any],
        *,
        town_id: str,
        town_name: str,
        house_number: str,
        schedule_period_id: str,
        fallback_group_name: str = "",
    ) -> list[ResolvedAddress]:
        resolved: list[ResolvedAddress] = []
        for street in details.get("streets", []):
            resolved.append(
                ResolvedAddress(
                    street_id=str(street.get("id", "")),
                    street_name=str(street.get("name", "")),
                    house_number=normalize_house_number(house_number),
                    town_id=town_id,
                    town_name=town_name,
                    schedule_period_id=schedule_period_id,
                    group_name=str(street.get("schedulegroup") or fallback_group_name),
                    group_description=str(street.get("schedulegroup") or fallback_group_name),
                    district=str(street.get("region") or street.get("townDistrict") or ""),
                    sides=str(street.get("sides") or ""),
                    stamp=str(street.get("stamp") or ""),
                )
            )
        return resolved

    def _deduplicate_candidates(
        self,
        candidates: list[ResolvedAddress],
    ) -> list[ResolvedAddress]:
        unique: dict[str, ResolvedAddress] = {}
        for candidate in candidates:
            unique[candidate.unique_id] = candidate
        return list(unique.values())

    def _candidate_sort_key(
        self,
        candidate: ResolvedAddress,
        *,
        preferred_group: str | None,
        preferred_street_id: str | None,
    ) -> tuple[int, int, str]:
        preferred_score = 0
        if preferred_street_id and candidate.street_id == preferred_street_id:
            preferred_score -= 100
        if preferred_group and normalize_text(candidate.group_name) == normalize_text(preferred_group):
            preferred_score -= 20
        if candidate.sides:
            preferred_score -= 1

        group_score = 0 if candidate.group_name else 1
        return (preferred_score, group_score, candidate.label)
