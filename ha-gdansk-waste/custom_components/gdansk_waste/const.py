from __future__ import annotations

from datetime import timedelta

from homeassistant.const import Platform

DOMAIN = "gdansk_waste"
PLATFORMS: tuple[Platform, ...] = (Platform.SENSOR,)

COMMUNITY_ID = "108"
API_BASE_URL = "https://pluginecoapi.ecoharmonogram.pl/v1"
REQUEST_TIMEOUT = 20
DEFAULT_SCAN_INTERVAL = timedelta(hours=12)
UPCOMING_LIMIT = 10

CONF_CANDIDATE = "candidate"
CONF_DISTRICT = "district"
CONF_GROUP_DESCRIPTION = "group_description"
CONF_GROUP_NAME = "group_name"
CONF_HOUSE_NUMBER = "house_number"
CONF_SCHEDULE_PERIOD_ID = "schedule_period_id"
CONF_SIDES = "sides"
CONF_STAMP = "stamp"
CONF_STREET_ID = "street_id"
CONF_STREET_NAME = "street_name"
CONF_TOWN_ID = "town_id"
CONF_TOWN_NAME = "town_name"

DEFAULT_NAME = "Odbiory odpadow"

IGNORED_SCHEDULE_TYPES = {"TERMINY PŁATNOŚCI"}
