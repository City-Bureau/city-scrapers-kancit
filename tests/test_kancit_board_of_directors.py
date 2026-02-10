from datetime import datetime
from os.path import dirname, join

import pytest
from city_scrapers_core.constants import BOARD, COMMITTEE, NOT_CLASSIFIED
from city_scrapers_core.items import Meeting
from city_scrapers_core.utils import file_response
from freezegun import freeze_time
from scrapy import Request

from city_scrapers.spiders.kancit_board_of_directors import KancitBoardOfDirectorsSpider

# Load test files
test_calendar_response = file_response(
    join(dirname(__file__), "files", "kancit_board_of_directors.html"),
    url="https://www.kcpublicschools.org/fs/elements/4952?cal_date=2026-01-01&is_draft=false&is_load_more=true&page_id=338&parent_id=4952&_=1234567890",  # noqa
)

test_api_response = file_response(
    join(dirname(__file__), "files", "kancit_board_of_directors.json"),
    url="https://simbli.eboardsolutions.com/Services/api/GetMeetingListing",
)

test_api_response.request = Request(
    url=test_api_response.url,
    meta={
        "record_start": 0,
        "connection_string": "test_connection_string",
        "security_token": "test_security_token",
    },
)


spider = KancitBoardOfDirectorsSpider()

freezer = freeze_time("2026-01-10")
freezer.start()

# Parse calendar-based meetings
parsed_calendar_items = []
for item in spider.parse_calendar_response(test_calendar_response):
    if isinstance(item, Meeting):
        parsed_calendar_items.append(item)

freezer.stop()

# Parse API-based meetings (use different freeze time to test past/future logic)
freezer2 = freeze_time("2026-01-28")  # After all meetings
freezer2.start()

parsed_api_items = []
for item in spider.parse_api_response(test_api_response):
    if isinstance(item, Meeting):
        parsed_api_items.append(item)

# Combine all items for general tests
parsed_items = parsed_calendar_items + parsed_api_items

freezer2.stop()


# CALENDAR-BASED MEETING TESTS
def test_calendar_meeting_count():
    """Test that we parsed expected calendar meetings"""
    # HTML has 4 meetings in January 2026, all should be parsed when frozen to Jan 10
    assert len(parsed_calendar_items) == 4


def test_calendar_first_meeting():
    """Test first calendar meeting - Jan 14 Policy Monitoring"""
    if len(parsed_calendar_items) == 0:
        pytest.skip("No calendar meetings parsed")

    item = parsed_calendar_items[0]
    assert "Policy Monitoring" in item["title"]
    assert item["start"] == datetime(2026, 1, 14, 18, 45)
    assert item["classification"] == BOARD


def test_calendar_committee_meetings():
    """Test that Ad Hoc Committee meetings are classified correctly"""
    committee_meetings = [
        m for m in parsed_calendar_items if m["classification"] == COMMITTEE
    ]
    assert len(committee_meetings) == 2


def test_calendar_locations():
    """Test calendar location parsing"""
    # Jan 20 meeting should have location
    jan_20_meetings = [m for m in parsed_calendar_items if m["start"].day == 20]
    if jan_20_meetings:
        assert (
            "Board of Education" in jan_20_meetings[0]["location"]["name"]
            or "Seven Oaks" in jan_20_meetings[0]["location"]["name"]
        )


def test_calendar_meeting_structure():
    """Test calendar meetings have correct structure"""
    for item in parsed_calendar_items:
        assert item["title"] != ""
        assert isinstance(item["start"], datetime)
        assert item["end"] is None
        assert item["all_day"] is False
        assert isinstance(item["location"], dict)
        assert "name" in item["location"]
        assert isinstance(item["links"], list)


# API-BASED MEETING TESTS


def test_api_meeting_count():
    """Test that we parsed expected API meetings"""
    # Based on the JSON, we should have 3 meetings
    assert len(parsed_api_items) == 3


def test_api_first_item():
    """Test first API meeting properties"""
    if len(parsed_api_items) == 0:
        pytest.skip("No API meetings parsed")

    item = parsed_api_items[0]

    # First meeting from JSON is "Policy Committee Meeting"
    assert item["title"] == "Policy Committee Meeting"
    assert item["start"] == datetime(2025, 12, 9, 11, 30)
    assert item["classification"] == COMMITTEE
    assert item["location"]["name"] == "Board of Education"

    # Check meeting details link format
    assert len(item["links"]) == 1
    assert (
        "https://simbli.eboardsolutions.com/SB_Meetings/ViewMeeting.aspx?S=228&MID=23208"  # noqa
        in item["links"][0]["href"]
    )
    assert item["links"][0]["title"] == "Meeting details"


