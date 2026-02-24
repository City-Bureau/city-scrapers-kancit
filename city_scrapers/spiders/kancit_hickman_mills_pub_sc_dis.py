import html
import json
import re
from datetime import datetime

import scrapy
from city_scrapers_core.constants import BOARD, COMMITTEE, NOT_CLASSIFIED
from city_scrapers_core.items import Meeting
from city_scrapers_core.spiders import CityScrapersSpider
from dateutil.relativedelta import relativedelta


class KancitHickmanMillsPubScDisSpider(CityScrapersSpider):
    name = "kancit_hickman_mills_pub_sc_dis"
    agency = "Hickman Mills C-1 Public School District"
    timezone = "America/Chicago"
    custom_settings = {
        "ROBOTSTXT_OBEY": False,
        "COOKIES_ENABLED": True,
        "DOWNLOAD_DELAY": 3,
        "RANDOMIZE_DOWNLOAD_DELAY": True,
        "DEFAULT_REQUEST_HEADERS": {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",  # noqa
        },
    }

    # Simbli
    school_id = "223"
    main_url = (
        "https://simbli.eboardsolutions.com/SB_Meetings/SB_MeetingListing.aspx?S=223"
    )
    api_url = "https://simbli.eboardsolutions.com/Services/api/GetMeetingListing"

    # Hickman Mills calendar
    calendar_base_url = "https://www.hickmanmills.org/calendar"
    calendar_url = "https://www.hickmanmills.org/fs/elements/9768"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.simbli_upcoming_dates = set()
        self.seen_calendar_keys = set()

    async def start(self):
        """
        Requests the Simbli main page for token extraction.
        New async start method for Scrapy 2.13+
        """
        yield scrapy.Request(
            url=self.main_url,
            callback=self.parse,
        )

    def _is_board_related_calendar_event(self, title: str) -> bool:
        t = (title or "").lower()
        allow = [
            "board",
            "boe",
            "work session",
            "working session",
            "regular board meeting",
            "special session",
            "closed session",
            "hearing",
            "orientation",
            "committee",
            "dinner & dialogue",
            "retreat",
        ]
        deny = [
            "day",
            "week",
            "month",
            "appreciation",
            "national",
            "no school",
            "spring break",
            "first day",
            "last day",
            "track meet",
            "multicultural night",
            "awards",
            "half day",
            "teacher work day",
            "pd day",
            "memorial day",
            "juneteenth",
            "school lunch",
            "school nurses",
            "school communicators",
            "assistant principals",
            "school librarians",
            "paraprofessional",
            "school bus driver",
            "stem day",
            "bosses day",
            "hmc one awards",
        ]
        if any(d in t for d in deny):
            return False
        return any(a in t for a in allow)

    def parse(self, response):
        """Parse Simbli listing page → extract tokens → start API paging."""
        self.logger.info(
            f"[Simbli listing] {response.status} len={len(response.text)} url={response.url}"  # noqa
        )

        if (
            "simbli.eboardsolutions.com/SB_Meetings/SB_MeetingListing.aspx"
            not in response.url
        ):
            return

        connection_string = self._extract_token(
            response.text,
            [r"var\s+constr\s*=\s*'([^']+)'", r'var\s+constr\s*=\s*"([^"]+)"'],
        )

        security_token = self._extract_token(
            response.text,
            [
                r"var\s+sToken\s*=\s*'([^']+)'",
                r'var\s+sToken\s*=\s*"([^"]+)"',
                r'"SecurityToken"\s*:\s*"([^"]+)"',
            ],
        )

        self.logger.info(f"constr found? {'YES' if connection_string else 'NO'}")
        self.logger.info(f"sToken found? {'YES' if security_token else 'NO'}")

        if not (connection_string and security_token):
            self.logger.warning("Could not extract required tokens; cannot call API.")
            return

        yield from self._fetch_meetings_page(0, connection_string, security_token)

    def _extract_token(self, html, patterns):
        """Extract token from HTML using regex patterns."""
        for pattern in patterns:
            match = re.search(pattern, html)
            if match:
                return match.group(1)
        return None

    def _fetch_meetings_page(self, record_start, connection_string, security_token):
        """POST to Simbli GetMeetingListing with pagination."""
        payload = {
            "ListingType": "0",
            "TimeZone": "-60",
            "CustomSort": 0,
            "SortColName": "DateTime",
            "IsSortDesc": True,
            "RecordStart": record_start,
            "RecordCount": 50,
            "FilterExp": "",
            "ParentGroup": None,
            "IsUserLoggedIn": False,
            "UserID": "",
            "UserRole": None,
            "EncUserId": None,
            "Id": 0,
            "SchoolID": self.school_id,
            "ConnectionString": connection_string,
            "SecurityToken": security_token,
            "CreatedOn": "0001-01-01T00:00:00",
            "CreatedBy": None,
            "ModifiedOn": "0001-01-01T00:00:00",
            "ModifiedBy": None,
            "DeletedBy": None,
            "DeletedOnUTC": None,
            "IsDeleted": False,
        }

        yield scrapy.Request(
            url=self.api_url,
            method="POST",
            headers={
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Content-Type": "application/json",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": self.main_url,
            },
            body=json.dumps(payload),
            callback=self.parse_api_response,
            meta={
                "record_start": record_start,
                "connection_string": connection_string,
                "security_token": security_token,
            },
            dont_filter=True,
        )

    def parse_api_response(self, response):
        try:
            data = json.loads(response.text)
            meetings = self._extract_meetings_from_response(data)

            if not meetings:
                self.logger.info("No Simbli meetings found, falling back to calendar")
                yield from self.fetch_calendar_meetings()
                return

            for meeting_data in meetings:
                meeting = self._parse_simbli_meeting(meeting_data)
                if meeting:
                    yield meeting

            if len(meetings) > 0:
                next_offset = response.meta["record_start"] + len(meetings)
                yield from self._fetch_meetings_page(
                    next_offset,
                    response.meta["connection_string"],
                    response.meta["security_token"],
                )

        except json.JSONDecodeError:
            self.logger.error(
                "Failed to parse Simbli API response, falling back to calendar"
            )
            yield from self.fetch_calendar_meetings()

    def _extract_meetings_from_response(self, data):
        """Extract meetings list from common Simbli response structures."""
        if isinstance(data, dict):
            return data.get("MeetingList") or data.get("Data") or data.get("data")
        if isinstance(data, list):
            return data
        return None

    def _parse_simbli_meeting(self, meeting_data):
        now = datetime.now()
        start = self._parse_start_time(meeting_data)
        if not start:
            return None

        if start.date() >= now.date():
            self.simbli_upcoming_dates.add(start.date())

        one_year_ago = now - relativedelta(years=1)
        one_year_future = now + relativedelta(years=1)

        if start < one_year_ago or start > one_year_future:
            return None

        meeting = self._create_meeting(meeting_data, start)
        if meeting:
            meeting["status"] = self._get_status(meeting)
            meeting["id"] = self._get_id(meeting)
        return meeting

    def _classify_meeting(self, title):
        """Parse or generate classification from allowed options."""
        t = (title or "").lower()
        if "committee" in t:
            return COMMITTEE
        if "board" in t or "meeting" in t or "work session" in t or "workshop" in t:
            return BOARD
        return NOT_CLASSIFIED

    def _create_meeting(self, meeting_data, start):
        meeting_id = meeting_data.get("Master_MeetingID") or meeting_data.get(
            "MM_MeetingID"
        )
        meeting_url = (
            f"https://simbli.eboardsolutions.com/SB_Meetings/ViewMeeting.aspx?S={self.school_id}"  # noqa
            f"&MID={meeting_id}"
            if meeting_id
            else self.main_url
        )

        title = (
            meeting_data.get("MM_MeetingTitle")
            or meeting_data.get("MeetingTitle")
            or "Meeting"
        ).strip()

        return Meeting(
            title=title,
            description="",
            classification=self._classify_meeting(title),
            start=start,
            end=None,
            all_day=False,
            time_notes="",
            location=self._parse_location(meeting_data),
            links=[{"href": meeting_url, "title": "Meeting details"}],
            source=self.main_url,
        )

    def _parse_start_time(self, meeting_data):
        date_str = meeting_data.get("DateTime") or meeting_data.get("MM_DateTime")
        if not date_str:
            return None

        fmts = [
            "%m/%d/%Y - %I:%M %p",  # e.g. 02/12/2026 - 06:30 PM
            "%m/%d/%Y %I:%M %p",  # sometimes without hyphen
            "%Y-%m-%dT%H:%M:%S",  # ISO without tz
            "%Y-%m-%dT%H:%M:%S.%f",  # ISO with millis
        ]

        for fmt in fmts:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue

        try:
            dt = datetime.fromisoformat(date_str)
            return dt.replace(tzinfo=None)
        except Exception:
            return None

    def _parse_end(self, item):
        """Parse end datetime as a naive datetime object. Added by pipeline if None"""
        return None

    def _parse_time_notes(self, item):
        """Parse any additional notes on the timing of the meeting"""
        return ""

    def _parse_all_day(self, item):
        """Parse or generate all-day status. Defaults to False."""
        return False

    def _parse_location(self, meeting_data):
        """Parse and normalize meeting location from Simbli data"""

        address1 = (meeting_data.get("MM_Address1") or "").strip()
        address2 = (meeting_data.get("MM_Address2") or "").strip()
        address3 = (meeting_data.get("MM_Address3") or "").strip()

        full_text = " ".join(
            filter(
                None,
                [
                    address1.rstrip(".,").lower(),
                    address2.rstrip(".,").lower(),
                    address3.rstrip(".,").lower(),
                ],
            )
        )

        HICKMAN_MILLS_ADDRESS = "10301 Hickman Mills Dr., Kansas City, MO 64137"
        RWLC_VARIATIONS = [
            "real world learning center",
            "hickman mills administrative center",
            "open session board room",
            "10301 hickman mills dr",
        ]
        VIRTUAL_KEYWORDS = [
            "conference call",
            "videoconference",
            "video conference",
            "teleconference",
            "via teleconference",
            "livestream",
            "live stream",
            "via zoom",
            "virtual",
            "live at",
            "zoom.us",
        ]

        is_rwlc = any(v in full_text for v in RWLC_VARIATIONS)
        is_virtual = any(keyword in full_text for keyword in VIRTUAL_KEYWORDS)

        if is_rwlc and is_virtual:
            return {
                "name": "Real-World Learning Center (Hybrid Meeting)",
                "address": HICKMAN_MILLS_ADDRESS,
            }
        elif is_rwlc:
            return {
                "name": "Real-World Learning Center",
                "address": HICKMAN_MILLS_ADDRESS,
            }
        elif is_virtual:
            return {
                "name": "Virtual",
                "address": "",
            }

        location_name = address1
        location_address = " ".join(filter(None, [address2, address3])).strip()

        # If address contains RWLC keywords, canonicalize it
        if location_address and any(
            v in location_address.lower() for v in RWLC_VARIATIONS
        ):
            location_address = HICKMAN_MILLS_ADDRESS

        return {
            "name": location_name,
            "address": location_address,
        }

    def fetch_calendar_meetings(self):
        today = datetime.now()

        for i in range(12):
            target_date = today + relativedelta(months=i)
            target_month = target_date.month
            target_year = target_date.year

            cal_date = f"{target_year}-{target_month:02d}-01"
            params = {
                "cal_date": cal_date,
                "is_draft": "false",
                "is_load_more": "true",
                "page_id": "450",
                "parent_id": "9768",
                # Add a random timestamp to the URL to prevent caching
                "_": str(int(today.timestamp() * 1000) + i),
            }

            url = f"{self.calendar_url}?" + "&".join(
                [f"{k}={v}" for k, v in params.items()]
            )

            yield scrapy.Request(
                url=url,
                callback=self.parse_calendar_response,
                headers={
                    "Accept": "*/*",
                    "X-Requested-With": "XMLHttpRequest",
                    "Referer": self.calendar_base_url,
                },
                meta={"cal_date": cal_date},
                dont_filter=True,
            )

    def parse_calendar_response(self, response):
        """
        Parse the calendar AJAX response.
        Extracts meeting information from the calendar response HTML returned by the calendar AJAX endpoint. # noqa
        Loops through each day with events and extracts meeting elements.
        """
        event_days = response.css(".fsCalendarDaybox.fsStateHasEvents")

        for day_elem in event_days:
            events = day_elem.css(".fsCalendarInfo")
            for event_elem in events:
                meeting = self.parse_calendar_meeting(event_elem, day_elem)
                if meeting:
                    yield meeting

    def parse_calendar_meeting(self, event_elem, day_elem):
        """Parse individual meeting from calendar HTML"""
        title = event_elem.css("a.fsCalendarEventTitle::text").get()
        if not title:
            return None

        normalized_title = self._normalize_title(title.strip())

        # Filter to only board-related events
        if not self._is_board_related_calendar_event(normalized_title):
            return None

        start = self._parse_calendar_datetime(event_elem, day_elem)
        if not start:
            return None

        now = datetime.now()
        one_year_ago = now - relativedelta(years=1)
        one_year_future = now + relativedelta(years=1)

        if start < one_year_ago or start > one_year_future:
            return None

        if start < datetime.now():
            return None

        if start.date() in self.simbli_upcoming_dates:
            return None

        key = (normalized_title.lower(), start)
        if key in self.seen_calendar_keys:
            return None
        self.seen_calendar_keys.add(key)

        location_text = event_elem.css(".fsLocation::text").get()
        location_name = location_text.strip() if location_text else ""
        if (
            "real world learning center" in location_name.lower()
            or "hickman mills" in location_name.lower()
        ):
            if "," in location_name:
                clean_name = location_name.split(",")[0].strip()
                location_address = "10301 Hickman Mills Dr., Kansas City, MO 64137"
            else:
                clean_name = "Real-World Learning Center"
                location_address = "10301 Hickman Mills Dr., Kansas City, MO 64137"
        elif location_name and "," in location_name:
            parts = location_name.split(",")
            first_part = parts[0].strip()

            if re.match(r"^\d+\s+", first_part):
                clean_name = ""
                location_address = location_name
            else:
                clean_name = first_part
                location_address = ", ".join(parts[1:]).strip()
        else:
            if re.match(r"^\d+\s+", location_name):
                clean_name = ""
                location_address = location_name
            else:
                clean_name = location_name
                location_address = ""

        location = {
            "name": clean_name,
            "address": location_address,
        }

        return self._create_calendar_meeting(
            title=normalized_title,
            start=start,
            location=location,
            links=[],
            source=self.calendar_base_url,
        )

    def _parse_calendar_datetime(self, event_elem, day_elem):

        time_elem = event_elem.css("time.fsStartTime")
        datetime_str = time_elem.attrib.get("datetime") if time_elem else None

        if datetime_str:
            return self._parse_iso_datetime(datetime_str)

        date_elem = day_elem.css(".fsCalendarDate")
        day = date_elem.attrib.get("data-day")
        month = date_elem.attrib.get("data-month")
        year = date_elem.attrib.get("data-year")

        if day and month and year:
            try:
                return datetime(int(year), int(month), int(day))
            except (ValueError, TypeError):
                return None

        return None

    def _parse_iso_datetime(self, datetime_str):
        try:
            return datetime.fromisoformat(datetime_str).replace(tzinfo=None)
        except ValueError:
            return None

    def _normalize_title(self, title):
        title = html.unescape(title)

        date_patterns = [
            r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}\s+",  # noqa
            r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}\s+",  # noqa
            r"\b\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}\s+",  # noqa
        ]

        for pattern in date_patterns:
            title = re.sub(pattern, "", title, flags=re.IGNORECASE)

        # Remove parentheses around cancelled/rescheduled
        title = re.sub(
            r"\(\s*(cancel\w+|rescheduled)\s*\)", r"\1", title, flags=re.IGNORECASE
        )

        return " ".join(title.split()).strip()

    def _create_calendar_meeting(self, title, start, location, links, source):
        """Create a Meeting object for calendar meetings"""
        meeting = Meeting(
            title=title,
            description="",
            classification=self._classify_meeting(title),
            start=start,
            end=None,
            all_day=False,
            time_notes="Please refer to the meeting attachments for more accurate information about the meeting details, address and time",  # noqa
            location=location,
            links=links,
            source=source,
        )

        meeting["status"] = self._get_status(meeting)
        meeting["id"] = self._get_id(meeting)

        return meeting
