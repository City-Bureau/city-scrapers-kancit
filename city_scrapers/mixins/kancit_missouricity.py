import re
from collections import defaultdict
from datetime import datetime
from urllib.parse import urlencode

import scrapy
from city_scrapers_core.constants import (
    BOARD,
    CITY_COUNCIL,
    COMMISSION,
    COMMITTEE,
    NOT_CLASSIFIED,
)
from city_scrapers_core.items import Meeting
from city_scrapers_core.spiders import LegistarSpider


class KancitMissouricityMixinMeta(type):
    """
    Metaclass that enforces the implementation of required static
    variables in child classes that inherit from KancitMissouricityMixin.
    """

    def __init__(cls, name, bases, dct):
        required_static_vars = ["agency", "name", "agency_filter"]
        missing_vars = [var for var in required_static_vars if var not in dct]

        if missing_vars:
            missing_vars_str = ", ".join(missing_vars)
            raise NotImplementedError(
                f"{name} must define the following static variable(s): "
                f"{missing_vars_str}."
            )

        super().__init__(name, bases, dct)


class KancitMissouricityMixin(LegistarSpider, metaclass=KancitMissouricityMixinMeta):
    """
    Mixin for scraping Kansas City Missouri Legistar calendar.

    To use this mixin, create a child spider class that inherits from
    KancitMissouricityMixin and define the required static variables:
    - agency: The agency name for display
    - name: The spider name (slug)
    - agency_filter: The exact meeting title to filter for
    """

    timezone = "America/Chicago"
    start_urls = ["https://clerk.kcmo.gov/Calendar.aspx"]

    # Legistar calendar requires bypassing robots.txt
    custom_settings = {
        "ROBOTSTXT_OBEY": False,
    }

    # Start year for scraping historical data
    START_YEAR = 2020

    # Required attributes to be set by child classes
    name = None
    agency = None
    agency_filter = None

    # Optional: classification override (default is auto-detect)
    classification = None

    def _get_max_year_from_dropdown(self, response):
        """
        Extract the maximum year from the year dropdown on the page.
        Returns the highest numeric year found in the dropdown.
        """
        # Look for year options in the dropdown (e.g., lstYears)
        year_options = response.css(
            "#ctl00_ContentPlaceHolder1_lstYears_DropDown .rcbList li::text"
        ).getall()

        # If dropdown not found in initial HTML, try alternative selectors
        if not year_options:
            year_options = response.css("select[id*='lstYears'] option::text").getall()

        # Extract numeric years only
        numeric_years = []
        for option in year_options:
            option = option.strip()
            if option.isdigit():
                numeric_years.append(int(option))

        # Return max year if found, otherwise fall back to current year + 1
        if numeric_years:
            return max(numeric_years)
        return datetime.now().year + 1

    def parse(self, response):
        """
        Override parent to request data for each year from START_YEAR to max year.
        Skip initial page processing to avoid duplicates from upcoming section.
        Max year is dynamically extracted from the page's year dropdown.
        """
        secrets = self._parse_secrets(response)

        # Get max year dynamically from the dropdown
        max_year = self._get_max_year_from_dropdown(response)

        # Request all years from START_YEAR to max year (inclusive)
        for year in range(self.START_YEAR, max_year + 1):
            yield scrapy.Request(
                response.url,
                method="POST",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                body=urlencode(
                    {
                        **secrets,
                        "__EVENTTARGET": "ctl00$ContentPlaceHolder1$lstYears",
                        "ctl00_ContentPlaceHolder1_lstYears_ClientState": (
                            f'{{"value":"{year}"}}'
                        ),
                    }
                ),
                callback=self._parse_legistar_events_page,
                dont_filter=True,
            )

    def _parse_legistar_events(self, response):
        """
        Override parent to parse events only from the calendar table.
        Skip gridUpcomingMeetings to avoid duplicates.
        Uses meeting name URL + date/time for deduplication.
        """
        events = []

        # Only process the calendar table, skip upcoming meetings table
        events_table = response.css("table.rgMasterTable[id*='gridCalendar']")
        if not events_table:
            return events
        events_table = events_table[0]

        headers = []
        for header in events_table.css("th[class^='rgHeader']"):
            header_text = (
                " ".join(header.css("*::text").extract()).replace("&nbsp;", " ").strip()
            )
            header_inputs = header.css("input")
            if header_text:
                headers.append(header_text)
            elif len(header_inputs) > 0:
                headers.append(header_inputs[0].attrib["value"])
            else:
                img_els = header.css("img")
                if img_els:
                    headers.append(img_els[0].attrib.get("alt", ""))
                else:
                    headers.append("")

        for row in events_table.css("tr.rgRow, tr.rgAltRow"):
            try:
                data = defaultdict(lambda: None)
                for header, field in zip(headers, row.css("td")):
                    field_text = (
                        " ".join(field.css("*::text").extract())
                        .replace("&nbsp;", " ")
                        .strip()
                    )
                    url = None
                    if len(field.css("a")) > 0:
                        link_el = field.css("a")[0]
                        if "onclick" in link_el.attrib and link_el.attrib[
                            "onclick"
                        ].startswith(("radopen('", "window.open", "OpenTelerikWindow")):
                            url = response.urljoin(
                                link_el.attrib["onclick"].split("'")[1]
                            )
                        elif "href" in link_el.attrib:
                            url = response.urljoin(link_el.attrib["href"])
                    if url:
                        if header in ["", "ics"] and "View.ashx?M=IC" in url:
                            header = "iCalendar"
                            value = {"url": url}
                        else:
                            value = {"label": field_text, "url": url}
                    else:
                        value = field_text

                    data[header] = value

                # Use name URL + date + time as unique key for deduplication
                name_url = ""
                if isinstance(data.get("Name"), dict):
                    name_url = data["Name"].get("url", "")
                meeting_date = data.get("Meeting Date", "")
                meeting_time = data.get("Meeting Time", "")
                unique_key = f"{name_url}|{meeting_date}|{meeting_time}"

                if unique_key in self._scraped_urls:
                    continue
                self._scraped_urls.add(unique_key)
                events.append(dict(data))
            except Exception:
                pass

        return events

    def _get_event_title(self, event):
        """Extract title from event data."""
        if isinstance(event.get("Name"), dict):
            return event["Name"].get("label", "")
        return event.get("Name", "")

    def _is_agency_match(self, event):
        """Check if this event matches the agency filter."""
        title = self._get_event_title(event)
        return title == self.agency_filter

    def parse_legistar(self, events):
        """Parse events from Legistar calendar, filtering by agency."""
        for event in events:
            # Filter events by agency
            if not self._is_agency_match(event):
                continue

            start = self.legistar_start(event)
            if not start:
                continue

            meeting = Meeting(
                title=self._get_event_title(event),
                description="",
                classification=self._parse_classification(event),
                start=start,
                end=None,
                all_day=False,
                time_notes="",
                location=self._parse_location(event),
                links=self._parse_links(event),
                source=self.legistar_source(event),
            )

            meeting["status"] = self._get_status(meeting)
            meeting["id"] = self._get_id(meeting)

            yield meeting

    def _parse_classification(self, item):
        """Parse classification from meeting name or use override."""
        if self.classification:
            return self.classification

        name = self._get_event_title(item).lower()

        if "council" in name:
            return CITY_COUNCIL
        if "committee" in name:
            return COMMITTEE
        if "commission" in name:
            return COMMISSION
        if "board" in name:
            return BOARD
        return NOT_CLASSIFIED

    def _parse_location(self, item):
        """Parse location from event data."""
        location = {"name": "", "address": ""}
        meeting_location = item.get("Meeting Location", "")

        if isinstance(meeting_location, dict):
            meeting_location = meeting_location.get("label", "")

        if not meeting_location:
            return location

        meeting_location = meeting_location.strip()

        # Check for virtual meeting indicators
        if "zoom" in meeting_location.lower() or "virtual" in meeting_location.lower():
            location["name"] = "Virtual Meeting"
            location["address"] = ""
            return location

        # Try to parse address with ZIP code pattern
        zip_match = re.search(r"(\d{5}(-\d{4})?)", meeting_location)
        if zip_match:
            location["address"] = meeting_location
        else:
            location["name"] = meeting_location

        return location

    def _parse_links(self, item):
        """Parse links from event data."""
        links = []

        # Agenda link
        agenda = item.get("Agenda")
        if isinstance(agenda, dict) and agenda.get("url"):
            links.append(
                {"href": agenda["url"], "title": agenda.get("label", "Agenda")}
            )

        # Minutes link
        minutes = item.get("Minutes")
        if isinstance(minutes, dict) and minutes.get("url"):
            links.append(
                {"href": minutes["url"], "title": minutes.get("label", "Minutes")}
            )

        # iCalendar link
        ical = item.get("iCalendar")
        if isinstance(ical, dict) and ical.get("url"):
            links.append({"href": ical["url"], "title": "iCalendar"})

        # Video link
        video = item.get("Video")
        if isinstance(video, dict) and video.get("url"):
            label = video.get("label", "Video")
            if (
                label
                and "not" not in label.lower()
                and "available" not in label.lower()
            ):
                links.append({"href": video["url"], "title": label})

        # Audio link
        audio = item.get("Audio")
        if isinstance(audio, dict) and audio.get("url"):
            label = audio.get("label", "Audio")
            if (
                label
                and "not" not in label.lower()
                and "available" not in label.lower()
            ):
                links.append({"href": audio["url"], "title": label})

        return links