def test_api_second_item():
    """Test second API meeting - checks title normalization"""
    if len(parsed_api_items) < 2:
        pytest.skip("Not enough API meetings parsed")

    item = parsed_api_items[1]

    # Should remove "January 2026" from title
    assert item["title"] == "Policy Monitoring Workshop"
    assert item["start"] == datetime(2026, 1, 14, 17, 30)
    assert item["classification"] == BOARD


def test_api_third_item():
    """Test third API meeting - committee classification"""
    if len(parsed_api_items) < 3:
        pytest.skip("Not enough API meetings parsed")

    item = parsed_api_items[2]

    assert "Committee" in item["title"]
    assert item["start"] == datetime(2026, 1, 20, 8, 0)
    assert item["classification"] == COMMITTEE


def test_api_meeting_structure():
    """Test API meetings have correct structure"""
    for item in parsed_api_items:
        assert item["title"] != ""
        assert isinstance(item["start"], datetime)
        assert item["end"] is None
        assert item["all_day"] is False
        assert isinstance(item["location"], dict)
        assert "name" in item["location"]
        assert "address" in item["location"]


# TITLE NORMALIZATION TESTS


def test_title_normalization():
    """Test that titles are properly normalized"""
    test_cases = [
        ("January 2019 Policy Monitoring Workshop", "Policy Monitoring Workshop"),
        (
            "June 5, 2019 Superintendent Evaluation Process Review",
            "Superintendent Evaluation Process Review",
        ),
        (
            "June 16, 2020 Government Relations Ad Hoc Committee",
            "Government Relations Ad Hoc Committee",
        ),
        ("Board Meeting", "Board Meeting"),
        ("December 2025 Special Meeting", "Special Meeting"),
        ("Policy Committee Meeting ", "Policy Committee Meeting"),  # Trailing space
        (
            "January 2026 Policy Monitoring Workshop",
            "Policy Monitoring Workshop",
        ),  # From JSON
    ]

    for input_title, expected_output in test_cases:
        result = spider._normalize_title(input_title)
        assert (
            result == expected_output
        ), f"Failed for '{input_title}': got '{result}', expected '{expected_output}'"


def test_title_removes_cancelled_parentheses():
    """Test that (Cancelled) becomes Cancelled for core's _clean_title to handle"""
    assert spider._normalize_title("Meeting (Cancelled)") == "Meeting Cancelled"
    assert spider._normalize_title("Workshop (Rescheduled)") == "Workshop Rescheduled"


def test_title_decodes_html_entities():
    """Test that HTML entities are decoded"""
    assert (
        spider._normalize_title("Finance &amp; Budget Committee")
        == "Finance & Budget Committee"
    )


# CLASSIFICATION TESTS
# ============================================================================


def test_classification_board():
    """Test board meeting classification"""
    assert spider._classify_meeting("Board of Education Meeting") == BOARD
    assert spider._classify_meeting("School Board Meeting") == BOARD
    assert spider._classify_meeting("Board Workshop") == BOARD
    assert spider._classify_meeting("Policy Monitoring Workshop") == BOARD
    assert spider._classify_meeting("School Board Policy Monitoring Meeting") == BOARD


def test_classification_committee():
    """Test committee meeting classification"""
    assert spider._classify_meeting("Finance Committee Meeting") == COMMITTEE
    assert spider._classify_meeting("Policy Committee") == COMMITTEE
    assert spider._classify_meeting("Ad Hoc Committee") == COMMITTEE
    assert (
        spider._classify_meeting("Government Relations Ad Hoc Committee") == COMMITTEE
    )
    assert (
        spider._classify_meeting(
            "School Board Ad Hoc Committee Meeting (Finance and Audit)"
        )
        == COMMITTEE
    )


def test_classification_workshop():
    """Test workshop classification defaults to BOARD"""
    assert spider._classify_meeting("Budget Workshop") == BOARD


# LOCATION TESTS


def test_location_board_of_education():
    """Test Board of Education location parsing"""
    meeting_data = {
        "MM_Address1": "2901 Troost Ave",
        "MM_Address2": "Kansas City, MO 64109",
        "MM_Address3": "Seven Oaks Conference Room",
    }

    location = spider._parse_location(meeting_data)
    assert location["name"] == "Board of Education"
    assert "2901 Troost Ave" in location["address"]
    assert "Kansas City, MO 64109" in location["address"]


