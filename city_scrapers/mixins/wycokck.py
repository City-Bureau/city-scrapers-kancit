"""
CivicClerk API Mixin for Wyandotte County/Kansas City scrapers.

This mixin scrapes meeting data from the Unified Government of Wyandotte County
and Kansas City via their CivicClerk API.

API Base URL:
    https://wycokck.api.civicclerk.com/v1/Events

Portal Base URL:
    https://wycokck.portal.civicclerk.com

Required class variables (enforced by __init_subclass__):
    name (str): Spider name/slug (e.g., "kancit_board_commissioners")
    agency (str): Full agency name
    category_ids (list[int]): Category IDs from CivicClerk API (e.g., [31, 33, 35])

Example:
    class KancitBoardCommissionersSpider(CivicClerkMixin):
        name = "kancit_board_commissioners"
        agency = "Board of Commissioners"
        category_ids = [31, 33, 35, 36, 37]
"""

from datetime import date, datetime

import scrapy
from city_scrapers_core.constants import BOARD, COMMISSION, COMMITTEE, NOT_CLASSIFIED
from city_scrapers_core.items import Meeting
from city_scrapers_core.spiders import CityScrapersSpider
from dateutil.relativedelta import relativedelta


class CivicClerkMixin(CityScrapersSpider):
    """
    Base mixin class for scraping Wyandotte County/Kansas City meetings.

    Uses CivicClerk API to extract meeting data.
    """

    # Required to be overridden (enforced by __init_subclass__)
    name = None
    agency = None
    category_ids = None

    _required_vars = [
        "name",
        "agency",
        "category_ids",
    ]

    def __init_subclass__(cls, **kwargs):
        """Enforces the implementation of required class variables in subclasses."""
        super().__init_subclass__(**kwargs)

        missing_vars = []
        for var in cls._required_vars:
            value = getattr(cls, var, None)
            if value is None:
                missing_vars.append(var)

        if missing_vars:
            missing_vars_str = ", ".join(missing_vars)
            raise NotImplementedError(
                f"{cls.__name__} must define the following class variable(s): "
                f"{missing_vars_str}."
            )

    # Configuration
    timezone = "America/Chicago"
    api_base_url = "https://wycokck.api.civicclerk.com"
    portal_base_url = "https://wycokck.portal.civicclerk.com"

    # Default location - consistent across all WYCOKCK meetings
    location_name = "Unified Government of Wyandotte County/Kansas City"
    default_address = "701 N 7th Street, Kansas City, KS 66101"

    # Date range configuration (can be overridden by subclasses)
    # First meeting in CivicClerk API: 2015-05-04
    start_date_str = "2015-05-01"
    months_ahead = 3

    def start_requests(self):
        """Generate API requests for past and upcoming events."""
        today = date.today()
        start_date = date.fromisoformat(self.start_date_str)
        end_date = today + relativedelta(months=self.months_ahead)

        start_date_str = start_date.isoformat()
        end_date_str = end_date.isoformat()
        today_str = today.isoformat()

        ids_str = ",".join(str(c) for c in self.category_ids)
        category_filter = f"categoryId+in+({ids_str})"

        urls = [
            # Past events (from start_date to today)
            f"{self.api_base_url}/v1/Events?$filter=startDateTime+ge+{start_date_str}+and+startDateTime+lt+{today_str}+and+{category_filter}&$orderby=startDateTime+desc,+eventName+desc",  # noqa
            # Upcoming events (today to end_date)
            f"{self.api_base_url}/v1/Events?$filter=startDateTime+ge+{today_str}+and+startDateTime+le+{end_date_str}+and+{category_filter}&$orderby=startDateTime+asc,+eventName+asc",  # noqa
        ]
        for url in urls:
            yield scrapy.Request(url, callback=self.parse)

    def parse(self, response):
        """
        Parse JSON response from CivicClerk API and yield Meeting items.
        """
        data = response.json()
        events = data.get("value", [])

        for raw_event in events:
            event_id = raw_event.get("id")
            if not event_id:
                continue

            title = self._parse_title(raw_event)
            meeting = Meeting(
                title=title,
                description=raw_event.get("eventDescription") or "",
                classification=self._parse_classification(title),
                start=self._parse_start(raw_event),
                end=self._parse_end(raw_event),
                all_day=False,
                time_notes="",
                location=self._parse_location(raw_event),
                links=self._parse_links(raw_event),
                source=f"{self.portal_base_url}/event/{event_id}",
            )

            meeting["status"] = self._get_status(meeting)
            meeting["id"] = self._get_id(meeting)

            yield meeting

        # Handle pagination
        next_link = data.get("@odata.nextLink")
        if next_link:
            yield scrapy.Request(next_link, callback=self.parse)

    def _parse_classification(self, title):
        """
        Parse classification from meeting title.
        Derives classification based on keywords in the title.
        """
        title_lower = title.lower()
        if "committee" in title_lower:
            return COMMITTEE
        if "commission" in title_lower:
            return COMMISSION
        if "board" in title_lower:
            return BOARD
        return NOT_CLASSIFIED

    def _parse_title(self, raw_event):
        """Parse or generate meeting title, cleaning up empty parentheses."""
        title = raw_event.get("eventName") or self.agency
        # Remove empty parentheses left after cancelled/cancel removal
        title = title.replace("()", "").strip()
        return title

    def _parse_start(self, raw_event):
        """Parse start datetime as a naive datetime object."""
        start_str = raw_event.get("startDateTime")
        return self._parse_dt(start_str)

    def _parse_end(self, raw_event):
        """Parse end datetime as a naive datetime object. Added by pipeline if None"""
        end_str = raw_event.get("endDateTime")
        return self._parse_dt(end_str)

    def _parse_location(self, raw_event):
        """Parse or generate location."""
        event_location = raw_event.get("eventLocation") or {}

        address_parts = [
            event_location.get("address1") or "",
            event_location.get("address2") or "",
            ", ".join(
                part
                for part in [
                    event_location.get("city"),
                    event_location.get("state"),
                    event_location.get("zipCode"),
                ]
                if part
            ),
        ]
        address = " ".join(part for part in address_parts if part).strip()

        # Default address if none provided in the event
        if not address:
            address = self.default_address

        return {
            "name": self.location_name,
            "address": address,
        }

    def _parse_links(self, raw_event):
        """Parse or generate links."""
        event_id = raw_event.get("id")
        links = []
        for f in raw_event.get("publishedFiles", []):
            file_id = f.get("fileId")
            if not file_id or not event_id:
                continue
            links.append(
                {
                    "title": f.get("type") or "Document",
                    "href": f"{self.portal_base_url}/event/{event_id}/files/agenda/{file_id}",  # noqa
                }
            )
        return links

    def _parse_dt(self, dt_str):
        """Parse an ISO datetime string into a naive datetime object."""
        if not dt_str:
            return None
        # Handle ISO format like '2025-11-19T11:30:00Z'
        dt_str = dt_str.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(dt_str)
            # Return naive datetime (strip timezone)
            return dt.replace(tzinfo=None)
        except ValueError:
            return None
