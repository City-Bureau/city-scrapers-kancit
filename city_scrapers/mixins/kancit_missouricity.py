import re
from collections import defaultdict
from datetime import datetime
from urllib.parse import urlencode

import scrapy
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

    # Optional: hardcoded meeting location for agencies with known physical locations
    meeting_location = None

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

    def _get_location_text(self, event):
        """Extract raw location text from event for status detection."""
        meeting_location = event.get("Meeting Location", "")
        if isinstance(meeting_location, dict):
            return meeting_location.get("label", "")
        return meeting_location

    def parse_legistar(self, events):
        """Parse events from Legistar calendar, filtering by agency."""
        for event in events:
            # Filter events by agency
            if not self._is_agency_match(event):
                continue

            start = self.legistar_start(event)
            if not start:
                continue

            # Extract location string for status detection
            location_text = self._get_location_text(event)

            meeting = Meeting(
                title=self._get_event_title(event),
                description="",
                classification=self.classification,
                start=start,
                end=None,
                all_day=False,
                time_notes="",
                location=self._parse_location(event),
                links=self._parse_links(event),
                source=self.legistar_source(event),
            )

            meeting["status"] = self._get_status(meeting, text=location_text)
            meeting["id"] = self._get_id(meeting)

            yield meeting

    def _parse_location(self, item):
        """Parse location from event data."""
        location = {"name": "", "address": ""}
        meeting_location_str = item.get("Meeting Location", "")

        if isinstance(meeting_location_str, dict):
            meeting_location_str = meeting_location_str.get("label", "")

        if meeting_location_str:
            meeting_location_str = meeting_location_str.strip()

            # Check for virtual meeting indicators
            virtual_indicators = [
                "zoom",
                "virtual",
                "teams.microsoft.com",
                "webex",
                "gotomeeting",
                "meet.google.com",
            ]
            location_lower = meeting_location_str.lower()

            # Check if location contains virtual meeting indicators
            if any(indicator in location_lower for indicator in virtual_indicators):
                location["name"] = "Virtual Meeting"
                return location

            # Check if location is primarily a phone number
            if re.match(
                r"^\+?1?[\s-]?\d{3}[\s-]?\d{3}[\s-]?\d{4}", meeting_location_str
            ):
                location["name"] = "Virtual Meeting"
                return location

            # Clean up the location string
            cleaned_location = self._clean_location_string(meeting_location_str)

            # If event data has complete address with ZIP code, use it
            if cleaned_location:
                zip_match = re.search(r"(\d{5}(-\d{4})?)", cleaned_location)
                if zip_match:
                    location["address"] = cleaned_location
                    return location

        # Use hardcoded location if available (fallback for incomplete addresses)
        if self.meeting_location:
            return self.meeting_location

        # If no hardcoded location and no complete address, parse from event data
        if not meeting_location_str:
            return location

        # Clean up the location string if not done already
        cleaned_location = self._clean_location_string(meeting_location_str)

        if cleaned_location:
            location["name"] = cleaned_location

        return location

    def _clean_location_string(self, location_str):
        """Clean up location string by removing noise."""
        # Split on newlines and process
        lines = location_str.split("\n")
        cleaned_lines = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Skip lines that are primarily phone numbers
            if re.match(r"^\+?1?[\s-]?\d{3}[\s-]?\d{3}[\s-]?\d{4}", line):
                continue

            # Skip lines with conference IDs
            if re.search(r"conference\s*(id|no|number)", line, re.IGNORECASE):
                continue

            # Skip lines with meeting IDs or passcodes
            if re.search(r"(meeting\s*id|passcode|password)\s*:", line, re.IGNORECASE):
                continue

            # Skip lines that are URLs
            if re.match(r"https?://", line, re.IGNORECASE):
                continue

            # Skip lines with virtual meeting indicators
            if any(
                ind in line.lower()
                for ind in ["teams.microsoft.com", "zoom", "webex", "click here"]
            ):
                continue

            cleaned_lines.append(line)

        # Join remaining lines
        result = " ".join(cleaned_lines)

        # Remove any trailing meeting type descriptions
        result = re.sub(
            r"\s+(board|committee|commission)?\s*(meeting|session)?\s*$",
            "",
            result,
            flags=re.IGNORECASE,
        )

        return result.strip()

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