def test_location_board_of_education_with_trailing_chars():
    """Test Board of Education location parsing with period/comma"""
    meeting_data = {
        "MM_Address1": "2901 Troost Ave.",
        "MM_Address2": "Kansas City, MO 64109",
        "MM_Address3": "",
    }

    location = spider._parse_location(meeting_data)
    assert location["name"] == "Board of Education"


def test_location_other_venue():
    """Test other venue location parsing"""
    meeting_data = {
        "MM_Address1": "Manual Career Tech Center",
        "MM_Address2": "1215 E Truman Rd",
        "MM_Address3": "Kansas City, MO 64106",
    }

    location = spider._parse_location(meeting_data)
    assert location["name"] == "Manual Career Tech Center"
    assert "1215 E Truman Rd" in location["address"]


def test_location_special_address():
    """Test special address handling for 1215 E Truman Rd"""
    meeting_data = {
        "MM_Address1": "1215 E Truman Rd",
        "MM_Address2": "Kansas City, MO 64106",
        "MM_Address3": "",
    }

    location = spider._parse_location(meeting_data)
    # Based on your spider code, this should result in empty name
    assert location["name"] == ""
    assert "Kansas City, MO 64106" in location["address"]


# DATETIME PARSING TESTS


def test_iso_datetime_parsing():
    """Test ISO 8601 datetime parsing"""
    test_cases = [
        ("2026-01-14T18:45:00-06:00", datetime(2026, 1, 14, 18, 45)),
        ("2026-01-22T09:30:00-06:00", datetime(2026, 1, 22, 9, 30)),
        ("2026-04-08T18:45:00-05:00", datetime(2026, 4, 8, 18, 45)),
    ]

    for dt_str, expected in test_cases:
        result = spider._parse_iso_datetime(dt_str)
        assert result == expected, f"Failed parsing {dt_str}"


# GENERAL MEETING TESTS (ALL SOURCES)
def test_title():
    """Test all meetings have valid titles"""
    for item in parsed_items:
        assert isinstance(item["title"], str)
        assert item["title"] != ""


def test_description():
    """Test all meetings have description field"""
    for item in parsed_items:
        assert isinstance(item["description"], str)


def test_start():
    """Test all meetings have valid start datetime"""
    for item in parsed_items:
        assert isinstance(item["start"], datetime)


def test_end():
    """Test all meetings have None for end time"""
    for item in parsed_items:
        assert item["end"] is None


def test_time_notes():
    """Test all meetings have time_notes field"""
    for item in parsed_items:
        assert isinstance(item["time_notes"], str)


def test_id_and_status():
    """Test all meetings have valid ID and status"""
    for item in parsed_items:
        assert item["id"]
        assert item["status"] in ["tentative", "cancelled", "passed"]


def test_location():
    """Test all meetings have valid location"""
    for item in parsed_items:
        assert isinstance(item["location"], dict)
        assert "name" in item["location"]
        assert "address" in item["location"]


def test_source():
    """Test all meetings have valid source URL"""
    for item in parsed_items:
        assert item["source"]
        assert item["source"].startswith("http")


def test_links():
    """Test all meetings have valid links structure"""
    for item in parsed_items:
        assert isinstance(item["links"], list)
        assert len(item["links"]) >= 1
        for link in item["links"]:
            assert "href" in link
            assert "title" in link


def test_classification():
    """Test all meetings have valid classification"""
    for item in parsed_items:
        assert item["classification"] in [BOARD, COMMITTEE, NOT_CLASSIFIED]


@pytest.mark.parametrize("item", parsed_items)
def test_all_day(item):
    """Test all meetings are not all-day events"""
    assert item["all_day"] is False


# SPECIFIC MEETING VALIDATION TESTS


def test_meeting_has_valid_year():
    """Test that meetings are in reasonable year range"""
    for item in parsed_items:
        assert 2020 <= item["start"].year <= 2030


def test_calendar_meetings_are_upcoming():
    """Test that calendar meetings were parsed as upcoming (frozen to Jan 10)"""
    for item in parsed_calendar_items:
        # All meetings should be on or after Jan 14, 2026
        assert item["start"].date() >= datetime(2026, 1, 14).date()


def test_api_meetings_marked_as_passed():
    """Test that past API meetings are marked as passed (frozen to Jan 28)"""
    # Dec 9 meeting should be marked as passed
    dec_meetings = [m for m in parsed_api_items if m["start"].month == 12]
    for m in dec_meetings:
        assert m["status"] == "passed"


def test_api_meetings_marked_correctly():
    """Test API meeting status based on freeze date Jan 28"""
    for item in parsed_api_items:
        if item["start"] < datetime(2026, 1, 28):
            assert item["status"] == "passed"
        else:
            assert item["status"] in ["tentative"]
