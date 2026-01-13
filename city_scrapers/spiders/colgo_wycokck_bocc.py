from datetime import date, datetime

import scrapy
from city_scrapers_core.constants import BOARD
from city_scrapers_core.items import Meeting
from city_scrapers_core.spiders import CityScrapersSpider


class ColgoWycokckBoccSpider(CityScrapersSpider):
    name = "colgo_wycokck_bocc"
    agency = "Board of Commissioners - Unified Government of Wyandotte County and Kansas City"  # noqa
    timezone = "America/Chicago"
    api_base_url = "https://wycokck.api.civicclerk.com"
    portal_base_url = "https://wycokck.portal.civicclerk.com"
    # Category IDs for Board of Commissioners meetings
    # 35 = Board of Commissioners, 36 = Board of Commissioners Special Meeting
    category_filter = "categoryId+in+(35,36)"

    def start_requests(self):
        """Generate API requests for past and upcoming events."""
        today = date.today()
        today_str = today.isoformat()
        urls = [
            # Past events up to today
            f"{self.api_base_url}/v1/Events?$filter=startDateTime+lt+{today_str}+and+{self.category_filter}&$orderby=startDateTime+desc,+eventName+desc",  # noqa
            # Upcoming events (today and future)
            f"{self.api_base_url}/v1/Events?$filter=startDateTime+ge+{today_str}+and+{self.category_filter}&$orderby=startDateTime+asc,+eventName+asc",  # noqa
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
                classification=BOARD,
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
        return raw_event.get("eventName") or "Board of Commissioners"

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

        location_name = "Unified Government of Wyandotte County/Kansas City"
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
            address = "701 N 7th Street, Kansas City, KS 66101"

        return {
            "name": location_name,
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
