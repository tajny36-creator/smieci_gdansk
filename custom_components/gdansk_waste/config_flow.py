from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow
from homeassistant.const import CONF_NAME, CONF_STREET
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .api import (
    GdanskWasteAddressNotFoundError,
    GdanskWasteApiClient,
    GdanskWasteApiError,
    GdanskWasteConnectionError,
    GdanskWasteNoScheduleError,
    ResolvedAddress,
)
from .const import CONF_CANDIDATE, CONF_HOUSE_NUMBER, DEFAULT_NAME, DOMAIN

_LOGGER = logging.getLogger(__name__)


class GdanskWasteConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the config flow for Gdansk waste collection."""

    VERSION = 1

    def __init__(self) -> None:
        self._candidates: dict[str, ResolvedAddress] = {}
        self._user_input: dict[str, str] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            cleaned_input = {
                CONF_NAME: str(user_input.get(CONF_NAME, "")).strip(),
                CONF_STREET: str(user_input[CONF_STREET]).strip(),
                CONF_HOUSE_NUMBER: str(user_input[CONF_HOUSE_NUMBER]).strip(),
            }
            client = GdanskWasteApiClient(aiohttp_client.async_get_clientsession(self.hass))

            try:
                candidates = await client.async_resolve_address_candidates(
                    street=cleaned_input[CONF_STREET],
                    house_number=cleaned_input[CONF_HOUSE_NUMBER],
                )
            except GdanskWasteConnectionError:
                errors["base"] = "cannot_connect"
            except GdanskWasteAddressNotFoundError:
                errors["base"] = "address_not_found"
            except GdanskWasteNoScheduleError:
                errors["base"] = "no_schedule"
            except GdanskWasteApiError:
                errors["base"] = "unknown"
            except Exception:
                _LOGGER.exception("Unexpected error during config flow")
                errors["base"] = "unknown"
            else:
                self._user_input = cleaned_input
                if len(candidates) == 1:
                    result = await self._async_try_create_entry(candidates[0], errors)
                    if result is not None:
                        return result

                self._candidates = {candidate.unique_id: candidate for candidate in candidates}
                return await self.async_step_select_address()

        return self.async_show_form(
            step_id="user",
            data_schema=self._build_user_schema(user_input),
            errors=errors,
        )

    async def async_step_select_address(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            candidate = self._candidates.get(str(user_input[CONF_CANDIDATE]))
            if candidate is None:
                errors["base"] = "address_not_found"
            else:
                result = await self._async_try_create_entry(candidate, errors)
                if result is not None:
                    return result

        return self.async_show_form(
            step_id="select_address",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_CANDIDATE): SelectSelector(
                        SelectSelectorConfig(
                            options=[
                                {"value": candidate_id, "label": candidate.label}
                                for candidate_id, candidate in self._candidates.items()
                            ],
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            ),
            description_placeholders={
                "address": (
                    f"{self._user_input.get(CONF_STREET, '')} "
                    f"{self._user_input.get(CONF_HOUSE_NUMBER, '')}"
                ).strip()
            },
            errors=errors,
        )

    async def _async_create_entry_from_candidate(
        self,
        candidate: ResolvedAddress,
    ) -> FlowResult:
        await self.async_set_unique_id(candidate.unique_id)
        self._abort_if_unique_id_configured()

        client = GdanskWasteApiClient(aiohttp_client.async_get_clientsession(self.hass))
        schedule = await client.async_fetch_schedule(candidate)

        name = self._user_input.get(CONF_NAME) or schedule.address.label or DEFAULT_NAME
        return self.async_create_entry(
            title=name,
            data=schedule.address.as_entry_data(name),
        )

    async def _async_try_create_entry(
        self,
        candidate: ResolvedAddress,
        errors: dict[str, str],
    ) -> FlowResult | None:
        try:
            return await self._async_create_entry_from_candidate(candidate)
        except GdanskWasteConnectionError:
            errors["base"] = "cannot_connect"
        except GdanskWasteNoScheduleError:
            errors["base"] = "no_schedule"
        except GdanskWasteApiError:
            errors["base"] = "unknown"
        return None

    @callback
    def _build_user_schema(
        self,
        user_input: dict[str, Any] | None,
    ) -> vol.Schema:
        user_input = user_input or {}
        return vol.Schema(
            {
                vol.Optional(
                    CONF_NAME,
                    default=str(user_input.get(CONF_NAME, "")),
                ): str,
                vol.Required(
                    CONF_STREET,
                    default=str(user_input.get(CONF_STREET, "")),
                ): str,
                vol.Required(
                    CONF_HOUSE_NUMBER,
                    default=str(user_input.get(CONF_HOUSE_NUMBER, "")),
                ): str,
            }
        )
