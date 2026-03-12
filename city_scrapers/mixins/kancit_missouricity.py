from collections import defaultdict

from city_scrapers_core.items import Meeting
from city_scrapers_core.spiders import LegistarSpider


class KancitMissouricityMixinMeta(type):
    """
    Metaclass that enforces the implementation of required static
    variables in child classes that inherit from KancitMissouricityMixin.
    """

    def __init__(cls, name, bases, dct):
        required_static_vars = ["agency", "name"]
        missing_vars = [var for var in required_static_vars if var not in dct]

        if missing_vars:
            missing_vars_str = ", ".join(missing_vars)
            raise NotImplementedError(
                f"{name} must define the following static variable(s): "
                f"{missing_vars_str}."
            )

        super().__init__(name, bases, dct)


class KancitMissouricityMixin(LegistarSpider, metaclass=KancitMissouricityMixinMeta):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.since_year = 2020
        self._scraped_urls = set()

    timezone = "America/Chicago"
    start_urls = ["https://clerk.kcmo.gov/Calendar.aspx"]

    # Legistar calendar requires bypassing robots.txt
    custom_settings = {
        "ROBOTSTXT_OBEY": False,
    }

    # Required attributes to be set by child classes
    name = None
    agency = None
    description = ""
    classification = None
    meeting_location = {}

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
                        if "View.ashx?M=IC" in url:
                            header = "iCalendar"
                            value = {"url": url}
                        else:
                            value = {"label": field_text, "url": url}
                    else:
                        value = field_text

                    data[header] = value

                ical_url = data.get("iCalendar", {}).get("url")
                if ical_url is None or ical_url in self._scraped_urls:
                    continue
                else:
                    self._scraped_urls.add(ical_url)
                events.append(dict(data))
            except Exception:
                self.logger.exception(f"Failed to parse row: {row.get()}")

        return events

    def _get_event_title(self, event):
        """Extract title from event data."""
        if isinstance(event.get("Name"), dict):
            return event["Name"].get("label", "")
        return event.get("Name", "")

    def _is_agency_match(self, event):
        """Check if this event matches the agency filter."""
        title = self._get_event_title(event)
        return title == self.agency

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
                description=self.description.format(agency=self.agency),
                classification=self.classification,
                start=start,
                end=None,
                all_day=False,
                time_notes="",
                location=self.meeting_location,
                links=self.legistar_links(event),
                source=self.legistar_source(event),
            )

            meeting["status"] = self._get_status(meeting, text=location_text)
            meeting["id"] = self._get_id(meeting)

            yield meeting
