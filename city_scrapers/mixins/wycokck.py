"""
Wyandotte County/Kansas City (WYCOKCK) Mixin for scrapers using CivicClerk API.

This mixin scrapes meeting data from the Unified Government of Wyandotte County
and Kansas City via their CivicClerk API.

API Base URL:
    https://wycokck.api.civicclerk.com/v1/Events

Portal Base URL:
    https://wycokck.portal.civicclerk.com

Required class variables (enforced by __init_subclass__):
    name (str): Spider name/slug (e.g., "kancit_full_commission")
    agency (str): Full agency name (e.g., "Full Commission")
    category_id (int): Category ID from CivicClerk API (e.g., 31)
    classification: Meeting classification constant (e.g., COMMISSION)

Example:
    class KancitFullCommissionSpider(WycokckMixin):
        name = "kancit_full_commission"
        agency = "Full Commission"
        category_id = 31
        classification = COMMISSION
"""

from datetime import date, datetime

import scrapy
from city_scrapers_core.items import Meeting
from city_scrapers_core.spiders import CityScrapersSpider


class WycokckMixin(CityScrapersSpider):
    """
    Base mixin class for scraping Wyandotte County/Kansas City meetings.

    Uses CivicClerk API to extract meeting data.
    """

    # Required to be overridden (enforced by __init_subclass__)
    name = None
    agency = None
    category_id = None
    classification = None

    _required_vars = [
        "name",
        "agency",
        "category_id",
        "classification",
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

    def start_requests(self):
        """Generate API requests for past and upcoming events."""
        today = date.today()
        today_str = today.isoformat()
        category_filter = f"categoryId+eq+{self.category_id}"

        urls = [
            # Past events up to today
            f"{self.api_base_url}/v1/Events?$filter=startDateTime+lt+{today_str}+and+{category_filter}&$orderby=startDateTime+desc,+eventName+desc",  # noqa
            # Upcoming events (today and future)
            f"{self.api_base_url}/v1/Events?$filter=startDateTime+ge+{today_str}+and+{category_filter}&$orderby=startDateTime+asc,+eventName+asc",  # noqa
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
            meeting = Meeting(
                title=self._parse_title(raw_event),
                description=raw_event.get("eventDescription") or "",
                classification=self.classification,
                start=self._parse_start(raw_event),
                end=self._parse_end(raw_event),
                all_day=False,
                time_notes="",
                location=self._parse_location(raw_event),
                links=self._parse_links(raw_event),
                source=f"{self.portal_base_url}/event/{raw_event.get('id')}",
            )

            meeting["status"] = self._get_status(meeting)
            meeting["id"] = self._get_id(meeting)

            yield meeting

        # Handle pagination
        next_link = data.get("@odata.nextLink")
        if next_link:
            yield scrapy.Request(next_link, callback=self.parse)

    def _parse_title(self, raw_event):
        """Parse or generate meeting title."""
        return raw_event.get("eventName") or self.agency

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
