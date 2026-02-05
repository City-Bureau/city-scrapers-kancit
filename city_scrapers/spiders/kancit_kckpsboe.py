from datetime import date, datetime, timedelta
from urllib.parse import urlencode

import scrapy
from city_scrapers_core.constants import BOARD, COMMITTEE
from city_scrapers_core.items import Meeting
from city_scrapers_core.spiders import CityScrapersSpider


class KancitKckpsBoeSpider(CityScrapersSpider):
    name = "kancit_kckps_boe"
    agency = "Kansas City Kansas Public Schools Board of Education"
    timezone = "America/Chicago"
    base_url = "https://kckps.community.highbond.com"
    meetings_api_url = f"{base_url}/Services/MeetingsService.svc/meetings"
    link_url = f"{base_url}/Portal/MeetingInformation.aspx"
    start_urls = f"{base_url}/Portal/MeetingTypeList.aspx"
    custom_settings = {"ROBOTSTXT_OBEY": False}

    def start_requests(self):
        """
        Example endpoint:
        /Services/MeetingsService.svc/meetings?from=2025-02-01&to=9999-12-31&loadall=false&_=...
        """
        # Fetch all meetings from July 2014 through +1 year
        from_date = "2014-07-01"
        to_date = (date.today() + timedelta(days=365)).isoformat()

        params = {
            "from": from_date,
            "to": to_date,
            "loadall": "false",
            "_": int(datetime.utcnow().timestamp() * 1000),  # cache buster
        }
        url = f"{self.meetings_api_url}?{urlencode(params)}"
        yield scrapy.Request(url=url, callback=self.parse)

    def parse(self, response):
        """
        `parse` should always `yield` Meeting items.

        Change the `_parse_title`, `_parse_start`, etc methods to fit your scraping
        needs.
        """
        data = response.json()
        for item in data:
            yield self._create_meeting(item)

    def _create_meeting(self, item):
        """Create a Meeting item with parsed data."""
        meeting = Meeting(
            title=self._parse_title(item),
            description=self._parse_description(item),
            classification=self._parse_classification(item),
            start=self._parse_start(item),
            end=self._parse_end(item),
            all_day=self._parse_all_day(item),
            time_notes=self._parse_time_notes(item),
            location=self._parse_location(item),
            links=self._parse_links(item),
            source=self.start_urls,
        )

        meeting["status"] = self._get_status(meeting)
        meeting["id"] = self._get_id(meeting)

        return meeting

    def _parse_title(self, item):
        """Parse or generate meeting title."""
        title = item.get("Name", "").strip() or item.get("MeetingTypeName", "").strip()

        import re

        # Remove time information first
        time_patterns = [
            r"\s+at\s+\d{1,2}:\d{2}\s*(?:a\.?m\.?|p\.?m\.?)",  # "at 4:00 PM"
            r"\s+\d{1,2}:\d{2}\s*(?:a\.?m\.?|p\.?m\.?)",  # "4:00 PM"
            r"\s+\d{1,2}\s*(?:a\.?m\.?|p\.?m\.?)",  # "9 AM"
        ]

        for pattern in time_patterns:
            title = re.sub(pattern, "", title, flags=re.IGNORECASE)

        # Remove date from title - handle multiple patterns

        # Pattern 1: Everything after the last dash
        if " - " in title:
            parts = title.rsplit(" - ", 1)
            title = parts[0].strip()

        # Pattern 2: Remove specific date patterns
        date_patterns = [
            r"\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4}$",  # "April 17, 2025" # noqa
            r"\s+\d{1,2}/\d{1,2}/\d{4}$",  # "02/21/2025"
            r"\s+\d{4}$",  # "2025" at end
            r"\s+\d{1,2},\s+\d{4}$",  # "21, 2025"
        ]

        for pattern in date_patterns:
            title = re.sub(pattern, "", title, flags=re.IGNORECASE)

        return title.strip()

    def _parse_description(self, item):
        """Parse or generate meeting description."""
        return ""

    def _parse_classification(self, item):
        """Parse or generate classification from allowed options."""
        meeting_title = (
            item.get("Name", "").strip() or item.get("MeetingTypeName", "").strip()
        )

        # Check both title and meeting type for classification
        if "committee" in meeting_title.lower():
            return COMMITTEE
        return BOARD

    def _parse_start(self, item):
        """Parse start datetime as a naive datetime object."""
        dt_str = item.get("MeetingDateTime", "")
        if dt_str:
            return datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
        return None

    def _parse_end(self, item):
        """Parse end datetime as a naive datetime object. Added by pipeline if None"""
        return None

    def _parse_time_notes(self, item):
        """Parse any additional notes on the timing of the meeting"""
        meeting_title = (
            item.get("Name", "").strip() or item.get("MeetingTypeName", "").strip()
        )

        notes = ["Please check meeting attachments for accurate time and location."]

        # Add virtual meeting note for Finance Committee meetings and Special meetings
        if (
            "Finance Committee Meeting" in meeting_title
            or "Special Meeting Agenda" in meeting_title
        ):
            notes.append(
                "You are invited to join virtually. Please check the attachments for the virtual link."  # noqa
            )

        return " ".join(notes)

    def _parse_all_day(self, item):
        """Parse or generate all-day status. Defaults to False."""
        return False

    def _parse_location(self, item):
        """Parse or generate location."""
        meeting_title = (
            item.get("Name", "").strip() or item.get("MeetingTypeName", "").strip()
        )

        CENTRAL_OFFICE = (
            "Kansas City, Kansas Public Schools - Central Office and Training Center"
        )

        LOCATION_MAP = [
            (
                "Board Retreat",
                None,
                "10 E Cambridge Circle Drive #300, Kansas City, Kansas 66103",
                "McAnany Van Cleave & Phillips Law Firm",
            ),
            ("Academic Committee Meeting", None, "2010 N. 59th Street", CENTRAL_OFFICE),
            (
                "Finance Committee Meeting",
                None,
                "",
                "Kansas City, Kansas Public Schools",
            ),
            (
                "Facilities",
                "Committee Meeting",
                "2010 N. 59th Street, Third Floor East Wing",
                CENTRAL_OFFICE,
            ),
            (
                "Boundary",
                "Committee Meeting",
                "2010 N. 59th Street, Third Floor East Wing",
                CENTRAL_OFFICE,
            ),
            (
                "Special Board Meeting Agenda",
                None,
                "2010 N. 59th Street, Third Floor Board Room",
                CENTRAL_OFFICE,
            ),
            ("Special", None, "2010 N. 59th Street", CENTRAL_OFFICE),
            (
                "Regular Meeting Agenda",
                None,
                "2010 N. 59th Street, Third Floor Board Room",
                CENTRAL_OFFICE,
            ),
            (
                "Regular Board Meeting Agenda",
                None,
                "2010 N. 59th Street, Third Floor Board Room",
                CENTRAL_OFFICE,
            ),
        ]

        for keyword, extra, address, name in LOCATION_MAP:
            if keyword in meeting_title:
                if extra is None or extra in meeting_title:
                    return {"address": address, "name": name}

        return {"address": "", "name": item.get("MeetingLocation", "")}

    def _parse_links(self, item):
        """Parse or generate links."""
        links = []
        meeting_id = item.get("Id")
        if meeting_id:
            links.append(
                {
                    "href": f"{self.link_url}?Org=Cal&Id={meeting_id}",
                    "title": "Meeting Details",
                }
            )
        return links
