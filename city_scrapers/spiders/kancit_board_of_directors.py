import calendar
import html
import json
import re
from datetime import datetime

import scrapy
from city_scrapers_core.constants import BOARD, COMMITTEE, NOT_CLASSIFIED
from city_scrapers_core.items import Meeting
from city_scrapers_core.spiders import CityScrapersSpider
from curl_cffi import requests as curl_requests


class KancitBoardOfDirectorsSpider(CityScrapersSpider):
    name = "kancit_board_of_directors"
    agency = "Kansas City Board of Directors"
    timezone = "America/Chicago"

    custom_settings = {
        "ROBOTSTXT_OBEY": False,
        "DOWNLOAD_DELAY": 1,
    }

    # Simbli eBoard scraping (main source)
    main_url = (
        "https://simbli.eboardsolutions.com/SB_Meetings/SB_MeetingListing.aspx?S=228"
    )
    api_url = "https://simbli.eboardsolutions.com/Services/api/GetMeetingListing"
    # KCPS calendar scraping (only for upcoming meetings for School Board and all DACs)
    calendar_api_url = (
        "https://thrillshare-cmsv2.services.thrillshare.com/api/v4/o/30884/cms/events"
    )
    calendar_base_url = (
        "https://www.kcpublicschools.org/events?filter_ids=650065,650066&view=cal-month"
    )
    calendar_filter_names = {"School Board", "District Advisory Committee (DAC)"}

    # Set to track upcoming meeting dates from Simbli to avoid duplicates with calendar meetings # noqa
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.simbli_upcoming_dates = set()

    def start_requests(self):
        """
        Fetch main page with curl_cffi to bypass Incapsula fingerprinting.
        """
        response = curl_requests.get(
            self.main_url,
            impersonate="chrome120",
        )
        if not response or len(response.text) < 10000:
            self.logger.warning(
                f"Unexpected response from {self.main_url}: "
                f"status={response.status_code if response else 'no response'}, "
            )
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

        if connection_string and security_token:
            yield from self._fetch_meetings_page(0, connection_string, security_token)
        else:
            self.logger.warning(f"Failed to extract tokens from {self.main_url}")

    def fetch_calendar_meetings(self):
        """Fetch upcoming meetings from Thrillshare calendar API."""
        today = datetime.now()

        for i in range(13):  # current month + 12 months ahead
            month = (today.month + i - 1) % 12 + 1
            year = today.year + (today.month + i - 1) // 12
            start_date = f"{year}-{month:02d}-01"
            last_day = calendar.monthrange(year, month)[1]
            end_date = f"{year}-{month:02d}-{last_day}"

            url = (
                f"{self.calendar_api_url}"
                f"?start_date={start_date}&end_date={end_date}"
                f"&section_ids=514507&paginate=false&locale=en"
            )

            yield scrapy.Request(
                url=url,
                callback=self.parse_calendar_response,
                headers={"accept": "application/json"},
                dont_filter=True,
            )

    def parse_calendar_response(self, response):
        """Parse Thrillshare calendar API response."""
        try:
            data = response.json()
        except Exception:
            self.logger.warning(f"Failed to parse calendar response: {response.url}")
            return

        for event in data.get("events", []):
            # Filter only board-related meetings
            filter_names = set(event.get("filter_name", []))
            if not filter_names & self.calendar_filter_names:
                continue

            meeting = self._parse_calendar_meeting(event)
            if meeting:
                yield meeting

    def _parse_calendar_meeting(self, event):
        """Parse individual meeting from Thrillshare API event."""
        title = event.get("title", "").strip()
        if not title:
            return None

        start = self._parse_calendar_datetime(event.get("start_at"))
        if not start:
            return None

        filter_names = set(event.get("filter_name", []))
        is_dac = "District Advisory Committee (DAC)" in filter_names
        is_past = start.date() < datetime.now().date()

        # DAC: allow past from March 2026 onward
        # School Board: only upcoming
        if is_past and not is_dac:
            return None
        if is_dac and start < datetime(2026, 3, 1):
            return None

        # Skip if already in Simbli
        if start.date() in self.simbli_upcoming_dates:
            return None

        address = event.get("address", "").strip()
        location = self._parse_calendar_location(address)

        return self._create_meeting(
            title=self._normalize_title(title),
            start=start,
            location=location,
            links=[{"href": "", "title": ""}],
            source=self.calendar_base_url,
        )

    def _parse_calendar_datetime(self, datetime_str):
        """Parse ISO 8601 datetime string from Thrillshare API."""
        if not datetime_str:
            return None
        # Format: "2026-03-03T08:00:00.000-06:00"
        match = re.match(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})", datetime_str)
        if match:
            try:
                return datetime.fromisoformat(match.group(1))
            except ValueError:
                return None
        return None

    def _parse_calendar_location(self, address):
        """Parse location from Thrillshare address string."""
        if "2901 Troost" in address:
            return {
                "name": "Board of Education",
                "address": "2901 Troost Ave, Kansas City, MO 64109",
            }
        return {
            "name": "",
            "address": address,
        }

    def _extract_token(self, html, patterns):
        """Extract token from HTML using regex patterns"""
        for pattern in patterns:
            match = re.search(pattern, html)
            if match:
                return match.group(1)

        return None

    def _fetch_meetings_page(self, record_start, connection_string, security_token):
        """
        Fetch a page of meetings via API.
        Sends a POST request to Simbli API.
        Handles pagination (50 meetings per page).
        Includes required connection tokens in payload.
        """
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
            "SchoolID": "228",
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
        )

    def parse_api_response(self, response):
        """
        Parse JSON API response and continue pagination
        Yields Meeting objects for each meeting.
        First scrapes Simbli for meetings.
        If no meetings are found, it falls back to scraping the calendar for upcoming meetings. # noqa
        """
        try:
            data = json.loads(response.text)
            meetings = self._extract_meetings_from_response(data)

            if not meetings:
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
            self.logger.warning(
                f"Failed to parse JSON response from {response.url}: {response.text[:200]}"  # noqa
            )
            pass

    def _parse_simbli_meeting(self, meeting_data):
        """
        Parse individual meeting data.
        Converts Simbli meeting data into a Meeting object.
        """
        start = self._parse_start_time(meeting_data)
        if not start:
            return None

        # Only store upcoming Simbli dates
        if start.date() >= datetime.now().date():
            self.simbli_upcoming_dates.add(start.date())

        meeting_id = meeting_data.get("Master_MeetingID")
        meeting_url = f"https://simbli.eboardsolutions.com/SB_Meetings/ViewMeeting.aspx?S=228&MID={meeting_id}"  # noqa

        raw_title = meeting_data.get("MM_MeetingTitle", "Board Meeting")

        return self._create_meeting(
            title=self._normalize_title(raw_title),
            start=start,
            location=self._parse_location(meeting_data),
            links=[{"href": meeting_url, "title": "Meeting details"}],
            source=self.main_url,
        )

    def _create_meeting(self, title, start, location, links, source):
        """Create a Meeting object with common fields"""
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

    def _normalize_title(self, title):
        """Remove date patterns and clean up meeting titles"""
        # Decode HTML entities
        title = html.unescape(title)

        # Remove date patterns
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

    def _classify_meeting(self, title):
        """Classify meeting based on title keywords"""
        title_lower = title.lower()

        if "committee" in title_lower or "dac" in title_lower:
            return COMMITTEE
        elif (
            "board" in title_lower
            or "workshop" in title_lower
            or "meeting" in title_lower
        ):
            return BOARD
        else:
            return NOT_CLASSIFIED

    def _parse_start_time(self, meeting_data):
        """Parse meeting start time from various formats"""
        date_str = meeting_data.get("DateTime") or meeting_data.get("MM_DateTime")
        if not date_str:
            return None

        for fmt in ["%m/%d/%Y - %I:%M %p", "%Y-%m-%dT%H:%M:%S"]:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                self.logger.debug(
                    f"Could not parse date string '{date_str}' with format '{fmt}'"
                )
                continue

        return None

    def _parse_location(self, meeting_data):
        """Parse and normalize meeting location from Simbli data"""

        address1 = (meeting_data.get("MM_Address1") or "").strip()
        address2 = (meeting_data.get("MM_Address2") or "").strip()
        address3 = (meeting_data.get("MM_Address3") or "").strip()

        normalized_address1 = address1.rstrip(".,").lower()
        normalized_address2 = address2.rstrip(".,").lower()
        normalized_address3 = address3.rstrip(".,").lower()

        full_text = " ".join(
            filter(
                None, [normalized_address1, normalized_address2, normalized_address3]
            )
        )

        BOARD_ADDRESS = "2901 Troost Ave, Kansas City, MO 64109"

        # Board of Education (2901 Troost) — versions
        TROOST_VARIATIONS = [
            "2901 troost ave",
            "2901 troost avenue",
            "2901 troost",
            "board auditorium",
            "board of education building",
            "board of education",
            "board room",
            "kcps board of education building",
            "delano",
        ]

        # Virtual / Remote Meetings
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
            "kcpublicschools.org/live",
            "816.418.1113",
            "816-418-1113",
            "zoom",
        ]

        TEAMS_KEYWORDS = [
            "teams",
            "msteams",
        ]

        is_board_troost_variation = any(v in full_text for v in TROOST_VARIATIONS)
        is_virtual = any(keyword in full_text for keyword in VIRTUAL_KEYWORDS)
        is_teams = any(keyword in full_text for keyword in TEAMS_KEYWORDS)

        # HYBRID (Board of Education + Virtual)
        if is_board_troost_variation and is_virtual:
            #       Optional: extract room name if present
            room_match = re.search(
                r"(delano room|board room|westport room)",
                full_text,
                re.IGNORECASE,
            )

            if room_match:
                room_name = room_match.group(1).title()
                name = f"{room_name} (Hybrid Meeting)"
            else:
                name = "Board of Education (Hybrid Meeting)"

            return {
                "name": name,
                "address": BOARD_ADDRESS,
            }
        # Physical Board Only
        elif is_board_troost_variation:
            return {
                "name": "Board of Education",
                "address": BOARD_ADDRESS,
            }

        # Virtual and Teams
        elif is_teams and is_virtual:
            return {
                "name": address1,
                "address": "",
            }

        elif is_virtual:
            return {
                "name": "Virtual",
                "address": "",
            }

        # 1215 E Truman Rd — Cardinal -B Room
        if (
            "1215 e truman rd" in normalized_address1
            and "cardinal -b room" in normalized_address3
        ):
            return {
                "name": "Cardinal -B Room",
                "address": "1215 E Truman Rd, Kansas City, MO 64106",
            }

        # Fallback — keep original structure
        location_name = address1
        location_address = " ".join(filter(None, [address2, address3])).strip()

        if location_address:
            normalized_location_address = location_address.lower()

            # If contains "2901 troost" anywhere → force canonical address
            if "2901 troost" in normalized_location_address:
                location_address = BOARD_ADDRESS

        return {
            "name": location_name,
            "address": location_address,
        }

    def _extract_meetings_from_response(self, data):
        """Extract meetings list from various JSON response structures"""
        if isinstance(data, dict):
            return (
                data.get("MeetingList")
                or data.get("Data")
                or data.get("data")
                or data.get("meetings")
            )
        elif isinstance(data, list):
            return data
        return None
